"""Company-address fallback and shared theme headers, without database writes."""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

from pypdf import PdfReader
import pytest

from app.modules.operations import invoice_documents as documents


@pytest.fixture(autouse=True)
def isolated_application_database():
    """The document adapter is exercised against a read-only repository stub."""
    yield


def document_payload(monkeypatch, snapshot):
    invoice = documents.ProjectInvoice(
        id=1, project_id=1, invoice_number="ADDRESS-REVIEW-001",
        invoice_date=date(2026, 10, 17), created_at=datetime(2026, 10, 17, 10, 30),
        amount=Decimal("20465"), tax_amount=Decimal("0"), currency="INR",
        signed=False, theme="blue_classic", document_snapshot=snapshot,
    )
    project = documents.FinanceProject(
        id=1, project_code="ADDRESS-PROJECT", project_name="Survey Services",
        client_name="ERP Client", description="Survey deliverables", client=None,
    )
    db = SimpleNamespace(
        get=lambda model, identifier: invoice,
        scalar=lambda query: project,
        scalars=lambda query: [],
    )
    monkeypatch.setattr(documents, "_invoice_payload", lambda db, row: {
        "id": row.id, "invoice_number": row.invoice_number, "invoice_date": row.invoice_date.isoformat(),
    })
    monkeypatch.setattr(documents, "_settlement_payload", lambda db, row: {})
    return documents.invoice_document_payload(db, invoice.id)


@pytest.mark.parametrize("configured", ["", " \t ", "  Configured Company Address  "])
def test_configured_address_takes_precedence_over_legal_default(monkeypatch, configured):
    monkeypatch.setattr(documents.settings, "invoice_company_address", configured)
    assert documents._configured_company()["address"] == (configured.strip() or documents.DEFAULT_COMPANY_ADDRESS)


@pytest.mark.parametrize("address", [None, "", "Historical Company Address"])
def test_snapshot_fallback_preserves_historical_data(monkeypatch, address):
    monkeypatch.setattr(documents.settings, "invoice_company_address", "Configured Company Address")
    snapshot = {
        "company": {"name": "NAKSHA TECH PRIVATE LIMITED", "address": address, "phone": "ERP PHONE", "pan": "ERP PAN"},
        "billing": {"name": "ERP Client", "address": "Saved Billing Address"},
    }
    original = deepcopy(snapshot)
    payload = document_payload(monkeypatch, snapshot)
    assert payload["company"]["address"] == (address or "Configured Company Address")
    assert payload["company"]["phone"] == "ERP PHONE"
    assert payload["company"]["pan"] == "ERP PAN"
    assert payload["client"]["address"] == "Saved Billing Address"
    assert snapshot == original


def test_snapshot_without_address_key_uses_configured_address(monkeypatch):
    monkeypatch.setattr(documents.settings, "invoice_company_address", "Configured Company Address")
    snapshot = {"company": {"name": "NAKSHA TECH PRIVATE LIMITED"}}
    original = deepcopy(snapshot)
    assert document_payload(monkeypatch, snapshot)["company"]["address"] == "Configured Company Address"
    assert snapshot == original


def test_legacy_invoice_without_snapshot_uses_legal_default(monkeypatch):
    monkeypatch.setattr(documents.settings, "invoice_company_address", "")
    assert document_payload(monkeypatch, None)["company"]["address"] == documents.DEFAULT_COMPANY_ADDRESS


@pytest.mark.parametrize("theme", documents.INVOICE_THEME_KEYS)
def test_legal_address_prints_below_company_name_in_all_three_headers(monkeypatch, theme):
    monkeypatch.setattr(documents.settings, "invoice_company_address", "")
    snapshot = {"company": {"name": "NAKSHA TECH PRIVATE LIMITED", "address": None}, "billing": {"name": "ERP Client"}}
    payload = document_payload(monkeypatch, snapshot)
    payload.update(theme=theme, theme_explicit=True)
    pdf = PdfReader(BytesIO(documents.build_invoice_a4_pdf(payload).getvalue()))
    assert len(pdf.pages) == 1
    content = " ".join(pdf.pages[0].extract_text().split())
    assert documents.DEFAULT_COMPANY_ADDRESS in content
    assert content.index("NAKSHA TECH PRIVATE LIMITED") < content.index(documents.DEFAULT_COMPANY_ADDRESS) < content.index("INVOICE No")
    assert content.count("20,465.00") >= 2
    assert content.count("Only") == 1
    assert snapshot["company"]["address"] is None
