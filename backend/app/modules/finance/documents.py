from __future__ import annotations

from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import re

from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.finance.attachments import read_finance_attachment_bytes
from app.modules.finance.models import ExpenseClaim, ExpenseSettlementAttachment
from app.modules.finance.service import CLAIM_TYPE_LABELS, STATUS_LABELS, approved_amount, claim_paid_amount, effective_settlement_due_date, remaining_amount
from app.modules.finance.settlement_service import tally_status

PAGE_WIDTH, PAGE_HEIGHT = A4


def _money(value) -> str:
    return f"INR {float(value or 0):,.2f}"


def _safe_text(value) -> str:
    return str(value or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _display_date(value) -> str:
    if value is None:
        return "-"
    return value.strftime("%d-%b-%Y") if hasattr(value, "strftime") else str(value)


def _user_name(db: Session, user_id: int | None) -> str:
    if not user_id:
        return "-"
    user = db.get(User, user_id)
    return user.full_name if user else "-"


def build_claim_a4_pdf(db: Session, claim: ExpenseClaim) -> BytesIO:
    output = BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle("FinanceTitle", parent=styles["Title"], fontSize=17, leading=21, alignment=TA_CENTER, textColor=colors.HexColor("#0B2D4F"))
    heading = ParagraphStyle("FinanceHeading", parent=styles["Heading2"], fontSize=10, leading=13, textColor=colors.HexColor("#0B7285"), spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle("FinanceBody", parent=styles["BodyText"], fontSize=8.5, leading=11)
    small = ParagraphStyle("FinanceSmall", parent=styles["BodyText"], fontSize=7.5, leading=9, textColor=colors.HexColor("#52677A"))

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title=f"{claim.claim_code} Project Expense Report",
        author="NakshaTech Finance CRM",
    )
    story = [
        Paragraph("NAKSHATECH", title),
        Paragraph("PROJECT EXPENSE / SETTLEMENT REPORT", ParagraphStyle("Sub", parent=heading, alignment=TA_CENTER, fontSize=9)),
        Spacer(1, 3 * mm),
    ]

    requester = db.get(User, claim.requester_id)
    summary_rows = [
        ["Claim ID", claim.claim_code, "Request Type", CLAIM_TYPE_LABELS.get(claim.claim_type, claim.claim_type)],
        ["Employee", requester.full_name if requester else "Unknown", "Department", requester.department if requester else "-"],
        ["Project", f"{claim.project.project_code} - {claim.project.project_name}", "Client", claim.project.client_name or "-"],
        ["Project Period", f"{_display_date(claim.project.start_date)} to {_display_date(claim.project.end_date)}", "Claim Status", STATUS_LABELS.get(claim.status, claim.status)],
        ["Employee Work Period", f"{_display_date(claim.requested_work_start_date)} to {_display_date(claim.requested_work_end_date)}", "Approved Work Period", f"{_display_date(claim.approved_work_start_date)} to {_display_date(claim.approved_work_end_date)}"],
        ["Settlement Due", _display_date(effective_settlement_due_date(claim)), "Settlement Status", claim.settlement_status.replace("_", " ").title()],
        ["Requested", _money(claim.total_amount), "Finance Approved", _money(approved_amount(claim)) if approved_amount(claim) else "-"],
        ["Paid / Released", _money(claim_paid_amount(claim)), "Payment Outstanding", _money(remaining_amount(claim))],
    ]
    t = Table(summary_rows, colWidths=[31 * mm, 58 * mm, 34 * mm, 55 * mm], repeatRows=0)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF4FB")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF4FB")),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.extend([t, Paragraph("Purpose / Description", heading), Paragraph(_safe_text(claim.purpose_description), body)])

    story.append(Paragraph("Requested Expense Breakup", heading))
    item_rows = [["#", "Category", "Description", "Payment Mode", "Expense Date", "Amount"]]
    for idx, item in enumerate(claim.items, start=1):
        category = item.other_category or item.category.replace("_", " ").title()
        item_rows.append([idx, category, Paragraph(_safe_text(item.description), small), (item.payment_mode or "-").replace("_", " ").title(), _display_date(item.expense_date), _money(item.amount)])
    requested_table = Table(item_rows, colWidths=[8 * mm, 29 * mm, 66 * mm, 27 * mm, 27 * mm, 29 * mm], repeatRows=1)
    requested_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2D4F")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.extend([requested_table, Spacer(1, 2 * mm), Paragraph(f"<b>Total requested:</b> {_money(claim.total_amount)}", body)])

    if claim.settlement:
        settlement = claim.settlement
        story.append(PageBreak())
        story.append(Paragraph("Advance Settlement", heading))
        settlement_rows = [
            ["Settlement ID", settlement.settlement_code, "Status", settlement.status.replace("_", " ").title()],
            ["Total Advance Released", _money(settlement.total_advance_received), "Actual Supported Expense", _money(settlement.total_expense_amount)],
            ["Balance to Return", _money(settlement.balance_to_return), "Shortage", _money(settlement.shortage_amount)],
            ["Tally", tally_status(settlement).replace("_", " ").title(), "Finalized", _display_date(settlement.finalized_at)],
        ]
        st = Table(settlement_rows, colWidths=[38 * mm, 51 * mm, 38 * mm, 51 * mm])
        st.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EAF4FB")),
            ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EAF4FB")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.4),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(st)
        story.append(Paragraph("Actual Expenses / Bills", heading))
        rows = [["#", "Category", "Description", "Mode", "Date", "Amount"]]
        for idx, item in enumerate(settlement.items, start=1):
            rows.append([idx, item.other_category or item.category.replace("_", " ").title(), Paragraph(_safe_text(item.description), small), item.payment_mode.replace("_", " ").title(), _display_date(item.expense_date), _money(item.amount)])
        sit = Table(rows, colWidths=[8 * mm, 29 * mm, 66 * mm, 27 * mm, 27 * mm, 29 * mm], repeatRows=1)
        sit.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2D4F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (-1, 1), (-1, -1), "RIGHT"),
        ]))
        story.append(sit)

        story.append(Paragraph("Settlement Verification", heading))
        settlement_decisions = [
            ["Admin", _user_name(db, settlement.admin_decision_by_id), _display_date(settlement.admin_decision_at), settlement.admin_comments or "-"],
            ["Finance", _user_name(db, settlement.finance_decision_by_id), _display_date(settlement.finance_decision_at), settlement.finance_comments or "-"],
        ]
        svt = Table(settlement_decisions, colWidths=[24 * mm, 42 * mm, 32 * mm, 80 * mm])
        svt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("FONTSIZE", (0, 0), (-1, -1), 7.2),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(svt)

    story.append(Paragraph("Verification & Payment History", heading))
    decision_rows = [
        ["Admin", _user_name(db, claim.admin_decision_by_id), _display_date(claim.admin_decision_at), claim.admin_comments or "-"],
        ["Finance", _user_name(db, claim.finance_decision_by_id), _display_date(claim.finance_decision_at), claim.finance_comments or "-"],
    ]
    dt = Table(decision_rows, colWidths=[24 * mm, 42 * mm, 32 * mm, 80 * mm])
    dt.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 7.2), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(dt)

    if claim.payments:
        story.append(Paragraph("Payment Ledger", heading))
        rows = [["Date", "Mode", "Reference", "Amount", "Recorded By"]]
        for payment in claim.payments:
            rows.append([_display_date(payment.payment_date), payment.payment_mode.replace("_", " ").title(), payment.payment_reference, _money(payment.amount), _user_name(db, payment.recorded_by_id)])
        pt = Table(rows, colWidths=[28 * mm, 31 * mm, 54 * mm, 32 * mm, 38 * mm], repeatRows=1)
        pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2D4F")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
        story.append(pt)

    attachments = [("Request proof", attachment) for attachment in claim.attachments]
    if claim.settlement:
        attachments.extend(("Settlement bill", attachment) for attachment in claim.settlement.attachments)
    proof_count = len(attachments)
    if attachments:
        story.append(Paragraph("Bill / Proof Register", heading))
        proof_rows = [["#", "Type", "Filename", "Uploaded", "Integrity SHA-256"]]
        for idx, (kind, attachment) in enumerate(attachments, start=1):
            digest = attachment.content_sha256 or "Legacy file - hash unavailable"
            digest_text = digest if len(digest) <= 24 else f"{digest[:12]}...{digest[-12:]}"
            proof_rows.append([idx, kind, Paragraph(_safe_text(attachment.original_filename), small), _display_date(attachment.created_at), digest_text])
        brt = Table(proof_rows, colWidths=[8 * mm, 28 * mm, 72 * mm, 32 * mm, 45 * mm], repeatRows=1)
        brt.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0B2D4F")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("FONTSIZE", (0, 0), (-1, -1), 6.8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.append(brt)
    story.extend([
        Spacer(1, 4 * mm),
        Paragraph(f"Supporting bill/proof files registered: <b>{proof_count}</b>", small),
        Paragraph(f"Generated from NakshaTech Finance CRM on {utc_now().strftime('%d-%b-%Y %H:%M UTC')}. Database records remain the source of truth.", small),
    ])
    doc.build(story)
    output.seek(0)
    return output


def _safe_filename(name: str, fallback: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name).strip(" .")
    return clean[:180] or fallback


def build_all_bills_zip(claim: ExpenseClaim) -> BytesIO:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        used: set[str] = set()
        def add(prefix: str, attachment, index: int) -> None:
            base = _safe_filename(attachment.original_filename, f"bill-{index}")
            candidate = f"{prefix}/{base}"
            counter = 2
            while candidate.lower() in used:
                stem, suffix = Path(base).stem, Path(base).suffix
                candidate = f"{prefix}/{stem}-{counter}{suffix}"
                counter += 1
            used.add(candidate.lower())
            archive.writestr(candidate, read_finance_attachment_bytes(attachment.storage_key))
        for idx, attachment in enumerate(claim.attachments, start=1):
            add("claim-proof", attachment, idx)
        if claim.settlement:
            for idx, attachment in enumerate(claim.settlement.attachments, start=1):
                add("settlement-bills", attachment, idx)
    output.seek(0)
    return output


def _image_pdf(data: bytes) -> BytesIO:
    img = Image.open(BytesIO(data))
    if img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=A4)
    margin = 12 * mm
    iw, ih = img.size
    max_w, max_h = PAGE_WIDTH - 2 * margin, PAGE_HEIGHT - 2 * margin
    scale = min(max_w / iw, max_h / ih)
    dw, dh = iw * scale, ih * scale
    x, y = (PAGE_WIDTH - dw) / 2, (PAGE_HEIGHT - dh) / 2
    c.drawImage(ImageReader(img), x, y, width=dw, height=dh, preserveAspectRatio=True)
    c.showPage()
    c.save()
    output.seek(0)
    return output


def _append_pdf_as_a4(writer: PdfWriter, data: bytes) -> None:
    reader = PdfReader(BytesIO(data))
    for page in reader.pages:
        source_w = float(page.mediabox.width)
        source_h = float(page.mediabox.height)
        if source_w <= 0 or source_h <= 0:
            continue
        margin = 10 * mm
        scale = min((PAGE_WIDTH - 2 * margin) / source_w, (PAGE_HEIGHT - 2 * margin) / source_h)
        tx = (PAGE_WIDTH - source_w * scale) / 2
        ty = (PAGE_HEIGHT - source_h * scale) / 2
        target = writer.add_blank_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)
        target.merge_transformed_page(page, Transformation().scale(scale).translate(tx, ty))


def build_complete_a4_pack(db: Session, claim: ExpenseClaim) -> BytesIO:
    writer = PdfWriter()
    summary = PdfReader(build_claim_a4_pdf(db, claim))
    for page in summary.pages:
        writer.add_page(page)

    attachments = list(claim.attachments)
    if claim.settlement:
        attachments.extend(claim.settlement.attachments)
    for attachment in attachments:
        data = read_finance_attachment_bytes(attachment.storage_key)
        if attachment.mime_type == "application/pdf":
            _append_pdf_as_a4(writer, data)
        elif attachment.mime_type.startswith("image/"):
            image_reader = PdfReader(_image_pdf(data))
            for page in image_reader.pages:
                writer.add_page(page)

    output = BytesIO()
    writer.write(output)
    output.seek(0)
    return output
