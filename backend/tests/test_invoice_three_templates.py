"""Three A4 presentation formats must preserve every existing legal/tax amount."""
from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from app.modules.operations.invoice_documents import build_invoice_a4_pdf
from test_invoice_layout_pagination import _payload

TEMPLATES = ("green_gold", "modern_teal", "geospatial_blue")


@pytest.mark.parametrize("standalone", [True, False])
@pytest.mark.parametrize("template", TEMPLATES)
def test_template_pdf_preserves_all_existing_invoice_fields(template: str, standalone: bool):
    payload = _payload(items=2, standalone=standalone)
    original_values = repr(payload)
    result = build_invoice_a4_pdf(payload, template=template)
    assert repr(payload) == original_values, "Rendering must never mutate the financial data"
    assert result.getvalue().startswith(b"%PDF")
    pages = PdfReader(BytesIO(result.getvalue())).pages
    assert len(pages) == 1
    text = " ".join((page.extract_text() or "") for page in pages).upper()
    for expected in (
        "TAX INVOICE", "LAYOUT-001", "2026", "NAKSHA TECH PRIVATE LIMITED",
        "GEOSPATIAL CLIENT", "GSTIN", "29ABCDE1234F1Z5", "PAN", "HSN",
        "998314", "SATELLITE IMAGERY SERVICE LINE 1", "SATELLITE IMAGERY SERVICE LINE 2",
        "IGST", "75,000.00", "13,500.00", "88,500.00", "AMOUNT CHARGEABLE",
        "BANK DETAILS", "AUTHORISE(D) SIGNATORY",
    ):
        if expected == "AUTHORISE(D) SIGNATORY":
            assert "AUTHORISED SIGNATORY" in text or "AUTHORIZED SIGNATORY" in text
        else:
            assert expected in text, f"{expected} missing in {template}"
    assert "SETTLEMENT SUMMARY" not in text
    assert "ADVANCE APPLIED" not in text


def test_unknown_template_rejected_without_modifying_data():
    payload = _payload(items=1)
    with pytest.raises(ValueError, match="Unsupported invoice template"):
        build_invoice_a4_pdf(payload, template="custom_or_untrusted")
