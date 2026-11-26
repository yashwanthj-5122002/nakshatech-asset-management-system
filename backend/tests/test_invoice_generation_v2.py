"""Invoice Generation V2: Auto Fill / Manual modes, multi-line items, GST split,
invoice snapshot immutability, reconciliation validation and legacy compatibility.

ProjectInvoice stays the only financial source of truth throughout: line items and
GST breakdown are presentation/detail on top of it, validated to reconcile to
``amount``/``tax_amount`` before the invoice is ever created.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import func, select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.invoice_documents import build_invoice_a4_pdf, invoice_document_payload
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoiceLineItem, ProjectInvoicePayment
from app.modules.operations.lifecycle_schemas import (
    InvoiceBillingSnapshotOverride,
    InvoiceDraftCreate,
    InvoiceLineItemCreate,
)
from app.modules.operations.lifecycle_service import create_invoice_draft, invoice_auto_fill
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str) -> User:
    row = User(
        email=email, full_name=email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _billable_project(db, suffix: str, *, gstin: str = "29ABCDE1234F1Z5", country: str = "India"):
    finance = _user(db, f"finance.v2.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"V2-{suffix}", client_name=f"V2 Client {suffix}", contact_person_name="Accounts Contact",
        contact_person_phone="9999999999", client_email=f"accounts.{suffix.lower()}@example.com",
        address="Client Master Address", country=country, gst_number=gstin, source_team="bd",
        source_person_name="BD Owner", is_active=True, created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"V2-P-{suffix}", project_name=f"V2 Survey Project {suffix}", client_id=client.id,
        client_name=client.client_name, description="Geospatial project services",
        start_date=date(2026, 9, 1), end_date=date(2026, 12, 31), created_by_id=finance.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectWorkflow(
        project_id=project.id, bd_owner_user_id=finance.id, performing_department_code="lidar",
        status="READY_FOR_BILLING", commercial_value=Decimal("147500"), currency="INR",
        created_by_id=finance.id, updated_by_id=finance.id,
    ))
    db.flush()
    return finance, client, project


DEMO_ITEMS = [
    InvoiceLineItemCreate(
        sequence=1, description="Digitization of Road Topographical Features at Goa",
        hsn_sac="998399", unit="Nos", quantity=Decimal("2"), rate=Decimal("50000"), amount=Decimal("100000"),
    ),
    InvoiceLineItemCreate(
        sequence=2, description="Data Processing and CAD Deliverables",
        hsn_sac="998399", unit="Nos", quantity=Decimal("1"), rate=Decimal("25000"), amount=Decimal("25000"),
    ),
]


def _demo_payload(**overrides) -> InvoiceDraftCreate:
    base = dict(
        invoice_number=overrides.pop("invoice_number", "INV-V2-DEMO"),
        invoice_date=date(2026, 10, 15), due_date=date(2026, 11, 14),
        amount=Decimal("125000"), tax_amount=Decimal("22500"), currency="INR",
        payment_terms="Net 30", po_wo_reference="PO-2026-DEMO", entry_mode="manual",
        line_items=list(DEMO_ITEMS), cgst_percent=Decimal("9.00"), cgst_amount=Decimal("11250"),
        sgst_percent=Decimal("9.00"), sgst_amount=Decimal("11250"),
        work_order_date=date(2026, 10, 1), dispatch_details="By courier", dispatch_date=date(2026, 10, 16),
        place_of_supply="Goa",
    )
    base.update(overrides)
    return InvoiceDraftCreate(**base)


def test_exact_demo_invoice_two_items_cgst_sgst_and_amount_in_words():
    """Step 28 scenario: exact two-item, CGST+SGST split demo invoice."""
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "DEMO")
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=_demo_payload())
        db.flush()

        payload = invoice_document_payload(db, invoice.id)
        assert len(payload["line_items"]) == 2
        assert payload["line_items"][0]["description"] == "Digitization of Road Topographical Features at Goa"
        assert payload["line_items"][0]["taxable_amount"] == Decimal("100000.00")
        assert payload["line_items"][1]["description"] == "Data Processing and CAD Deliverables"
        assert payload["line_items"][1]["taxable_amount"] == Decimal("25000.00")

        labels = {line["label"]: line["amount"] for line in payload["tax_lines"]}
        assert labels["CGST @ 9.00%"] == Decimal("11250.00")
        assert labels["SGST @ 9.00%"] == Decimal("11250.00")
        assert "IGST" not in " ".join(labels)

        assert payload["totals"]["taxable_amount"] == Decimal("125000.00")
        assert payload["totals"]["invoice_total"] == Decimal("147500.00")
        assert payload["totals"]["amount_in_words"] == "Indian Rupee One Lakh Forty-Seven Thousand Five Hundred Only"

        pdf = build_invoice_a4_pdf(payload)
        reader = PdfReader(pdf)
        # Wrapped table cells insert line breaks mid-sentence in pypdf's extracted text,
        # so compare against whitespace-normalized text rather than the literal string.
        text = " ".join(" ".join(p.extract_text() or "" for p in reader.pages).split())
        assert "Digitization of Road Topographical Features at Goa" in text
        assert "Data Processing and CAD Deliverables" in text
        assert "CGST" in text and "SGST" in text
        assert "IGST" not in text
        assert payload["totals"]["amount_in_words"] in text
        db.rollback()


def test_igst_invoice_excludes_cgst_sgst():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "IGST", country="United Arab Emirates")
        payload_in = _demo_payload(
            invoice_number="INV-V2-IGST", cgst_percent=None, cgst_amount=None, sgst_percent=None, sgst_amount=None,
            igst_percent=Decimal("18.00"), igst_amount=Decimal("22500"),
        )
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=payload_in)
        db.flush()
        payload = invoice_document_payload(db, invoice.id)
        labels = [line["label"] for line in payload["tax_lines"]]
        assert labels == ["IGST @ 18.00%"]
        assert payload["totals"]["invoice_total"] == Decimal("147500.00")
        db.rollback()


def test_igst_cannot_be_combined_with_cgst_sgst():
    with pytest.raises(ValidationError, match="IGST cannot be combined"):
        _demo_payload(igst_percent=Decimal("18"), igst_amount=Decimal("5000"))


def test_line_item_sum_must_equal_taxable_amount():
    with pytest.raises(ValidationError, match="Sum of line item amounts"):
        _demo_payload(amount=Decimal("999999"))


def test_gst_breakdown_must_equal_tax_amount():
    with pytest.raises(ValidationError, match=r"CGST \+ SGST \+ IGST"):
        _demo_payload(tax_amount=Decimal("1"))


def test_line_item_amount_must_equal_quantity_times_rate():
    with pytest.raises(ValidationError, match="does not match quantity x rate"):
        InvoiceLineItemCreate(sequence=1, description="Bad row", unit="Nos", quantity=Decimal("2"), rate=Decimal("100"), amount=Decimal("999"))


def test_auto_fill_mode_reads_erp_data_without_creating_anything():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "AUTO")
        before_invoice_count = int(db.scalar(select(func.count(ProjectInvoice.id))) or 0)

        result = invoice_auto_fill(db, project_id=project.id)
        assert result["client"]["name"] == client.client_name
        assert result["client"]["gstin"] == client.gst_number
        assert result["project"]["code"] == project.project_code
        assert result["company"]["name"]
        assert "bank" in result

        after_invoice_count = int(db.scalar(select(func.count(ProjectInvoice.id))) or 0)
        assert after_invoice_count == before_invoice_count
        db.rollback()


def test_manual_mode_billing_snapshot_override_is_captured():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "SNAP")
        payload_in = _demo_payload(
            invoice_number="INV-V2-SNAP",
            billing_snapshot=InvoiceBillingSnapshotOverride(billing_name="Manual Override Pvt Ltd", billing_address="Manually Typed Address"),
        )
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=payload_in)
        db.flush()
        assert invoice.document_snapshot["billing"]["name"] == "Manual Override Pvt Ltd"
        assert invoice.document_snapshot["billing"]["address"] == "Manually Typed Address"
        # Fields not overridden still fall back to the live Client Master, same as Auto Fill.
        assert invoice.document_snapshot["billing"]["gstin"] == client.gst_number

        payload = invoice_document_payload(db, invoice.id)
        assert payload["client"]["name"] == "Manual Override Pvt Ltd"
        assert payload["client"]["data_source"] == "invoice_snapshot"
        db.rollback()


def test_invoice_snapshot_is_immune_to_later_client_master_edits():
    """Core requirement #10: an issued invoice must not silently change when Client Master changes later."""
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "FROZEN")
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=_demo_payload(invoice_number="INV-V2-FROZEN"))
        db.flush()
        original_payload = invoice_document_payload(db, invoice.id)
        assert original_payload["client"]["address"] == "Client Master Address"

        # Client moves offices next month.
        client.address = "New Office Address, Changed Later"
        client.gst_number = "99ZZZZZ9999Z9Z9"
        db.flush()

        reread_payload = invoice_document_payload(db, invoice.id)
        assert reread_payload["client"]["address"] == "Client Master Address"
        assert reread_payload["client"]["gstin"] != "99ZZZZZ9999Z9Z9"
        db.rollback()


def test_plain_invoice_create_without_v2_fields_still_renders_single_line_combined_tax():
    """A draft created without entry_mode/line_items/GST split (today's existing call shape)
    still renders exactly as before: one synthetic line, one combined tax line. A snapshot is
    still captured (every new invoice is protected from future Client Master drift going
    forward); that is a deliberate improvement, not a regression, so ``client.data_source``
    correctly reads "invoice_snapshot" rather than "current_client_master" here. Only invoices
    that already existed in the database before Invoice Generation V2 have a NULL snapshot and
    the true "current_client_master" live-lookup path; that is covered separately by
    test_existing_legacy_and_partially_paid_invoices_remain_readable in
    test_invoice_document_generation.py.
    """
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "LEGACY2")
        legacy_payload = InvoiceDraftCreate(
            invoice_number="INV-V2-LEGACY2", invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 31),
            amount=Decimal("125000"), tax_amount=Decimal("22500"), currency="INR",
        )
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=legacy_payload)
        db.flush()
        assert invoice.document_snapshot is not None
        assert invoice.entry_mode is None
        assert db.scalar(select(func.count(ProjectInvoiceLineItem.id)).where(ProjectInvoiceLineItem.invoice_id == invoice.id)) == 0

        payload = invoice_document_payload(db, invoice.id)
        assert len(payload["line_items"]) == 1
        assert payload["line_items"][0]["source"] == "project_invoice.amount"
        assert len(payload["tax_lines"]) == 1
        assert payload["tax_lines"][0]["label"] == "Tax (18.00%)"
        assert payload["client"]["data_source"] == "invoice_snapshot"
        assert build_invoice_a4_pdf(payload).getvalue().startswith(b"%PDF-")
        db.rollback()


def test_many_line_items_paginate_without_shrinking_and_keep_financial_totals():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "MANYROWS")
        rows = [
            InvoiceLineItemCreate(
                sequence=i, description=f"Survey work package {i}", hsn_sac="998399", unit="Nos",
                quantity=Decimal("1"), rate=Decimal("1000"), amount=Decimal("1000"),
            )
            for i in range(1, 61)
        ]
        payload_in = InvoiceDraftCreate(
            invoice_number="INV-V2-MANYROWS", invoice_date=date(2026, 10, 1), due_date=date(2026, 10, 31),
            amount=Decimal("60000"), tax_amount=Decimal("0"), currency="INR",
            entry_mode="manual", line_items=rows,
        )
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=payload_in)
        db.flush()
        payload = invoice_document_payload(db, invoice.id)
        assert len(payload["line_items"]) == 60
        pdf = build_invoice_a4_pdf(payload)
        reader = PdfReader(pdf)
        assert len(reader.pages) > 1, "60 line items must paginate, not shrink onto one page"
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
        assert "Survey work package 1" in text
        assert "Survey work package 60" in text
        assert "Authorised Signatory" in text
        db.rollback()


def test_repeated_document_generation_creates_no_duplicate_invoice_or_line_items():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "IDEMP")
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=_demo_payload(invoice_number="INV-V2-IDEMP"))
        db.flush()
        before_invoices = int(db.scalar(select(func.count(ProjectInvoice.id))) or 0)
        before_items = int(db.scalar(select(func.count(ProjectInvoiceLineItem.id))) or 0)
        for _ in range(10):
            build_invoice_a4_pdf(invoice_document_payload(db, invoice.id))
        assert int(db.scalar(select(func.count(ProjectInvoice.id))) or 0) == before_invoices
        assert int(db.scalar(select(func.count(ProjectInvoiceLineItem.id))) or 0) == before_items
        db.rollback()


def test_sales_revenue_unaffected_by_v2_line_items_and_gst_split():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "REVCHK")
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=_demo_payload(invoice_number="INV-V2-REVCHK"))
        db.flush()
        before = sales_revenue_overview(db)
        build_invoice_a4_pdf(invoice_document_payload(db, invoice.id))
        after = sales_revenue_overview(db)
        assert before == after
        db.rollback()


def test_auto_fill_endpoint_requires_finance_or_admin_role():
    with SessionLocal() as db:
        finance, client, project = _billable_project(db, "PERM")
        bd = _user(db, "bd.v2.perm@nakshatech.com", "bd")
        db.commit()
        project_id = project.id
        users = {"finance": finance, "bd": bd}

    selected_role = "finance"

    def auth_override():
        with SessionLocal() as db:
            selected = db.scalar(select(User).where(User.email == users[selected_role].email))
            return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    client_api = TestClient(app)
    try:
        selected_role = "finance"
        ok = client_api.get(f"/api/operations/lifecycle/projects/{project_id}/invoices/auto-fill")
        assert ok.status_code == 200, ok.text
        assert ok.json()["project"]["code"]

        selected_role = "bd"
        denied = client_api.get(f"/api/operations/lifecycle/projects/{project_id}/invoices/auto-fill")
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
