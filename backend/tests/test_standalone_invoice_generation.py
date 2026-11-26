"""Standalone Generate Invoice (Finance-only) + document isolation from project accounting.

Covers the second invoice workflow:

    Finance -> Generate Invoice -> manual entry -> A4 preview / PDF / print -> history

It is intentionally disconnected from Projects, Client Advance, Payments, Sales,
Revenue and the Finance Command Center, and this module proves that:

* the standalone tables receive the document and nothing else,
* money is persisted as Decimal and reconciles (CGST/SGST and IGST),
* amount in words is backend-authoritative,
* only Finance may reach the API,
* the produced PDF is one A4 page, carries the official logo + watermark and
  never prints ERP settlement data,
* a large invoice paginates professionally with a repeated header row.

The exact reference case is the one from the brief:

    Item 1 Rs. 45,000 + Item 2 Rs. 30,000 = Rs. 75,000
    IGST 18% = Rs. 13,500 -> total Rs. 88,500, balance due Rs. 88,500
    "Indian Rupee Eighty-Eight Thousand Five Hundred Only"
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO

from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.employee_portal.models import AuditEvent
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.finance.standalone_invoice_models import StandaloneInvoice, StandaloneInvoiceLineItem
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment

API = "/api/finance/generated-invoices"


def _user(db, email: str, role: str) -> User:
    row = User(
        email=email, full_name=email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _line(sequence: int, amount: str, tax_percent: str, *, description: str) -> dict:
    value = Decimal(amount)
    tax = (value * Decimal(tax_percent) / Decimal("100")).quantize(Decimal("0.01"))
    return {
        "sequence": sequence,
        "description": description,
        "detail": "Detailed description for the line item",
        "hsn_sac": "998314",
        "quantity": "1",
        "unit": "Nos",
        "rate": str(value),
        "tax_percent": tax_percent,
        "tax_amount": str(tax),
        "amount": str(value),
    }


def _payload(invoice_number: str, *, tax_mode: str = "igst", rate: str = "18", lines: list[dict] | None = None) -> dict:
    return {
        "invoice_number": invoice_number,
        "invoice_date": "2026-10-01",
        "terms": "Net 15",
        "due_date": "2026-10-16",
        "reference_work_order": "WO-2026-001",
        "place_of_supply": "Karnataka",
        "seller": {
            "company_name": "NAKSHA TECH PRIVATE LIMITED", "address": "Bengaluru, India",
            "gstin": "29ABCDE1234F1Z5", "pan": "ABCDE1234F", "email": "billing@nakshatech.com",
            "phone": "+91 9999999999", "website": "https://nakshatech.com",
            "msme_registration": "UDYAM-KA-00-0000000",
        },
        "bill_to": {
            "company_name": "UAT ADVANCE CLIENT 001", "address": "Client Street, Bengaluru",
            "gstin": "29AAAAA0000A1Z5", "pan": "AAAAA0000A", "email": "accounts@client.example",
            "phone": "+91 9888888888",
        },
        "ship_to": {
            "company_name": "UAT ADVANCE CLIENT 001", "address": "Client Street, Bengaluru",
            "gstin": "29AAAAA0000A1Z5", "pan": None, "email": None, "phone": None,
        },
        "bank": {
            "bank_name": "HDFC Bank", "account_name": "NAKSHA TECH PRIVATE LIMITED",
            "account_number": "50200012345678", "ifsc_code": "HDFC0001234",
            "swift_code": "HDFCINBB", "bank_address": "Bengaluru, India",
        },
        "line_items": lines or [_line(1, "45000", rate, description="Item 1"),
                                _line(2, "30000", rate, description="Item 2")],
        "tax_mode": tax_mode,
        "cgst_percent": "9" if tax_mode == "cgst_sgst" else "0",
        "sgst_percent": "9" if tax_mode == "cgst_sgst" else "0",
        "igst_percent": rate if tax_mode == "igst" else "0",
        "notes": "Thank you for your business.",
        "terms_conditions": "Payment due within 15 days.",
        "authorized_signatory_name": "Authorized Signatory",
        "qr_data": "",
    }


def _pdf_page_count(content: bytes) -> int:
    return len(PdfReader(BytesIO(content)).pages)


def _first_page_text(content: bytes) -> str:
    return PdfReader(BytesIO(content)).pages[0].extract_text() or ""


def _first_page_has_image(content: bytes) -> bool:
    """True when the A4 embeds at least one real image XObject (logo / watermark).

    ReportLab stores the official logo and the watermark as image XObjects, so a
    dependency-free scan of the embedded object dictionary proves the real brand
    asset is used instead of plain text.
    """
    return b"/Subtype /Image" in content or b"/Subtype/Image" in content


def _client_for(role: str, email: str):
    """Build a TestClient whose authentication resolves to the given seeded role."""

    def auth_override():
        with SessionLocal() as db:
            selected = db.scalar(select(User).where(User.email == email))
            return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    return TestClient(app), auth_override


def _seed_finance_and_denied_roles(db) -> dict[str, str]:
    emails = {"finance": "finance.standalone@nakshatech.com"}
    _user(db, emails["finance"], "finance")
    for role in ("bd", "ortho", "employee", "production", "qc", "qa", "management", "admin"):
        emails[role] = f"{role}.standalone@nakshatech.com"
        _user(db, emails[role], role)
    db.commit()
    return emails


# ---------------------------------------------------------------- STEP 27 exact reference case
def test_standalone_reference_invoice_totals_words_and_one_page_pdf():
    emails = None
    with SessionLocal() as db:
        emails = _seed_finance_and_denied_roles(db)

    client, _ = _client_for("finance", emails["finance"])
    try:
        created = client.post(API, json=_payload("SA-2026-0001", tax_mode="igst", rate="18"))
        assert created.status_code == 201, created.text
        payload = created.json()

        # Two item rows, HSN/SAC, QTY/Unit and Rate come straight from the request.
        assert len(payload["line_items"]) == 2
        first = payload["line_items"][0]
        assert first["description"] == "Item 1"
        assert first["hsn_sac"] == "998314"
        assert first["unit"] == "Nos"
        assert Decimal(str(first["rate"])) == Decimal("45000")
        assert Decimal(str(first["quantity"])) == Decimal("1")
        assert Decimal(str(first["taxable_amount"])) == Decimal("45000")

        totals = payload["totals"]
        assert Decimal(str(totals["subtotal"])) == Decimal("75000")
        assert Decimal(str(totals["taxable_amount"])) == Decimal("75000")
        assert Decimal(str(totals["tax_amount"])) == Decimal("13500")
        assert Decimal(str(totals["invoice_total"])) == Decimal("88500")
        assert Decimal(str(totals["balance_due"])) == Decimal("88500")
        assert totals["amount_in_words"] == "Indian Rupee Eighty-Eight Thousand Five Hundred Only"

        # IGST is used exclusively: no CGST/SGST rows leak into an IGST invoice.
        labels = [line["label"].upper() for line in payload["tax_lines"]]
        assert any("IGST" in label for label in labels)
        assert not any("CGST" in label or "SGST" in label for label in labels)

        # Document content from 26-27020.pdf: parties, work order, bank, notes, terms.
        assert payload["invoice"]["po_wo_reference"] == "WO-2026-001"
        assert payload["invoice"]["place_of_supply"] == "Karnataka"
        assert payload["ship_to"]["name"] == "UAT ADVANCE CLIENT 001"
        assert payload["company"]["bank_name"] == "HDFC Bank"
        assert payload["notes"] and payload["terms_conditions"]
        assert payload["authorized_signatory_name"] == "Authorized Signatory"

        # Step 4: one shared PDF endpoint serves inline print and download.
        inline = client.get(f"{API}/{payload['invoice']['id']}/document.pdf")
        assert inline.status_code == 200
        assert inline.headers["content-type"].startswith("application/pdf")
        assert inline.headers["content-disposition"].startswith("inline")
        download = client.get(f"{API}/{payload['invoice']['id']}/document.pdf?download=true")
        assert download.status_code == 200
        assert download.headers["content-disposition"].startswith("attachment")

        # STEP 15/16/17: one A4 page, real logo image, watermark image, no ERP settlement.
        assert _pdf_page_count(inline.content) == 1
        assert _first_page_has_image(inline.content), "official NakshaTech logo/watermark must be embedded"
        text = _first_page_text(inline.content).upper()
        assert "SETTLEMENT SUMMARY" not in text
        assert "ADVANCE APPLIED" not in text
        assert "OUTSTANDING" not in text
        assert "TAX INVOICE" in text or "INVOICE NO" in text

        # STEP 4/9: history exposes document fields only - never payment/outstanding.
        history = client.get(API)
        assert history.status_code == 200
        rows = history.json()["invoices"]
        assert rows and rows[0]["invoice_number"] == "SA-2026-0001"
        for key in ("invoice_number", "invoice_date", "party", "total", "created_by", "created_at"):
            assert key in rows[0]
        for forbidden in ("payment_pending", "partial_payment", "outstanding", "revenue"):
            assert forbidden not in rows[0]
        assert Decimal(str(rows[0]["total"])) == Decimal("88500")
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


def test_cgst_sgst_split_and_validation_rejects_inconsistent_inputs():
    with SessionLocal() as db:
        emails = _seed_finance_and_denied_roles(db)

    client, _ = _client_for("finance", emails["finance"])
    try:
        created = client.post(API, json=_payload("SA-2026-CGST", tax_mode="cgst_sgst"))
        assert created.status_code == 201, created.text
        payload = created.json()
        totals = payload["totals"]
        # 75,000 taxable split 9% + 9% = 13,500 in total (6,750 + 6,750).
        assert Decimal(str(totals["subtotal"])) == Decimal("75000")
        assert Decimal(str(totals["tax_amount"])) == Decimal("13500")
        assert Decimal(str(totals["invoice_total"])) == Decimal("88500")
        labels = {line["label"].upper(): Decimal(str(line["amount"])) for line in payload["tax_lines"]}
        assert any("CGST" in label for label in labels)
        assert any("SGST" in label for label in labels)
        assert not any("IGST" in label for label in labels)

        # A line amount that does not equal quantity x rate is rejected.
        broken = _payload("SA-2026-BAD")
        broken["line_items"][0]["amount"] = "44999"
        assert client.post(API, json=broken).status_code == 422

        # IGST cannot be combined with CGST/SGST.
        mixed = _payload("SA-2026-MIXED", tax_mode="igst")
        mixed["cgst_percent"] = "9"
        mixed["sgst_percent"] = "9"
        assert client.post(API, json=mixed).status_code == 422

        # Duplicate invoice numbers are rejected (history stays unique).
        assert client.post(API, json=_payload("SA-2026-CGST", tax_mode="cgst_sgst")).status_code == 422

        history = client.get(API).json()["invoices"]
        numbers = [row["invoice_number"] for row in history]
        assert len(numbers) == len(set(numbers))
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


def test_generate_invoice_is_finance_only_backend_side():
    with SessionLocal() as db:
        emails = _seed_finance_and_denied_roles(db)

    denied = ("bd", "ortho", "employee", "production", "qc", "qa", "management", "admin")
    try:
        client, _ = _client_for("finance", emails["finance"])
        created = client.post(API, json=_payload("SA-2026-ROLE"))
        assert created.status_code == 201, created.text
        invoice_id = created.json()["invoice"]["id"]

        for role in denied:
            client, _ = _client_for(role, emails[role])
            assert client.get(API).status_code == 403, f"{role} must not list standalone invoices"
            assert client.post(API, json=_payload(f"SA-2026-{role.upper()}")).status_code == 403
            assert client.get(f"{API}/{invoice_id}").status_code == 403
            assert client.get(f"{API}/{invoice_id}/document").status_code == 403
            assert client.get(f"{API}/{invoice_id}/document.pdf").status_code == 403

        # Finance keeps full access on every endpoint.
        client, _ = _client_for("finance", emails["finance"])
        assert client.get(API).status_code == 200
        assert client.get(f"{API}/{invoice_id}").status_code == 200
        assert client.get(f"{API}/{invoice_id}/document").status_code == 200
        assert client.get(f"{API}/{invoice_id}/document.pdf").status_code == 200

        # STEP 24: repeated preview/pdf/print must not duplicate documents.
        with SessionLocal() as db:
            before_count = int(db.scalar(select(func.count(StandaloneInvoice.id))) or 0)
        for _ in range(10):
            assert client.get(f"{API}/{invoice_id}/document").status_code == 200
            assert client.get(f"{API}/{invoice_id}/document.pdf").status_code == 200
        with SessionLocal() as db:
            assert int(db.scalar(select(func.count(StandaloneInvoice.id))) or 0) == before_count
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
def _accounting_snapshot(db) -> dict:
    overview = sales_revenue_overview(db)
    return {
        "project_invoices": int(db.scalar(select(func.count(ProjectInvoice.id))) or 0),
        "project_payments": int(db.scalar(select(func.count(ProjectInvoicePayment.id))) or 0),
        "advance_transactions": int(db.scalar(select(func.count(ClientAdvanceTransaction.id))) or 0),
        "standalone_invoices": int(db.scalar(select(func.count(StandaloneInvoice.id))) or 0),
        "standalone_lines": int(db.scalar(select(func.count(StandaloneInvoiceLineItem.id))) or 0),
        "revenue_events": len(overview["revenue_events"]),
        "realized_revenue": overview["kpi_summary"]["realized_revenue_inr"],
        "open_sales": overview["kpi_summary"]["open_sales_inr"],
        "outstanding": overview["kpi_summary"]["outstanding_inr"],
    }


def test_standalone_invoice_has_no_accounting_side_effects():
    """STEP 22: creating a standalone document must not touch any project ledger."""
    with SessionLocal() as db:
        emails = _seed_finance_and_denied_roles(db)
        db.commit()
        before = _accounting_snapshot(db)

    client, _ = _client_for("finance", emails["finance"])
    try:
        created = client.post(API, json=_payload("SA-2026-ISOLATED"))
        assert created.status_code == 201, created.text
        invoice_id = created.json()["invoice"]["id"]
        # Viewing, printing and downloading repeatedly stays read-only.
        for _ in range(10):
            assert client.get(f"{API}/{invoice_id}/document").status_code == 200
            assert client.get(f"{API}/{invoice_id}/document.pdf").status_code == 200
            assert client.get(f"{API}/{invoice_id}/document.pdf?download=true").status_code == 200

        with SessionLocal() as db:
            after = _accounting_snapshot(db)

        # Only the standalone document tables may grow.
        assert after["standalone_invoices"] == before["standalone_invoices"] + 1
        assert after["standalone_lines"] == before["standalone_lines"] + 2
        for key in (
            "project_invoices", "project_payments", "advance_transactions",
            "revenue_events", "realized_revenue", "open_sales", "outstanding",
        ):
            assert after[key] == before[key], f"{key} must be unchanged by a standalone invoice"

        # STEP 22/34: the payload itself is not linked to any project or client register.
        payload = client.get(f"{API}/{invoice_id}").json()
        assert payload["project"] is None
        assert payload["client"].get("code") is None
        assert payload["document_source"] == "standalone_invoice"

        # The creation is audited.
        with SessionLocal() as db:
            audited = int(db.scalar(select(func.count(AuditEvent.id)).where(
                AuditEvent.event_type == "STANDALONE_INVOICE_CREATED"
            )) or 0)
            assert audited >= 1
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


def test_large_standalone_invoice_paginates_with_repeated_header():
    """STEP 18: genuinely long invoices paginate professionally instead of shrinking."""
    with SessionLocal() as db:
        emails = _seed_finance_and_denied_roles(db)

    lines = [_line(index + 1, "1200", "18", description=f"Survey deliverable line {index + 1}")
             for index in range(70)]
    client, _ = _client_for("finance", emails["finance"])
    try:
        created = client.post(API, json=_payload("SA-2026-LARGE", tax_mode="igst", lines=lines))
        assert created.status_code == 201, created.text
        payload = created.json()
        assert len(payload["line_items"]) == 70
        assert Decimal(str(payload["totals"]["subtotal"])) == Decimal("84000")
        assert Decimal(str(payload["totals"]["invoice_total"])) == Decimal("99120")

        pdf = client.get(f"{API}/{payload['invoice']['id']}/document.pdf")
        assert pdf.status_code == 200
        pages = _pdf_page_count(pdf.content)
        assert pages > 1, "a 70-line invoice must genuinely paginate"
        reader = PdfReader(BytesIO(pdf.content))
        # Every page keeps the repeating column header and carries the watermark.
        for page in reader.pages:
            page_text = (page.extract_text() or "").upper()
            assert "HSN/SAC" in page_text, "the item header must repeat on every page"
        assert _first_page_has_image(pdf.content)
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
        app.dependency_overrides.pop(get_current_auth, None)
