"""Reference-theme regression checks over PDF output, using no live ERP records."""
from copy import deepcopy
from decimal import Decimal
from io import BytesIO

from pypdf import PdfReader
import pytest
from reportlab.lib.pagesizes import A4

from app.modules.operations.invoice_documents import build_invoice_a4_pdf
from scripts.render_invoice_theme_samples import sample_payload

THEMES = ("blue_topographic", "blue_classic", "green_gold_premium")


@pytest.fixture(autouse=True)
def isolated_application_database():
    """These tests render literal payloads and never connect to any database."""
    yield


def render(theme, mutate=None):
    payload = sample_payload()
    payload.update(theme=theme, theme_explicit=True)
    if mutate:
        mutate(payload)
    return PdfReader(BytesIO(build_invoice_a4_pdf(payload).getvalue()))


@pytest.mark.parametrize("theme", THEMES)
def test_reference_sample_is_one_a4_page_and_financial_text_is_selectable(theme):
    pdf = render(theme)
    assert len(pdf.pages) == 1
    assert float(pdf.pages[0].mediabox.width) == pytest.approx(A4[0], abs=.01)
    assert float(pdf.pages[0].mediabox.height) == pytest.approx(A4[1], abs=.01)
    content = " ".join(pdf.pages[0].extract_text().split())
    assert "DESIGN-REVIEW-2026-001" in content.replace(" ", "")
    for value in ("Topographical Survey", "20,465.00", "12,500.00", "32,965.00", "38,898.70", "Authorised Signatory"):
        assert value in content
    assert "Only Only" not in content
    assert content.count("Only") == 1
    assert content.count("20,465.00") == 2, "the ERP value is printed in both Rate and Amount"
    assert content.count("12,500.00") == 2
    assert "UNSIGNED" in content
    assert pdf.pages[0]["/Resources"].get("/XObject"), "the official logo is embedded"


@pytest.mark.parametrize("theme", THEMES)
def test_long_invoice_repeats_context_and_table_and_finishes_with_totals(theme):
    def many(payload):
        item = payload["line_items"][0]
        payload["line_items"] = [dict(item, sequence=i, description=f"Measured survey package {i}", taxable_amount=Decimal("20465")) for i in range(1, 61)]
        payload["settlement"] = {"outstanding": "DO NOT PRINT", "advance_applied": "DO NOT PRINT"}
    pdf = render(theme, many)
    assert len(pdf.pages) > 1
    contents = [" ".join(page.extract_text().split()) for page in pdf.pages]
    for page in contents:
        assert "DESIGN-REVIEW-2026-001" in page.replace(" ", "")
        assert "Items & Description" in page
        assert "DO NOT PRINT" not in page
    assert "Measured survey package 60" in contents[-1]
    assert "INVOICE VALUE" in contents[-1]
    assert "Authorised Signatory" in contents[-1]
    assert all("INVOICE VALUE" not in page for page in contents[:-1])


@pytest.mark.parametrize("theme", THEMES)
def test_long_dynamic_fields_and_literal_markup_survive(theme):
    def longer(payload):
        payload["client"].update(address="Long Customer Address & Building <West>\n"*4, email="accounts.payable.long-address@customer.example", phone="+91 99999 12345")
        payload["line_items"][0]["detail"] = "Detailed mapping, processing & delivery across multiple locations with a three line description and quality assurance checks."
        payload["totals"]["amount_in_words"] += " Only only."
    pdf = render(theme, longer)
    content = " ".join(" ".join(p.extract_text() for p in pdf.pages).split())
    for value in ("Building <West>", "accounts.payable.long-address@customer.example", "quality assurance checks", "20,465.00"):
        assert value in content
    assert content.count("Only") == 1


def test_renderer_is_read_only_and_uses_no_reference_sample_data():
    payload = sample_payload()
    payload.update(theme="blue_topographic", theme_explicit=True)
    original = deepcopy(payload)
    build_invoice_a4_pdf(payload)
    assert payload == original
    pdf = render("blue_topographic")
    content = pdf.pages[0].extract_text()
    for value in ("NAK/026-27/002", "29/09/2026", "7936279626Jkwefg", "AA73FH39"):
        assert value not in content


@pytest.mark.parametrize("theme", THEMES)
def test_oversized_description_splits_without_losing_content(theme):
    def oversized(payload):
        payload["line_items"] = payload["line_items"][:1]
        payload["line_items"][0]["detail"] = "Measured survey deliverable with quality assurance. "*140 + "END-OF-DESCRIPTION"
    pdf = render(theme, oversized)
    assert 1 < len(pdf.pages) < 12
    contents = [p.extract_text() for p in pdf.pages]
    assert "END-OF-DESCRIPTION" in " ".join(contents)
    assert "INVOICE VALUE" in contents[-1]
    assert "Authorised Signatory" in contents[-1]
    assert all("Items & Description" in page for page in contents)


def test_long_legal_text_flows_to_continuation_pages():
    def legal(payload):
        payload["terms_conditions"] = "Dynamic ERP contract clause with agreed commercial terms.\n"*150 + "FINAL-ERP-CLAUSE"
    pdf = render("green_gold_premium", legal)
    assert 1 < len(pdf.pages) < 12
    assert "FINAL-ERP-CLAUSE" in pdf.pages[-1].extract_text()


def test_signature_assets_are_used_only_in_signed_state(tmp_path):
    from PIL import Image
    paths = []
    for index, color in enumerate(("red", "blue")):
        path = tmp_path / f"test-asset-{index}.png"
        Image.new("RGB", (120 if index == 0 else 30, 30), color).save(path)
        paths.append(str(path))
    def state(signed):
        def update(payload):
            payload["signature"] = dict(signed=signed, signature_image=paths[0], stamp_image=paths[1], signed_by_name="ERP Approved Signer")
        return update
    unsigned = render("green_gold_premium", state(False)).pages[0]
    signed = render("green_gold_premium", state(True)).pages[0]
    assert "ERP Approved Signer" not in unsigned.extract_text()
    assert "ERP Approved Signer" in signed.extract_text()
    assert "UNSIGNED" not in signed.extract_text()
    assert len(signed["/Resources"]["/XObject"]) == len(unsigned["/Resources"]["/XObject"]) + 2
