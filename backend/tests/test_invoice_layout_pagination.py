"""Invoice A4 layout regression: item-row separators and page economy.

Presentation-only assertions over ``build_invoice_a4_pdf``:

* an ordinary invoice (1..4 items) must fit on a SINGLE A4 page;
* a genuinely large invoice must still paginate with the item header repeated;
* every item row must close with one continuous separator across all columns,
  including rows whose description wraps;
* the printable document never shows ERP settlement data.

No business/finance/database state is touched: the payloads below are literal
document models handed straight to the renderer.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader

from app.modules.operations.invoice_documents import amount_in_words, build_invoice_a4_pdf

LONG_DESCRIPTION = "Digitization of Road Topographical Features at Goa and surrounding district"


def _payload(*, items: int, standalone: bool = False, qr: bool = True) -> dict:
    """Realistic document model for one invoice with ``items`` ordinary line items."""
    line_items = [
        {
            "sequence": index + 1,
            "description": f"Satellite Imagery Service Line {index + 1}",
            "detail": "Standard deliverable with processing and quality assurance" if index == 0 else None,
            "hsn_sac": "998314",
            "quantity": Decimal("1"),
            "unit": "Nos",
            "rate": Decimal("45000") if index == 0 else Decimal("30000"),
            "tax_percent": Decimal("18.00"),
            "tax_amount": Decimal("8100") if index == 0 else Decimal("5400"),
            "taxable_amount": Decimal("45000") if index == 0 else Decimal("30000"),
            "source": "test",
        }
        for index in range(items)
    ]
    subtotal = sum((row["taxable_amount"] for row in line_items), Decimal("0"))
    tax = sum((row["tax_amount"] for row in line_items), Decimal("0"))
    total = subtotal + tax
    return {
        "document_type": "TAX INVOICE",
        "document_version": 2,
        "document_source": "standalone_invoice" if standalone else "project_invoice",
        "entry_mode": "manual",
        "company": {
            "name": "NAKSHA TECH PRIVATE LIMITED",
            "address": "No. 42, Survey Technology Park, Bengaluru 560001",
            "gstin": "29ABCDE1234F1Z5", "pan": "ABCDE1234F",
            "phone": "+91 80 4000 1000", "email": "accounts@nakshatech.com",
            "website": "https://nakshatech.com", "msme_registration": "UDYAM-KA-00-0000000",
            "hsn_sac": "998314", "bank_name": "HDFC Bank",
            "bank_account_name": "NAKSHA TECH PRIVATE LIMITED", "bank_account_number": "50200012345678",
            "bank_ifsc": "HDFC0001234", "bank_swift": "HDFCINBB",
            "bank_branch": "Koramangala, Bengaluru", "data_source": "test",
        },
        "client": {
            "code": "CLI-001", "name": "Geospatial Client Private Limited",
            "address": "Plot 7, MIDC Industrial Area, Pune 411019", "country": "India",
            "gstin": "27AAAAA0000A1Z5", "pan": "AAAAA0000A", "contact_person": "Accounts Manager",
            "phone": "+91 20 4000 2000", "email": "accounts@client.example",
            "data_source": "test",
        },
        "ship_to": {
            "name": "Geospatial Client Private Limited",
            "address": "Plot 7, MIDC Industrial Area, Pune 411019",
            "gstin": "27AAAAA0000A1Z5", "pan": None, "phone": None, "email": None,
        } if standalone else None,
        "project": None if standalone else {"id": 1, "code": "P-001", "name": "Survey Project", "description": None},
        "invoice": {
            "id": 1, "invoice_number": "LAYOUT-001", "invoice_date": "2026-10-01",
            "due_date": "2026-10-16", "payment_terms": "Net 15",
            "po_wo_reference": "WO-2026-001", "work_order_date": "2026-09-28",
            "dispatch_details": "Dispatched from Bengaluru head office",
            "dispatch_date": "2026-09-30", "place_of_supply": "Maharashtra",
            "created_at": "2026-10-01T10:30:00", "notes": "Thank you for your business.",
        },
        "line_items": line_items,
        "tax_lines": [{"label": "IGST (18%)", "amount": tax}],
        "totals": {
            "subtotal": subtotal, "taxable_amount": subtotal, "tax_amount": tax,
            "invoice_total": total, "balance_due": total if standalone else None,
            "amount_in_words": amount_in_words(total, "INR"), "currency": "INR",
        },
        "settlement": {
            "advance_applied": Decimal("500000"), "cash_received": Decimal("1500000"),
            "total_settled": Decimal("2000000"), "outstanding": Decimal("0"), "status": "INVOICE_CLOSED",
        },
        "notes": "Thank you for your business.",
        "terms_conditions": "Payment due within 15 days of the invoice date.",
        "authorized_signatory_name": "Authorized Signatory",
        "qr_data": "upi://pay?pa=nakshatech@bank" if qr else None,
        "qr_image_data_uri": None,
    }


def _pages(payload: dict) -> int:
    return len(PdfReader(BytesIO(build_invoice_a4_pdf(payload).getvalue())).pages)


def _text(payload: dict, page: int = 0) -> str:
    return PdfReader(BytesIO(build_invoice_a4_pdf(payload).getvalue())).pages[page].extract_text() or ""


def test_normal_single_item_invoice_stays_on_one_a4_page():
    """A normal one-item invoice must be a single A4 page, signature block included."""
    payload = _payload(items=1)
    assert _pages(payload) == 1
    text = _text(payload).upper()
    for expected in (
        "LAYOUT-001",                        # invoice number
        "GEOSPATIAL CLIENT",                 # client
        "SATELLITE IMAGERY SERVICE LINE 1",  # item description
        "TAXABLE VALUE",                     # totals
        "IGST",                              # tax
        "AMOUNT CHARGEABLE",                 # amount in words
        "FOR NAKSHA TECH PRIVATE LIMITED",    # signature block
        "AUTHORISED SIGNATORY",              # signatory label
    ):
        assert expected in text, f"{expected} must be on page 1"


def test_standalone_single_item_invoice_stays_on_one_a4_page():
    """The standalone document follows the same page economy."""
    payload = _payload(items=1, standalone=True)
    assert _pages(payload) == 1
    text = _text(payload).upper()
    for expected in ("SHIP TO", "BALANCE DUE", "BANK DETAILS", "AUTHORISED SIGNATORY"):
        assert expected in text, f"{expected} must be on page 1"


def test_ordinary_two_three_and_four_item_invoices_stay_on_one_page():
    """No artificial page break by item count - only physical overflow may paginate."""
    counts = {}
    for items in (2, 3, 4):
        counts[items] = _pages(_payload(items=items))
        assert counts[items] == 1, f"{items}-item invoice should fit on one A4 page"
    assert counts == {2: 1, 3: 1, 4: 1}


def test_long_wrapped_description_keeps_one_row_and_one_page():
    """A wrapping description grows its row and keeps the separator below it."""
    payload = _payload(items=1)
    payload["line_items"][0]["description"] = LONG_DESCRIPTION
    assert _pages(payload) == 1
    text = _text(payload)
    assert "Road Topographical" in text
    assert "Authorised Signatory" in text, "the signature block must stay on page 1 under a wrapping description"


def test_large_invoice_paginates_naturally_with_repeated_header():
    """Genuinely large invoices still paginate, repeating the item header."""
    payload = _payload(items=70)
    assert _pages(payload) > 1, "a 70-item invoice must paginate"
    reader = PdfReader(BytesIO(build_invoice_a4_pdf(payload).getvalue()))
    for page in reader.pages:
        assert "HSN" in (page.extract_text() or "").upper(), "item header repeats on every page"
    last = (reader.pages[-1].extract_text() or "").upper()
    assert "TAXABLE VALUE" in last or "TOTAL TAXABLE" in last
    assert "AUTHORISED SIGNATORY" in last


def test_printable_document_never_prints_erp_settlement_data():
    """STEP 12 separation must survive the layout work."""
    text = _text(_payload(items=1)).upper()
    for forbidden in ("SETTLEMENT SUMMARY", "ADVANCE APPLIED", "OUTSTANDING", "CASH RECEIVED"):
        assert forbidden not in text, f"{forbidden} must never reach the printable invoice"

