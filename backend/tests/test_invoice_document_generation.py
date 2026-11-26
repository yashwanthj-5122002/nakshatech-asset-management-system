"""A4 invoice output is presentation-only over the existing ProjectInvoice ledger."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.employee_portal.models import AuditEvent
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.invoice_documents import amount_in_words, build_invoice_a4_pdf, invoice_document_payload
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str) -> User:
    row = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="test-only",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _seed_invoice(db, suffix: str, *, amount: str, tax: str, status: str = "PAYMENT_PENDING"):
    finance = _user(db, f"finance.docs.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"DOC-{suffix}",
        client_name=f"Document Client {suffix}",
        contact_person_name="Accounts Contact",
        contact_person_phone="9999999999",
        client_email=f"accounts.{suffix.lower()}@example.com",
        address="Client Master Address",
        country="India",
        gst_number="29ABCDE1234F1Z5",
        source_team="bd",
        source_person_name="BD Owner",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"DOC-P-{suffix}",
        project_name=f"A4 Survey Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        description="Geospatial project services",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 12, 31),
        created_by_id=finance.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=finance.id,
        performing_department_code="lidar",
        status=status,
        commercial_value=Decimal(amount) + Decimal(tax),
        currency="INR",
        created_by_id=finance.id,
        updated_by_id=finance.id,
    ))
    invoice = ProjectInvoice(
        project_id=project.id,
        invoice_number=f"INV-DOC-{suffix}",
        status=status,
        invoice_date=date(2026, 10, 1),
        due_date=date(2026, 10, 31),
        amount=Decimal(amount),
        tax_amount=Decimal(tax),
        tax_percent=(Decimal(tax) / Decimal(amount) * Decimal("100")) if Decimal(tax) else None,
        currency="INR",
        payment_terms="Net 30",
        po_wo_reference="PO-2026-001",
        notes="Thank you for your business.",
        created_by_id=finance.id,
        raised_by_id=finance.id,
    )
    db.add(invoice)
    db.flush()
    return finance, client, project, invoice


def _financial_snapshot(db, invoice_id: int) -> dict:
    invoice = db.get(ProjectInvoice, invoice_id)
    return {
        "invoice_count": int(db.scalar(select(func.count(ProjectInvoice.id))) or 0),
        "payment_count": int(db.scalar(select(func.count(ProjectInvoicePayment.id))) or 0),
        "advance_count": int(db.scalar(select(func.count(ClientAdvanceTransaction.id))) or 0),
        "status": invoice.status,
        "amount": Decimal(invoice.amount),
        "tax": Decimal(invoice.tax_amount),
        "closed_at": invoice.closed_at,
        "raised_at": invoice.raised_at,
    }


def test_taxed_invoice_preview_pdf_and_amount_words_match_project_invoice():
    assert amount_in_words(Decimal("147500.00"), "INR") == "Indian Rupee One Lakh Forty-Seven Thousand Five Hundred Only"
    with SessionLocal() as db:
        _, client, project, invoice = _seed_invoice(db, "TAX", amount="125000", tax="22500")
        db.flush()
        before = _financial_snapshot(db, invoice.id)

        payload = invoice_document_payload(db, invoice.id)
        assert payload["invoice"]["id"] == invoice.id
        assert payload["invoice"]["project_id"] == project.id
        assert payload["client"]["name"] == client.client_name
        assert payload["client"]["address"] == client.address
        assert payload["client"]["gstin"] == client.gst_number
        assert payload["client"]["data_source"] == "current_client_master"
        assert payload["line_items"] == [{
            "sequence": 1,
            "description": project.project_name,
            "detail": project.description,
            "hsn_sac": None,
            "quantity": Decimal("1.00"),
            "unit": "Project",
            "rate": Decimal("125000.00"),
            "taxable_amount": Decimal("125000.00"),
            "source": "project_invoice.amount",
        }]
        assert payload["totals"]["taxable_amount"] == Decimal("125000.00")
        assert payload["totals"]["tax_amount"] == Decimal("22500.00")
        assert payload["totals"]["invoice_total"] == Decimal("147500.00")
        assert payload["totals"]["amount_in_words"] == "Indian Rupee One Lakh Forty-Seven Thousand Five Hundred Only"
        assert payload["tax_lines"][0]["amount"] == Decimal("22500.00")

        pdf = build_invoice_a4_pdf(payload)
        reader = PdfReader(pdf)
        assert len(reader.pages) == 1
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
        assert invoice.invoice_number in text
        assert "INR 147,500.00" in text
        assert payload["totals"]["amount_in_words"] in text

        # Regeneration is pure presentation: no invoice/payment/advance state changes.
        for _ in range(10):
            build_invoice_a4_pdf(invoice_document_payload(db, invoice.id))
        assert _financial_snapshot(db, invoice.id) == before
        db.rollback()


def test_existing_legacy_and_partially_paid_invoices_remain_readable():
    with SessionLocal() as db:
        finance, _, _, legacy = _seed_invoice(db, "LEGACY", amount="10000", tax="0", status="PARTIALLY_PAID")
        # Nullable commercial/FX additions emulate an invoice created before those fields existed.
        legacy.tax_percent = None
        legacy.fx_rate_to_inr = None
        legacy.base_inr = None
        legacy.tax_inr = None
        legacy.total_inr = None
        db.add(ProjectInvoicePayment(
            project_id=legacy.project_id,
            invoice_id=legacy.id,
            payment_reference="LEGACY-PARTIAL",
            payment_date=date(2026, 10, 10),
            amount=Decimal("4000"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        ))
        db.flush()

        payload = invoice_document_payload(db, legacy.id)
        assert payload["settlement"]["cash_received"] == Decimal("4000.00")
        assert payload["settlement"]["total_settled"] == Decimal("4000.00")
        assert payload["settlement"]["outstanding"] == Decimal("6000.00")
        assert payload["settlement"]["status"] == "PARTIALLY_PAID"
        assert build_invoice_a4_pdf(payload).getvalue().startswith(b"%PDF-")
        db.rollback()


def test_controlled_20l_advance_cash_and_revenue_reconcile_before_and_after_documents():
    with SessionLocal() as db:
        finance, _, project, invoice = _seed_invoice(db, "20L", amount="2000000", tax="0", status="INVOICE_CLOSED")
        invoice.closed_by_id = finance.id
        db.add(ClientAdvanceTransaction(
            project_id=project.id,
            client_id=project.client_id,
            sequence=1,
            amount=Decimal("500000"),
            currency="INR",
            amount_inr=Decimal("500000"),
            fx_rate=Decimal("1"),
            payment_date=date(2026, 10, 5),
            payment_mode="bank_transfer",
            reference_number="ADV-5L",
            adjusted_amount_inr=Decimal("500000"),
            adjusted_invoice_id=invoice.id,
            recorded_by_id=finance.id,
        ))
        db.add(ProjectInvoicePayment(
            project_id=project.id,
            invoice_id=invoice.id,
            payment_reference="CASH-15L",
            payment_date=date(2026, 10, 20),
            amount=Decimal("1500000"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        ))
        db.flush()

        revenue_before = sales_revenue_overview(db)
        financial_before = _financial_snapshot(db, invoice.id)
        for _ in range(10):
            payload = invoice_document_payload(db, invoice.id)
            build_invoice_a4_pdf(payload)

        assert payload["totals"]["invoice_total"] == Decimal("2000000.00")
        assert payload["settlement"]["advance_applied"] == Decimal("500000.00")
        assert payload["settlement"]["cash_received"] == Decimal("1500000.00")
        assert payload["settlement"]["total_settled"] == Decimal("2000000.00")
        assert payload["settlement"]["outstanding"] == Decimal("0.00")
        assert _financial_snapshot(db, invoice.id) == financial_before
        assert sales_revenue_overview(db) == revenue_before

        row = next(item for item in revenue_before["projects"] if item["project_id"] == project.id)
        event = next(item for item in revenue_before["revenue_events"] if item["project_id"] == project.id)
        assert row["sales_value_inr"] == 2000000.0
        assert row["outstanding_inr"] == 0.0
        assert row["open_sales_inr"] == 0.0
        assert event["revenue_amount_inr"] == 2000000.0
        db.rollback()


def test_invoice_document_endpoints_enforce_roles_and_only_add_audit_events():
    with SessionLocal() as db:
        finance, _, _, invoice = _seed_invoice(db, "AUTH", amount="10000", tax="1800")
        users = {"finance": finance}
        for role in ("management", "admin", "bd", "ortho", "employee"):
            users[role] = _user(db, f"{role}.docs@nakshatech.com", role)
        db.commit()
        invoice_id = invoice.id
        invoice_number = invoice.invoice_number

    selected_role = "finance"

    def auth_override():
        with SessionLocal() as db:
            selected = db.scalar(select(User).where(User.email == users[selected_role].email))
            return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    client = TestClient(app)
    try:
        with SessionLocal() as db:
            before = _financial_snapshot(db, invoice_id)
            audit_before = int(db.scalar(select(func.count(AuditEvent.id))) or 0)

        for role in ("finance", "management", "admin"):
            selected_role = role
            preview = client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document")
            assert preview.status_code == 200
            assert preview.json()["invoice"]["invoice_number"] == invoice_number
            inline = client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document.pdf")
            assert inline.status_code == 200
            assert inline.headers["content-type"].startswith("application/pdf")
            assert inline.headers["content-disposition"].startswith("inline")
            download = client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document.pdf?download=true")
            assert download.status_code == 200
            assert download.headers["content-disposition"].startswith("attachment")

        for role in ("bd", "ortho", "employee"):
            selected_role = role
            assert client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document").status_code == 403
            assert client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document.pdf").status_code == 403

        # Repeated preview/download/inline-print requests change audit only.
        selected_role = "finance"
        for _ in range(10):
            assert client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document").status_code == 200
            assert client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document.pdf").status_code == 200
            assert client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document.pdf?download=true").status_code == 200

        with SessionLocal() as db:
            assert _financial_snapshot(db, invoice_id) == before
            audit_after = int(db.scalar(select(func.count(AuditEvent.id))) or 0)
            assert audit_after > audit_before
            generated = int(db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.event_type == "INVOICE_GENERATED")) or 0)
            downloaded = int(db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.event_type == "INVOICE_DOWNLOADED")) or 0)
            assert generated >= 20
            assert downloaded >= 10
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
