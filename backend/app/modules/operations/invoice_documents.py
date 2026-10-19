"""Read-only A4 presentation for the existing ProjectInvoice source of truth.

This module deliberately owns no invoice state. Both the JSON preview and PDF
renderer consume the same payload assembled from ProjectInvoice, Client Master
and Project Master. Payment/advance/dashboard values deliberately stay outside
the customer-facing tax-invoice render model.

Invoice Generation V2 (additive)
---------------------------------
A V2 invoice may carry 1..N ``ProjectInvoiceLineItem`` rows and an explicit
CGST/SGST/IGST breakdown (``ProjectInvoice.cgst_amount`` etc.) plus a frozen
``document_snapshot`` of the billing/company/bank details captured when the
invoice was created. A legacy invoice (raised before V2) has none of these:
it keeps rendering exactly as before — one synthetic line built from
``ProjectInvoice.amount``, one combined "Tax (X%)" line, and live Client
Master / app-configuration data. Nothing about legacy rendering changes.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User
from app.modules.finance.models import FinanceProject
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoiceLineItem, ProjectInvoicePayment
from app.modules.operations.lifecycle_service import _invoice_payload

MONEY = Decimal("0.01")
DEFAULT_COMPANY_ADDRESS = (
    "R.K Chambers, 4th Floor, 5th Main, "
    "Chamarajpet, Bengaluru, Karnataka, India 560018"
)

_ONES = (
    "Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
)
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")


def _money(value: object | None) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(MONEY, rounding=ROUND_HALF_UP)


def _words_below_hundred(value: int) -> str:
    if value < 20:
        return _ONES[value]
    tens, ones = divmod(value, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _integer_words(value: int) -> str:
    """English words using the Indian lakh/crore grouping used by Finance."""
    if value < 100:
        return _words_below_hundred(value)
    if value < 1_000:
        hundreds, rest = divmod(value, 100)
        return f"{_ONES[hundreds]} Hundred" + (f" {_integer_words(rest)}" if rest else "")
    if value < 100_000:
        thousands, rest = divmod(value, 1_000)
        return f"{_integer_words(thousands)} Thousand" + (f" {_integer_words(rest)}" if rest else "")
    if value < 10_000_000:
        lakhs, rest = divmod(value, 100_000)
        return f"{_integer_words(lakhs)} Lakh" + (f" {_integer_words(rest)}" if rest else "")
    crores, rest = divmod(value, 10_000_000)
    return f"{_integer_words(crores)} Crore" + (f" {_integer_words(rest)}" if rest else "")


def amount_in_words(value: object, currency: str = "INR") -> str:
    amount = _money(value)
    negative = amount < 0
    amount = abs(amount)
    whole = int(amount)
    fraction = int((amount - Decimal(whole)) * 100)
    code = (currency or "INR").upper()
    major, minor = {
        "INR": ("Indian Rupee", "Paise"),
        "USD": ("US Dollar", "Cent"),
        "EUR": ("Euro", "Cent"),
        "GBP": ("Pound", "Pence"),
        "AED": ("UAE Dirham", "Fils"),
    }.get(code, (code, "Subunit"))
    result = f"{major} {_integer_words(whole)}"
    if fraction:
        result += f" and {_integer_words(fraction)} {minor}"
    return ("Minus " if negative else "") + result + " Only"


def _configured_company() -> dict:
    configured_address = settings.invoice_company_address.strip()
    return {
        "name": settings.invoice_company_name.strip() or "NakshaTech",
        "address": configured_address or DEFAULT_COMPANY_ADDRESS,
        "gstin": settings.invoice_company_gstin.strip() or None,
        "pan": settings.invoice_company_pan.strip() or None,
        "phone": settings.invoice_company_phone.strip() or None,
        "email": settings.invoice_company_email.strip() or None,
        "website": settings.invoice_company_website.strip() or None,
        "hsn_sac": settings.invoice_company_hsn_sac.strip() or None,
        "bank_name": settings.invoice_bank_name.strip() or None,
        "bank_account_name": settings.invoice_bank_account_name.strip() or None,
        "bank_account_number": settings.invoice_bank_account_number.strip() or None,
        "bank_ifsc": settings.invoice_bank_ifsc.strip() or None,
        "bank_swift": settings.invoice_bank_swift.strip() or None,
        "bank_branch": settings.invoice_bank_branch.strip() or None,
        "data_source": "application_configuration",
    }


def _resolve_logo_path() -> Path | None:
    """Locate the official NakshaTech brand mark, or None (text-only header is fine).

    Checks an explicit override first, then the existing frontend asset that ships with
    this monorepo (``frontend/public/nakshatech-logo.png``). Never fetches or invents one.
    """
    candidates: list[Path] = []
    if settings.invoice_logo_path.strip():
        candidates.append(Path(settings.invoice_logo_path.strip()))
    # backend/app/modules/operations/invoice_documents.py -> repo root is 4 parents up.
    repo_root = Path(__file__).resolve().parents[4]
    candidates.append(repo_root / "frontend" / "public" / "nakshatech-logo.png")
    # Docker mounts the same official asset here because the backend container
    # intentionally has no access to the frontend bind mount.
    candidates.append(Path(__file__).resolve().parents[2] / "nakshatech-logo.png")
    for path in candidates:
        try:
            if path.is_file():
                return path
        except OSError:
            continue
    return None


def _line_items_payload(db: Session, invoice: ProjectInvoice, project: FinanceProject) -> list[dict]:
    rows = list(db.scalars(
        select(ProjectInvoiceLineItem)
        .where(ProjectInvoiceLineItem.invoice_id == invoice.id)
        .order_by(ProjectInvoiceLineItem.sequence.asc())
    ))
    if rows:
        return [{
            "sequence": row.sequence,
            "description": row.description,
            "detail": None,
            "hsn_sac": row.hsn_sac,
            "quantity": Decimal(row.quantity).quantize(Decimal("0.001")),
            "unit": row.unit,
            "rate": _money(row.rate),
            "taxable_amount": _money(row.amount),
            "source": "project_invoice_line_item",
        } for row in rows]
    # Legacy / no line items entered: one synthetic line from the authoritative amount,
    # exactly as every invoice rendered before Invoice Generation V2.
    taxable = _money(invoice.amount)
    return [{
        "sequence": 1,
        "description": project.project_name,
        "detail": project.description or invoice.notes,
        "hsn_sac": None,
        "quantity": Decimal("1.00"),
        "unit": "Project",
        "rate": taxable,
        "taxable_amount": taxable,
        "source": "project_invoice.amount",
    }]


def _tax_lines_payload(invoice: ProjectInvoice) -> list[dict]:
    cgst = invoice.cgst_amount
    sgst = invoice.sgst_amount
    igst = invoice.igst_amount
    has_split = any(value is not None for value in (cgst, sgst, igst))
    if has_split:
        lines = []
        if cgst or invoice.cgst_percent is not None:
            lines.append({
                "label": f"CGST @ {_money(invoice.cgst_percent):f}%" if invoice.cgst_percent is not None else "CGST",
                "rate_percent": invoice.cgst_percent, "amount": _money(cgst), "source": "project_invoice.cgst_amount",
            })
        if sgst or invoice.sgst_percent is not None:
            lines.append({
                "label": f"SGST @ {_money(invoice.sgst_percent):f}%" if invoice.sgst_percent is not None else "SGST",
                "rate_percent": invoice.sgst_percent, "amount": _money(sgst), "source": "project_invoice.sgst_amount",
            })
        if igst or invoice.igst_percent is not None:
            lines.append({
                "label": f"IGST @ {_money(invoice.igst_percent):f}%" if invoice.igst_percent is not None else "IGST",
                "rate_percent": invoice.igst_percent, "amount": _money(igst), "source": "project_invoice.igst_amount",
            })
        return lines
    # Legacy / no explicit GST split: one combined tax line, exactly as before.
    tax = _money(invoice.tax_amount)
    if not tax and invoice.tax_percent is None:
        return []
    tax_label = "Tax"
    if invoice.tax_percent is not None:
        tax_label = f"Tax ({_money(invoice.tax_percent):f}%)"
    return [{
        "label": tax_label, "rate_percent": invoice.tax_percent if invoice.tax_percent is not None else None,
        "amount": tax, "source": "project_invoice.tax_amount",
    }]


def _settlement_payload(db: Session, invoice: ProjectInvoice) -> dict:
    """Internal settlement snapshot for ERP consumers (never printed on the tax invoice).

    Reads the existing ledgers only: the client-advance rows already adjusted
    against this invoice, plus the recorded invoice payments. Nothing is written,
    recalculated or duplicated here.
    """
    # Lazy import: the client-advance ledger is a Finance model and is optional for
    # the read-only document adapter.
    from app.modules.finance.advance import ClientAdvanceTransaction

    advance_applied = Decimal(db.scalar(
        select(func.coalesce(func.sum(ClientAdvanceTransaction.adjusted_amount_inr), 0)).where(
            ClientAdvanceTransaction.adjusted_invoice_id == invoice.id,
            ClientAdvanceTransaction.is_reversed.is_(False),
        )
    ) or 0)

    cash_rows = db.scalars(
        select(ProjectInvoicePayment).where(ProjectInvoicePayment.invoice_id == invoice.id)
    ).all()
    cash_received = Decimal("0")
    for row in cash_rows:
        if row.inr_equivalent is not None:
            cash_received += Decimal(row.inr_equivalent)
        elif (row.payment_currency or invoice.currency or "INR").upper() == "INR":
            cash_received += Decimal(row.amount)
        else:
            cash_received += Decimal(row.amount)

    cash_received = _money(cash_received)
    advance_applied = _money(advance_applied)
    total_settled = _money(advance_applied + cash_received)
    invoice_total = _money(Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0))
    return {
        "advance_applied": advance_applied,
        "cash_received": cash_received,
        "total_settled": total_settled,
        "outstanding": _money(max(invoice_total - total_settled, Decimal("0"))),
        "status": invoice.status,
    }


# ===========================================================================================
# V8.7 invoice presentation themes + authorised signatory
#
# THREE designs, ONE normalized payload (``invoice_document_payload``). Tax, amount-in-words
# and every financial figure stay computed exactly once, upstream of rendering.
# ===========================================================================================

INVOICE_THEME_KEYS: tuple[str, ...] = ("blue_classic", "blue_topographic", "green_gold_premium")

INVOICE_THEME_LABELS: dict[str, str] = {
    "blue_classic": "Theme 1 — Blue Classic",
    "blue_topographic": "Theme 2 — Blue Topographic",
    "green_gold_premium": "Theme 3 — Green Gold Premium",
}

DEFAULT_INVOICE_THEME = "blue_classic"


def normalize_invoice_theme(value: str | None) -> str:
    """Validate/normalize a theme key; unknown/NULL falls back to the classic design."""
    key = (value or "").strip().lower()
    return key if key in INVOICE_THEME_KEYS else DEFAULT_INVOICE_THEME


def invoice_theme(invoice: object) -> str:
    return normalize_invoice_theme(getattr(invoice, "theme", None))


def _configured_signature() -> dict:
    """Authorised-signatory configuration (name + optional signature/stamp image paths).

    Read from application settings so nothing is hard-coded; if the company has not
    configured an asset the value is None and the template simply leaves the area unsigned.
    """
    from app.core.config import settings

    def _path(attr: str) -> str | None:
        raw = getattr(settings, attr, None)
        return str(raw).strip() or None if raw else None

    return {
        "name": _path("invoice_signatory_name"),
        "signature_image": _path("invoice_signature_image_path"),
        "stamp_image": _path("invoice_stamp_image_path"),
    }


def invoice_document_payload(db: Session, invoice_id: int) -> dict:
    """Build the canonical preview/PDF payload without changing financial state."""
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    project = db.scalar(
        select(FinanceProject).where(FinanceProject.id == invoice.project_id)
    )
    if project is None:
        raise ValueError("Invoice project not found")

    # Reuse the existing lifecycle payload for authoritative invoice fields. The
    # customer-facing document adapter intentionally excludes its settlement data.
    lifecycle = _invoice_payload(db, invoice)
    client = project.client
    signatory = _configured_signature()
    signed_by = db.get(User, invoice.signed_by_id) if invoice.signed_by_id else None
    signed_by_name = (
        signed_by.full_name if signed_by is not None
        else (signatory.get("name") if invoice.signed else None)
    )
    taxable = _money(invoice.amount)
    tax = _money(invoice.tax_amount)
    total = _money(taxable + tax)

    configured_company = _configured_company()
    snapshot = invoice.document_snapshot
    if snapshot:
        # Frozen at invoice-creation time: a later Client Master or company-configuration
        # edit never replaces saved values. A missing legal company address alone
        # falls back for presentation; the stored snapshot is never modified.
        billing = snapshot.get("billing") or {}
        company_snap = snapshot.get("company") or {}
        bank_snap = snapshot.get("bank") or {}
        company_payload = {
            "name": company_snap.get("name") or "NakshaTech",
            "address": company_snap.get("address") or configured_company.get("address"),
            "gstin": company_snap.get("gstin"),
            "pan": company_snap.get("pan"),
            "phone": company_snap.get("phone"),
            "email": company_snap.get("email"),
            "website": company_snap.get("website"),
            "hsn_sac": company_snap.get("hsn_sac"),
            "bank_name": bank_snap.get("bank_name"),
            "bank_account_name": bank_snap.get("account_name"),
            "bank_account_number": bank_snap.get("account_number"),
            "bank_ifsc": bank_snap.get("ifsc"),
            "bank_swift": bank_snap.get("swift"),
            "bank_branch": bank_snap.get("branch"),
            "data_source": "invoice_snapshot",
        }
        client_payload = {
            "code": client.client_code if client else None,
            "name": billing.get("name") or (client.client_name if client else project.client_name) or "Client not recorded",
            "address": billing.get("address"),
            "country": client.country if client else None,
            "gstin": billing.get("gstin"),
            "pan": billing.get("pan"),
            "contact_person": client.contact_person_name if client else None,
            "phone": billing.get("phone"),
            "email": billing.get("email"),
            "data_source": "invoice_snapshot",
        }
    else:
        company_payload = configured_company
        client_payload = {
            "code": client.client_code if client else None,
            "name": (client.client_name if client else project.client_name) or "Client not recorded",
            "address": client.address if client else None,
            "country": client.country if client else None,
            "gstin": client.gst_number if client else None,
            "pan": None,
            "contact_person": client.contact_person_name if client else None,
            "phone": (client.contact_person_phone or client.primary_phone) if client else None,
            "email": (client.client_email or (client.master_profile.organization_email if client.master_profile else None)) if client else None,
            # ProjectInvoice has no historical client snapshot in the current schema.
            # Existing and new documents therefore use the same explicit master-data rule.
            "data_source": "current_client_master",
        }

    return {
        "document_type": "TAX INVOICE" if tax > 0 else "INVOICE",
        "document_version": 2,
        "document_source": "project_invoice",
        "entry_mode": invoice.entry_mode,
        "company": company_payload,
        "client": client_payload,
        "ship_to": None,
        "project": {
            "id": project.id,
            "code": project.project_code,
            "name": project.project_name,
            "description": project.description,
        },
        "invoice": {
            **lifecycle,
            "project_id": invoice.project_id,
            "created_at": invoice.created_at.isoformat(),
            "work_order_date": invoice.work_order_date.isoformat() if invoice.work_order_date else None,
            "dispatch_details": invoice.dispatch_details,
            "dispatch_date": invoice.dispatch_date.isoformat() if invoice.dispatch_date else None,
            "place_of_supply": invoice.place_of_supply,
        },
        # 1..N real line items when Finance entered them (Invoice Generation V2); otherwise
        # one synthetic line from the authoritative taxable amount, exactly as before.
        "line_items": _line_items_payload(db, invoice, project),
        # Split CGST/SGST/IGST when Finance entered them; otherwise one combined tax line.
        "tax_lines": _tax_lines_payload(invoice),
        "totals": {
            "subtotal": taxable,
            "taxable_amount": taxable,
            "tax_amount": tax,
            "invoice_total": total,
            "balance_due": None,
            "amount_in_words": amount_in_words(total, invoice.currency),
            "currency": invoice.currency,
        },
        # Internal settlement snapshot (advance applied / cash received / total settled /
        # outstanding / payment status). STEP 12: this data stays available to ERP consumers
        # and is never deleted, but the renderer must NOT print it on the customer tax invoice.
        "settlement": _settlement_payload(db, invoice),
        "notes": invoice.notes,
        "terms_conditions": None,
        "authorized_signatory_name": signatory.get("name"),
        "qr_data": None,
        # --- V8.7 presentation -----------------------------------------------------------
        # The SAME normalized payload feeds all three themes; only the renderer differs.
        "theme": invoice_theme(invoice),
        "theme_label": INVOICE_THEME_LABELS[invoice_theme(invoice)],
        # True only when a theme was explicitly chosen and stored. A NULL theme is a legacy
        # invoice and keeps the historical layout byte-for-byte.
        "theme_explicit": invoice.theme is not None,
        "signature_assets_configured": bool(
            signatory.get("signature_image") or signatory.get("stamp_image")
        ),
        "signature": {
            "signed": bool(invoice.signed),
            "signed_by_name": signed_by_name,
            "signed_at": invoice.signed_at.isoformat() if invoice.signed_at else None,
            "invalidated_at": (
                invoice.signature_invalidated_at.isoformat()
                if invoice.signature_invalidated_at else None
            ),
            # Configured assets (never hard-coded); None when the company has not uploaded them.
            "signature_image": signatory.get("signature_image"),
            "stamp_image": signatory.get("stamp_image"),
        },
    }


def _safe(value: object | None, fallback: str = "-") -> str:
    text = str(value).strip() if value is not None else ""
    return escape(text or fallback)


def _display_money(value: object, currency: str) -> str:
    return f"{currency} {_money(value):,.2f}"


def _display_date(value: str | None) -> str:
    if not value:
        return "-"
    parts = value[:10].split("-")
    return f"{parts[2]}-{parts[1]}-{parts[0]}" if len(parts) == 3 else value


def _build_invoice_a4_pdf_v2(payload: dict) -> BytesIO:
    """Render the canonical payload; no database session or mutation is involved."""
    output = BytesIO()
    styles = getSampleStyleSheet()
    navy = colors.HexColor("#082A4A")
    cyan = colors.HexColor("#08A8C4")
    line = colors.HexColor("#CBD5E1")
    pale = colors.HexColor("#EFF8FB")
    muted = colors.HexColor("#52677A")
    body = ParagraphStyle("InvoiceBody", parent=styles["BodyText"], fontSize=8.2, leading=11, textColor=navy)
    small = ParagraphStyle("InvoiceSmall", parent=body, fontSize=7.2, leading=9, textColor=muted)
    label = ParagraphStyle("InvoiceLabel", parent=small, fontName="Helvetica-Bold", textColor=cyan, spaceAfter=2)
    title = ParagraphStyle("InvoiceTitle", parent=styles["Title"], fontSize=20, leading=23, alignment=TA_RIGHT, textColor=navy)
    right = ParagraphStyle("InvoiceRight", parent=body, alignment=TA_RIGHT)
    center = ParagraphStyle("InvoiceCenter", parent=body, alignment=TA_CENTER)
    sig_label = ParagraphStyle("InvoiceSigLabel", parent=body, alignment=TA_CENTER, fontName="Helvetica-Bold")

    invoice = payload["invoice"]
    company = payload["company"]
    client = payload["client"]
    totals = payload["totals"]
    # NOTE: payload["settlement"] is intentionally NOT rendered here - the printed tax invoice
    # shows only customer-facing document content (STEP 12); settlement stays in ERP Finance.
    currency = totals["currency"]
    logo_path = _resolve_logo_path()

    def footer(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(15 * mm, 15 * mm, 195 * mm, 15 * mm)
        canvas.setFont("Helvetica-Bold", 7.3)
        canvas.setFillColor(navy)
        canvas.drawString(15 * mm, 10.3 * mm, _safe(company.get("name"), "NakshaTech"))
        canvas.setFont("Helvetica", 6.6)
        canvas.setFillColor(muted)
        footer_bits = " · ".join(part for part in (
            company.get("phone"), company.get("email"), company.get("website"), company.get("address"),
        ) if part)
        canvas.drawString(15 * mm, 6.6 * mm, _safe(footer_bits, "Computer-generated from NakshaTech ERP"))
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(muted)
        canvas.drawRightString(195 * mm - (10 * mm if logo_path else 0), 8.4 * mm, f"Page {doc.page}")
        if logo_path:
            try:
                canvas.drawImage(str(logo_path), 190 * mm, 5.5 * mm, width=10 * mm, height=10 * mm,
                                  preserveAspectRatio=True, mask="auto")
            except Exception:  # noqa: BLE001 - a bad/unreadable asset must never break a tax invoice
                pass
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=20 * mm,
        title=f"{invoice['invoice_number']} {payload['document_type']}", author="NakshaTech ERP",
    )

    # ---- Header: brand mark + TAX INVOICE -----------------------------------------------
    brand_cell = [Image(str(logo_path), width=34 * mm, height=21.8 * mm)] if logo_path else \
        [Paragraph(f"<b>{_safe(company['name'])}</b>", ParagraphStyle("Company", parent=body, fontSize=16, leading=19, textColor=navy))]
    header = Table([
        [brand_cell, [Paragraph(_safe(payload["document_type"]), title)]],
    ], colWidths=[90 * mm, 90 * mm])
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))

    # ---- Company block (left) + invoice/work-order/dispatch/destination (right) ---------
    company_lines = [Paragraph(f"<b>{_safe(company['name'])}</b>", ParagraphStyle("CompanyName", parent=body, fontSize=10.5, leading=13, textColor=navy))]
    for value in (company.get("address"), company.get("phone"), company.get("email")):
        if value:
            company_lines.append(Paragraph(_safe(value), small))
    legal = " · ".join(part for part in (
        f"GSTIN: {company['gstin']}" if company.get("gstin") else "",
        f"PAN: {company['pan']}" if company.get("pan") else "",
    ) if part)
    if legal:
        company_lines.append(Paragraph(_safe(legal), small))

    def meta_row(label_text: str, value: str | None):
        if not value:
            return None
        return [Paragraph(label_text, label), Paragraph(_safe(value), body)]

    meta_rows = [row for row in (
        meta_row("INVOICE NO.", invoice["invoice_number"]),
        meta_row("INVOICE DATE", _display_date(invoice["invoice_date"])),
        meta_row("WORK ORDER / PO", invoice.get("po_wo_reference")),
        meta_row("WORK ORDER DATE", _display_date(invoice.get("work_order_date"))),
        meta_row("DISPATCH DETAILS", invoice.get("dispatch_details")),
        meta_row("DISPATCH DATE", _display_date(invoice.get("dispatch_date"))),
        meta_row("DESTINATION", invoice.get("place_of_supply")),
        meta_row("DUE DATE", _display_date(invoice.get("due_date"))),
    ) if row is not None]
    meta_table = Table(meta_rows, colWidths=[32 * mm, 53 * mm])
    meta_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "LEFT"), ("ALIGN", (1, 0), (1, -1), "LEFT"),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6),
    ]))
    header_strip = Table([[company_lines, meta_table]], colWidths=[105 * mm, 85 * mm])
    header_strip.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, line), ("LINEBEFORE", (1, 0), (1, 0), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    # ---- Billing To (left) + Bank Details (right) ----------------------------------------
    bill_lines = [Paragraph("BILLING TO", label), Paragraph(f"<b>{_safe(client['name'])}</b>", body)]
    for value in (client.get("address"), client.get("country")):
        if value:
            bill_lines.append(Paragraph(_safe(value), small))
    if client.get("gstin"):
        bill_lines.append(Paragraph(f"GSTIN: {_safe(client['gstin'])}", small))
    if client.get("pan"):
        bill_lines.append(Paragraph(f"PAN: {_safe(client['pan'])}", small))
    if client.get("contact_person"):
        bill_lines.append(Paragraph(f"Attn: {_safe(client['contact_person'])}", small))
    for value in (client.get("email"), client.get("phone")):
        if value:
            bill_lines.append(Paragraph(_safe(value), small))

    bank_lines = [Paragraph("BANK DETAILS", label)]
    bank_facts = (
        ("Bank Name", company.get("bank_name")), ("Account Name", company.get("bank_account_name")),
        ("Account Number", company.get("bank_account_number")), ("SWIFT Code", company.get("bank_swift")),
        ("IFSC", company.get("bank_ifsc")), ("Bank Address", company.get("bank_branch")),
    )
    had_bank_fact = False
    for fact_label, value in bank_facts:
        if value:
            had_bank_fact = True
            bank_lines.append(Paragraph(f"<b>{fact_label}:</b> {_safe(value)}", small))
    if not had_bank_fact:
        bank_lines.append(Paragraph("Not configured", small))

    parties = Table([[bill_lines, bank_lines]], colWidths=[105 * mm, 75 * mm])
    parties.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, line), ("LINEBEFORE", (1, 0), (1, 0), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    # ---- Line items (1..N; repeats header row across pages) -----------------------------
    item_rows = [[
        Paragraph("#", center), Paragraph("DESCRIPTION", body), Paragraph("HSN/SAC", center),
        Paragraph("UNIT", center), Paragraph("QTY", center), Paragraph("RATE", right), Paragraph("AMOUNT INR", right),
    ]]
    for item in payload["line_items"]:
        description = f"<b>{_safe(item['description'])}</b>"
        if item.get("detail"):
            description += f"<br/><font color='#52677A' size='7'>{_safe(item['detail'])}</font>"
        item_rows.append([
            Paragraph(str(item["sequence"]), center), Paragraph(description, body),
            Paragraph(_safe(item.get("hsn_sac"), "—"), center),
            Paragraph(_safe(item["unit"]), center), Paragraph(f"{_money(item['quantity']):f}", center),
            Paragraph(_display_money(item["rate"], currency), right),
            Paragraph(_display_money(item["taxable_amount"], currency), right),
        ])
    items = Table(item_rows, colWidths=[8 * mm, 62 * mm, 18 * mm, 14 * mm, 14 * mm, 27 * mm, 37 * mm], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("GRID", (0, 0), (-1, -1), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    # ---- Tax summary: Taxable / CGST / SGST / IGST / Invoice Total (highlighted) ---------
    total_rows = [["Taxable Value", _display_money(totals["taxable_amount"], currency)]]
    for tax_line in payload["tax_lines"]:
        total_rows.append([tax_line["label"], _display_money(tax_line["amount"], currency)])
    total_rows.append(["Invoice Value", _display_money(totals["invoice_total"], currency)])
    total_table = Table(total_rows, colWidths=[55 * mm, 45 * mm], hAlign="RIGHT")
    total_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, line), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), pale),
        ("FONTSIZE", (0, -1), (-1, -1), 9.2), ("FONTSIZE", (0, 0), (-1, -2), 8.2),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))

    # STEP 12: settlement / advance / outstanding data is deliberately NOT printed on the
    # customer-facing tax invoice. It remains available in the ERP Finance screens and in the
    # document payload's settlement block for internal use; only its rendering is removed here.

    legal_block_parts = [part for part in (
        f"Company GST No.: {company['gstin']}" if company.get("gstin") else None,
        f"HSN/SAC: {company['hsn_sac']}" if company.get("hsn_sac") else None,
        f"Company PAN: {company['pan']}" if company.get("pan") else None,
    ) if part]

    signature_block = Table([
        [Paragraph(f"For {_safe(company['name'])}", sig_label)],
        [Spacer(1, 13 * mm)],
        [Paragraph("Authorised Signatory", sig_label)],
    ], colWidths=[60 * mm])
    signature_block.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    signature_row = Table([["", signature_block]], colWidths=[130 * mm, 60 * mm])
    signature_row.setStyle(TableStyle([("ALIGN", (1, 0), (1, 0), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))

    story = [
        header, Spacer(1, 3 * mm), header_strip, Spacer(1, 4 * mm), parties, Spacer(1, 4 * mm), items,
        Spacer(1, 3 * mm), total_table,
        KeepTogether([
            Spacer(1, 3 * mm),
            Paragraph("AMOUNT CHARGEABLE (IN WORDS)", label), Paragraph(_safe(totals["amount_in_words"]), body),
        ]),
    ]
    if legal_block_parts:
        story.extend([Spacer(1, 2.5 * mm), Paragraph(" &nbsp;|&nbsp; ".join(escape(p) for p in legal_block_parts), small)])
    if invoice.get("notes"):
        story.extend([Spacer(1, 4 * mm), Paragraph("NOTES", label), Paragraph(_safe(invoice["notes"]), body)])
    story.append(KeepTogether([Spacer(1, 8 * mm), signature_row]))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    output.seek(0)
    return output


<<<<<<< HEAD
def build_invoice_a4_pdf(payload: dict, template: str | None = None) -> BytesIO:
=======
def _build_themed_invoice_a4(payload: dict) -> BytesIO:
    """Render the selected PNG-reference design from the canonical ERP payload."""
    from app.modules.operations.invoice_theme_renderer import build_reference_invoice_pdf

    # Ship the official horizontal brand asset with the backend as well as the UI.
    # An explicitly configured company logo continues to take precedence.
    horizontal = Path(__file__).resolve().parents[2] / "assets" / "invoice-logo.png"
    logo = _resolve_logo_path() if settings.invoice_logo_path.strip() else (
        horizontal if horizontal.is_file() else _resolve_logo_path()
    )
    return build_reference_invoice_pdf(payload, logo)


def build_invoice_a4_pdf(payload: dict) -> BytesIO:
>>>>>>> 174c0fba15985a1a49d771807ff205580c8e0398
    """Shared NakshaTech A4 renderer for project and standalone adapters.

    The renderer formats only the canonical document payload. It does not query,
    recalculate, or mutate any accounting source.
    """
    # V8.7 THEME DISPATCH — an explicitly stored theme renders through the themed builder;
    # a NULL theme (legacy invoice) keeps the historical layout unchanged.
    if payload.get("theme_explicit"):
        return _build_themed_invoice_a4(payload)
    output = BytesIO()
    styles = getSampleStyleSheet()
    # Optional presentation-only themes. No values in the financial payload are modified.
    palettes = {
        "green_gold": ("#075244", "#BD9137", "#B6D0C2", "#E8F1EB", "#435C55"),
        "modern_teal": ("#075B75", "#00A8BB", "#B4DCE2", "#E9F6F8", "#496976"),
        "geospatial_blue": ("#063A67", "#0F9BD0", "#C1D8E8", "#EAF4FC", "#52677A"),
    }
    if template is not None and template not in palettes:
        raise ValueError("Unsupported invoice template")
    palette = palettes.get(template) or ("#082A4A", "#08A8C4", "#CAD9E2", "#EFF9FB", "#52677A")
    navy, cyan, line, pale, muted = (colors.HexColor(value) for value in palette)
    body = ParagraphStyle("A4Body", parent=styles["BodyText"], fontSize=7.5, leading=9.2, textColor=navy)
    small = ParagraphStyle("A4Small", parent=body, fontSize=6.7, leading=8.2, textColor=muted)
    label = ParagraphStyle("A4Label", parent=small, fontName="Helvetica-Bold", textColor=cyan, spaceAfter=1.5)
    title = ParagraphStyle("A4Title", parent=styles["Title"], fontSize=19, leading=21, alignment=TA_RIGHT, textColor=navy)
    right = ParagraphStyle("A4Right", parent=body, alignment=TA_RIGHT)
    center = ParagraphStyle("A4Center", parent=body, alignment=TA_CENTER)
    signature_style = ParagraphStyle("A4Signature", parent=body, alignment=TA_CENTER, fontName="Helvetica-Bold")

    invoice = payload["invoice"]
    company = payload["company"]
    client = payload["client"]
    ship_to = payload.get("ship_to")
    totals = payload["totals"]
    currency = totals["currency"]
    standalone = payload.get("document_source") == "standalone_invoice"
    logo_path = _resolve_logo_path()

    def canvas_text(value: object | None, fallback: str = "") -> str:
        return " ".join(str(value or fallback).split())

    def page_brand(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        if template is not None:
            page_w, page_h = A4
            # Top and bottom vector bands: the original A4 layout remains identical.
            canvas.setFillColor(navy)
            canvas.rect(0, page_h - 3.4 * mm, page_w, 3.4 * mm, stroke=0, fill=1)
            canvas.rect(0, 0, page_w, 3.2 * mm, stroke=0, fill=1)
            canvas.setFillColor(cyan)
            canvas.rect(0, page_h - 4.1 * mm, page_w, 0.7 * mm, stroke=0, fill=1)
            canvas.rect(0, 3.2 * mm, page_w, 0.5 * mm, stroke=0, fill=1)
            # Thin, decorative contour arcs: decorative only and away from live invoice data.
            canvas.setStrokeColor(line)
            canvas.setLineWidth(0.32)
            for offset in range(4):
                y = page_h - (13 + offset * 2.5) * mm
                canvas.bezier(147 * mm, y, 165 * mm, y + 4 * mm, 195 * mm, y - 5 * mm,
                              211 * mm, y + 2 * mm)
        canvas.restoreState()
        canvas.saveState()
        if logo_path:
            try:
                if hasattr(canvas, "setFillAlpha"):
                    canvas.setFillAlpha(0.055)
                canvas.drawImage(
                    str(logo_path), 50 * mm, 113 * mm, width=110 * mm, height=54 * mm,
                    preserveAspectRatio=True, anchor="c", mask="auto",
                )
            except Exception:  # noqa: BLE001 - document text remains valid if image decoding fails
                pass
        canvas.restoreState()

        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(12 * mm, 13.5 * mm, 198 * mm, 13.5 * mm)
        canvas.setFillColor(navy)
        canvas.setFont("Helvetica-Bold", 6.8)
        canvas.drawString(12 * mm, 9.7 * mm, canvas_text(company.get("name"), "NakshaTech")[:75])
        footer = " · ".join(canvas_text(part) for part in (
            company.get("phone"), company.get("email"), company.get("website"), company.get("address"),
        ) if part)
        canvas.setFillColor(muted)
        canvas.setFont("Helvetica", 6.0)
        canvas.drawString(12 * mm, 6.2 * mm, (footer or "NakshaTech tax invoice")[:145])
        canvas.drawRightString(198 * mm, 9.0 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        output, pagesize=A4, leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=11 * mm, bottomMargin=18 * mm,
        title=f"{invoice['invoice_number']} {payload['document_type']}", author="NakshaTech ERP",
    )

    brand = (
        Image(str(logo_path), width=43 * mm, height=18 * mm, kind="proportional")
        if logo_path else Paragraph(f"<b>{_safe(company.get('name'), 'NakshaTech')}</b>", body)
    )
    header = Table([[brand, Paragraph(_safe(payload["document_type"]), title)]], colWidths=[93 * mm, 93 * mm])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 1.1, cyan), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    company_lines = [Paragraph(f"<b>{_safe(company.get('name'), 'NakshaTech')}</b>", ParagraphStyle("A4Company", parent=body, fontSize=9.5, leading=11.5))]
    for value in (company.get("address"), company.get("phone"), company.get("email"), company.get("website")):
        if value:
            company_lines.append(Paragraph(_safe(value), small))
    seller_ids = " · ".join(part for part in (
        f"GSTIN: {company['gstin']}" if company.get("gstin") else None,
        f"PAN: {company['pan']}" if company.get("pan") else None,
        f"MSME: {company['msme_registration']}" if company.get("msme_registration") else None,
    ) if part)
    if seller_ids:
        company_lines.append(Paragraph(_safe(seller_ids), small))

    def meta(label_text: str, value: object | None):
        if value in (None, ""):
            return None
        return [Paragraph(label_text, label), Paragraph(_safe(value), body)]

    meta_rows = [row for row in (
        meta("INVOICE NO.", invoice.get("invoice_number")),
        meta("INVOICE DATE", _display_date(invoice.get("invoice_date"))),
        meta("TERMS", invoice.get("payment_terms")),
        meta("DUE DATE", _display_date(invoice.get("due_date"))),
        meta("WORK ORDER / REF. W.O", invoice.get("po_wo_reference")),
        meta("WORK ORDER DATE", _display_date(invoice.get("work_order_date"))),
        meta("DISPATCH DETAILS", invoice.get("dispatch_details")),
        meta("DISPATCH DATE", _display_date(invoice.get("dispatch_date"))),
        meta("DESTINATION / PLACE OF SUPPLY", invoice.get("place_of_supply")),
    ) if row is not None]
    details = Table(meta_rows, colWidths=[34 * mm, 51 * mm])
    details.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1.1), ("LEFTPADDING", (0, 0), (-1, -1), 1),
        ("RIGHTPADDING", (0, 0), (-1, -1), 1),
    ]))
    top = Table([[company_lines, details]], colWidths=[101 * mm, 85 * mm])
    top.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.45, line), ("LINEBEFORE", (1, 0), (1, 0), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    def party_lines(heading: str, party: dict | None) -> list:
        data = party or {}
        rows = [Paragraph(heading, label), Paragraph(f"<b>{_safe(data.get('name'), '-')}</b>", body)]
        for value in (data.get("address"), data.get("country")):
            if value:
                rows.append(Paragraph(_safe(value), small))
        for prefix, key in (("GSTIN", "gstin"), ("PAN", "pan")):
            if data.get(key):
                rows.append(Paragraph(f"{prefix}: {_safe(data[key])}", small))
        for value in (data.get("email"), data.get("phone")):
            if value:
                rows.append(Paragraph(_safe(value), small))
        return rows

    if standalone:
        right_party = party_lines("SHIP TO", ship_to)
    else:
        right_party = [Paragraph("BANK DETAILS", label)]
        bank_facts = (
            ("Bank Name", company.get("bank_name")), ("Account Name", company.get("bank_account_name")),
            ("Account Number", company.get("bank_account_number")), ("SWIFT", company.get("bank_swift")),
            ("RTGS / NEFT / IFSC", company.get("bank_ifsc")), ("Bank Address", company.get("bank_branch")),
        )
        facts = [(key, value) for key, value in bank_facts if value]
        right_party.extend([Paragraph(f"<b>{_safe(key)}:</b> {_safe(value)}", small) for key, value in facts])
        if not facts:
            right_party.append(Paragraph("Not configured", small))
    parties = Table([[party_lines("BILL TO", client), right_party]], colWidths=[93 * mm, 93 * mm])
    parties.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.45, line), ("LINEBEFORE", (1, 0), (1, 0), 0.35, line),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))

    if standalone:
        item_rows = [[
            Paragraph("S.NO", center), Paragraph("ITEM & DESCRIPTION", body), Paragraph("HSN/SAC", center),
            Paragraph("QTY", center), Paragraph("UNIT", center), Paragraph("RATE", right),
            Paragraph("TAX %", center), Paragraph("TAX AMT", right), Paragraph("AMOUNT", right),
        ]]
        for item in payload["line_items"]:
            description = f"<b>{_safe(item['description'])}</b>"
            if item.get("detail"):
                description += f"<br/><font color='#52677A' size='6.5'>{_safe(item['detail'])}</font>"
            item_rows.append([
                Paragraph(str(item["sequence"]), center), Paragraph(description, body),
                Paragraph(_safe(item.get("hsn_sac"), "—"), center), Paragraph(f"{Decimal(item['quantity']):f}", center),
                Paragraph(_safe(item["unit"]), center), Paragraph(_display_money(item["rate"], currency), right),
                Paragraph(f"{_money(item.get('tax_percent')):f}%", center),
                Paragraph(_display_money(item.get("tax_amount", 0), currency), right),
                Paragraph(_display_money(item["taxable_amount"], currency), right),
            ])
        widths = [8, 48, 17, 12, 13, 25, 14, 23, 26]
    else:
        item_rows = [[
            Paragraph("SL NO.", center), Paragraph("DESCRIPTION", body), Paragraph("HSN / SAC", center),
            Paragraph("UNIT", center), Paragraph("QTY", center), Paragraph("RATE", right), Paragraph("AMOUNT INR", right),
        ]]
        for item in payload["line_items"]:
            description = f"<b>{_safe(item['description'])}</b>"
            if item.get("detail"):
                description += f"<br/><font color='#52677A' size='6.5'>{_safe(item['detail'])}</font>"
            item_rows.append([
                Paragraph(str(item["sequence"]), center), Paragraph(description, body),
                Paragraph(_safe(item.get("hsn_sac"), "—"), center), Paragraph(_safe(item["unit"]), center),
                Paragraph(f"{Decimal(item['quantity']):f}", center), Paragraph(_display_money(item["rate"], currency), right),
                Paragraph(_display_money(item["taxable_amount"], currency), right),
            ])
        widths = [9, 64, 19, 16, 14, 29, 35]
    items = Table(item_rows, colWidths=[value * mm for value in widths], repeatRows=1)
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), navy if template else pale),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if template else navy),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.2), ("LEFTPADDING", (0, 0), (-1, -1), 3.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5), ("FONTSIZE", (0, 0), (-1, 0), 6.5),
        # ---- Issue 1: one clean, continuous separator under EVERY item row, spanning the
        # complete table width (including the Description column, wrapped text included),
        # plus subtle vertical column separators. Deliberately not a heavy black grid.
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, line),
        ("LINEAFTER", (0, 0), (-2, -1), 0.25, line),
        ("BOX", (0, 0), (-1, -1), 0.4, line),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, cyan),
    ]))

    total_rows = []
    if standalone:
        total_rows.append(["Sub Total", _display_money(totals.get("subtotal", totals["taxable_amount"]), currency)])
        total_rows.append(["Total Taxable Amount", _display_money(totals["taxable_amount"], currency)])
    else:
        total_rows.append(["Taxable Value", _display_money(totals["taxable_amount"], currency)])
    total_rows.extend([[item["label"], _display_money(item["amount"], currency)] for item in payload["tax_lines"]])
    total_rows.append(["Total" if standalone else "Invoice Value", _display_money(totals["invoice_total"], currency)])
    if standalone:
        total_rows.append(["Balance Due", _display_money(totals["balance_due"], currency)])
    total_table = Table(total_rows, colWidths=[58 * mm, 42 * mm])
    total_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, line), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("BACKGROUND", (0, -1), (-1, -1), pale),
        ("FONTSIZE", (0, 0), (-1, -1), 7.2), ("TOPPADDING", (0, 0), (-1, -1), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4.5),
    ]))
    words = [Paragraph("AMOUNT CHARGEABLE (IN WORDS)", label), Paragraph(_safe(totals["amount_in_words"]), body)]
    legal_parts = [part for part in (
        f"Company GST No.: {company['gstin']}" if company.get("gstin") else None,
        f"HSN / SAC: {company['hsn_sac']}" if company.get("hsn_sac") else None,
        f"Company PAN: {company['pan']}" if company.get("pan") else None,
    ) if part]
    if legal_parts:
        words.append(Spacer(1, 2 * mm))
        words.append(Paragraph(" | ".join(_safe(value) for value in legal_parts), small))
    summary = Table([[words, total_table]], colWidths=[86 * mm, 100 * mm])
    summary.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (0, 0), 0), ("RIGHTPADDING", (1, 0), (1, 0), 0)]))

    story = [header, Spacer(1, 2 * mm), top, Spacer(1, 3 * mm), parties, Spacer(1, 3 * mm), items, Spacer(1, 3 * mm), summary]

    # ---- Compact lower block -------------------------------------------------
    # Notes / bank / terms stack in the LEFT column while the QR and the signature
    # share the RIGHT column, so the bottom of the page uses horizontal space
    # instead of stacking vertically. This is what previously forced ReportLab to
    # move the whole final group onto a second page.
    left_blocks: list = []
    if payload.get("notes"):
        left_blocks.extend([Paragraph("NOTES", label), Paragraph(_safe(payload["notes"]), small), Spacer(1, 2 * mm)])
    if standalone:
        bank_parts = [part for part in (
            f"Bank Name: {company['bank_name']}" if company.get("bank_name") else None,
            f"Account Name: {company['bank_account_name']}" if company.get("bank_account_name") else None,
            f"Account Number: {company['bank_account_number']}" if company.get("bank_account_number") else None,
            f"IFSC: {company['bank_ifsc']}" if company.get("bank_ifsc") else None,
            f"SWIFT: {company['bank_swift']}" if company.get("bank_swift") else None,
            f"Bank Address: {company['bank_branch']}" if company.get("bank_branch") else None,
        ) if part]
        if bank_parts:
            left_blocks.extend([
                Paragraph("BANK DETAILS", label),
                Paragraph("<br/>".join(_safe(value) for value in bank_parts), small),
                Spacer(1, 2 * mm),
            ])
    if payload.get("terms_conditions"):
        left_blocks.extend([
            Paragraph("TERMS &amp; CONDITIONS", label),
            Paragraph(_safe(payload["terms_conditions"]).replace("\n", "<br/>"), small),
        ])

    signatory = payload.get("authorized_signatory_name")
    # A genuine signature area without the previous oversized void. It is a nested
    # one-cell table (not KeepTogether) because ReportLab does not allow
    # KeepTogether inside a table cell; a nested table is still atomic, so the
    # "For X" / signatory / "Authorised Signatory" unit never splits.
    signature_block = Table([[[
        Paragraph(f"For {_safe(company.get('name'), 'NakshaTech')}", signature_style),
        Spacer(1, 10 * mm),
        Paragraph(_safe(signatory), signature_style) if signatory else Spacer(1, 1),
        Paragraph("Authorised Signatory", signature_style),
    ]]], colWidths=[62 * mm])
    signature_block.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    right_blocks: list = []
    if payload.get("qr_data"):
        try:
            import qrcode

            qr_stream = BytesIO()
            qrcode.make(payload["qr_data"]).save(qr_stream, format="PNG")
            qr_stream.seek(0)
            right_blocks.append(Image(qr_stream, width=18 * mm, height=18 * mm))
            right_blocks.append(Spacer(1, 2 * mm))
        except Exception:  # noqa: BLE001 - optional QR never blocks the invoice
            pass
    right_blocks.append(signature_block)
    created_label = canvas_text(invoice.get("created_at"), "-").replace("T", " ")[:19]
    right_blocks.insert(0, Paragraph("DATE &amp; TIME OF INVOICE", label))
    right_blocks.insert(1, Paragraph(_safe(created_label), small))
    right_blocks.append(Spacer(1, 1.5 * mm))

    # NOTE: deliberately NOT wrapped in one big KeepTogether. The table itself may
    # split naturally, so a new page only appears when content truly cannot fit.
    lower_block = Table([[left_blocks or Spacer(1, 1), right_blocks]], colWidths=[100 * mm, 86 * mm])
    lower_block.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story.extend([Spacer(1, 3 * mm), lower_block])

    doc.build(story, onFirstPage=page_brand, onLaterPages=page_brand)
    output.seek(0)
    return output
