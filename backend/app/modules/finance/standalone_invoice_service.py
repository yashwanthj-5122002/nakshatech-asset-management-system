"""Standalone invoice document service; intentionally disconnected from project finance."""

from __future__ import annotations

import base64
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import User
from app.modules.finance.standalone_invoice_models import StandaloneInvoice, StandaloneInvoiceLineItem
from app.modules.finance.standalone_invoice_schemas import StandaloneInvoiceCreate
from app.modules.operations.invoice_documents import amount_in_words

MONEY = Decimal("0.01")


def _money(value: object) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def create_standalone_invoice(db: Session, *, actor: User, payload: StandaloneInvoiceCreate) -> StandaloneInvoice:
    number = payload.invoice_number.strip()
    if db.scalar(select(StandaloneInvoice.id).where(StandaloneInvoice.invoice_number == number)) is not None:
        raise ValueError("Standalone invoice number already exists")

    subtotal = _money(sum((item.amount for item in payload.line_items), Decimal("0")))
    total_item_tax = _money(sum((item.tax_amount for item in payload.line_items), Decimal("0")))
    cgst = sgst = igst = Decimal("0.00")
    if payload.tax_mode == "cgst_sgst":
        cgst = _money(sum((item.amount * payload.cgst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
        sgst = _money(sum((item.amount * payload.sgst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
    elif payload.tax_mode == "igst":
        igst = _money(sum((item.amount * payload.igst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
    if _money(cgst + sgst + igst) != total_item_tax:
        raise ValueError("Line-item tax does not reconcile to the selected GST breakdown")

    total = _money(subtotal + total_item_tax)
    row = StandaloneInvoice(
        invoice_number=number,
        invoice_date=payload.invoice_date,
        terms=payload.terms,
        due_date=payload.due_date,
        reference_work_order=payload.reference_work_order,
        place_of_supply=payload.place_of_supply,
        seller_snapshot=payload.seller.model_dump(mode="json"),
        bill_to_snapshot=payload.bill_to.model_dump(mode="json"),
        ship_to_snapshot=payload.ship_to.model_dump(mode="json"),
        bank_snapshot=payload.bank.model_dump(mode="json"),
        notes=payload.notes,
        terms_conditions=payload.terms_conditions,
        tax_mode=payload.tax_mode,
        subtotal=subtotal,
        taxable_amount=subtotal,
        cgst_percent=payload.cgst_percent,
        cgst_amount=cgst,
        sgst_percent=payload.sgst_percent,
        sgst_amount=sgst,
        igst_percent=payload.igst_percent,
        igst_amount=igst,
        total=total,
        balance_due=total,
        amount_in_words=amount_in_words(total, "INR"),
        authorized_signatory_name=payload.authorized_signatory_name,
        qr_data=payload.qr_data,
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    for item in sorted(payload.line_items, key=lambda value: value.sequence):
        db.add(StandaloneInvoiceLineItem(
            standalone_invoice_id=row.id,
            sequence=item.sequence,
            description=item.description,
            detail=item.detail,
            hsn_sac=item.hsn_sac,
            quantity=item.quantity,
            unit=item.unit,
            rate=item.rate,
            tax_percent=item.tax_percent,
            tax_amount=item.tax_amount,
            amount=item.amount,
        ))
    db.flush()
    return row


def _invoice_query():
    return select(StandaloneInvoice).options(selectinload(StandaloneInvoice.line_items))


def get_standalone_invoice(db: Session, invoice_id: int) -> StandaloneInvoice:
    row = db.scalar(_invoice_query().where(StandaloneInvoice.id == invoice_id))
    if row is None:
        raise ValueError("Standalone invoice not found")
    return row


def standalone_invoice_edit_payload(db: Session, invoice_id: int) -> dict:
    """Round-trip the original, saved form parameters, not reconstructed PDF strings."""
    row = get_standalone_invoice(db, invoice_id)
    return {
        "invoice_number": row.invoice_number,
        "invoice_date": row.invoice_date.isoformat(),
        "terms": row.terms,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "reference_work_order": row.reference_work_order,
        "place_of_supply": row.place_of_supply,
        "seller": dict(row.seller_snapshot or {}),
        "bill_to": dict(row.bill_to_snapshot or {}),
        "ship_to": dict(row.ship_to_snapshot or {}),
        "bank": dict(row.bank_snapshot or {}),
        "line_items": [{
            "sequence": item.sequence, "description": item.description,
            "detail": item.detail, "hsn_sac": item.hsn_sac, "quantity": item.quantity,
            "unit": item.unit, "rate": item.rate,
            "tax_percent": item.tax_percent, "tax_amount": item.tax_amount,
            "amount": item.amount,
        } for item in row.line_items],
        "tax_mode": row.tax_mode,
        "cgst_percent": row.cgst_percent, "sgst_percent": row.sgst_percent,
        "igst_percent": row.igst_percent,
        "notes": row.notes, "terms_conditions": row.terms_conditions,
        "authorized_signatory_name": row.authorized_signatory_name, "qr_data": row.qr_data,
    }


def update_standalone_invoice(db: Session, *, invoice_id: int, payload: StandaloneInvoiceCreate) -> StandaloneInvoice:
    """Edit a standalone Finance-only invoice using EXACTLY the creation schema and GST rules.

    Invoice number is immutable after first save. No project invoice, advance,
    payment, or accounting records are touched.
    """
    row = get_standalone_invoice(db, invoice_id)
    if payload.invoice_number.strip() != row.invoice_number:
        raise ValueError("Saved invoice numbers cannot be changed. Create a new invoice if a new number is required")

    subtotal = _money(sum((item.amount for item in payload.line_items), Decimal("0")))
    total_item_tax = _money(sum((item.tax_amount for item in payload.line_items), Decimal("0")))
    cgst = sgst = igst = Decimal("0.00")
    if payload.tax_mode == "cgst_sgst":
        cgst = _money(sum((item.amount * payload.cgst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
        sgst = _money(sum((item.amount * payload.sgst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
    elif payload.tax_mode == "igst":
        igst = _money(sum((item.amount * payload.igst_percent / Decimal("100") for item in payload.line_items), Decimal("0")))
    if _money(cgst + sgst + igst) != total_item_tax:
        raise ValueError("Line-item tax does not reconcile to the selected GST breakdown")
    total = _money(subtotal + total_item_tax)

    row.invoice_date = payload.invoice_date
    row.terms = payload.terms
    row.due_date = payload.due_date
    row.reference_work_order = payload.reference_work_order
    row.place_of_supply = payload.place_of_supply
    row.seller_snapshot = payload.seller.model_dump(mode="json")
    row.bill_to_snapshot = payload.bill_to.model_dump(mode="json")
    row.ship_to_snapshot = payload.ship_to.model_dump(mode="json")
    row.bank_snapshot = payload.bank.model_dump(mode="json")
    row.notes = payload.notes
    row.terms_conditions = payload.terms_conditions
    row.tax_mode = payload.tax_mode
    row.subtotal = subtotal
    row.taxable_amount = subtotal
    row.cgst_percent = payload.cgst_percent
    row.cgst_amount = cgst
    row.sgst_percent = payload.sgst_percent
    row.sgst_amount = sgst
    row.igst_percent = payload.igst_percent
    row.igst_amount = igst
    row.total = total
    row.balance_due = total
    row.amount_in_words = amount_in_words(total, "INR")
    row.authorized_signatory_name = payload.authorized_signatory_name
    row.qr_data = payload.qr_data

    row.line_items.clear()
    db.flush()  # Clears old per-invoice sequence constraints before reinserting rows.
    for item in sorted(payload.line_items, key=lambda value: value.sequence):
        row.line_items.append(StandaloneInvoiceLineItem(
            sequence=item.sequence, description=item.description, detail=item.detail,
            hsn_sac=item.hsn_sac, quantity=item.quantity, unit=item.unit,
            rate=item.rate, tax_percent=item.tax_percent,
            tax_amount=item.tax_amount, amount=item.amount,
        ))
    db.flush()
    return row


def standalone_invoice_document_payload(db: Session, invoice_id: int) -> dict:
    row = get_standalone_invoice(db, invoice_id)
    seller = dict(row.seller_snapshot or {})
    bank = dict(row.bank_snapshot or {})
    bill = dict(row.bill_to_snapshot or {})
    ship = dict(row.ship_to_snapshot or {})
    tax_lines = []
    if Decimal(row.cgst_amount or 0) or Decimal(row.cgst_percent or 0):
        tax_lines.append({"label": f"CGST @ {_money(row.cgst_percent):f}%", "rate_percent": _money(row.cgst_percent), "amount": _money(row.cgst_amount), "source": "standalone_invoice.cgst_amount"})
    if Decimal(row.sgst_amount or 0) or Decimal(row.sgst_percent or 0):
        tax_lines.append({"label": f"SGST @ {_money(row.sgst_percent):f}%", "rate_percent": _money(row.sgst_percent), "amount": _money(row.sgst_amount), "source": "standalone_invoice.sgst_amount"})
    if Decimal(row.igst_amount or 0) or Decimal(row.igst_percent or 0):
        tax_lines.append({"label": f"IGST @ {_money(row.igst_percent):f}%", "rate_percent": _money(row.igst_percent), "amount": _money(row.igst_amount), "source": "standalone_invoice.igst_amount"})
    qr_image_data_uri = None
    if row.qr_data:
        import qrcode

        qr_stream = BytesIO()
        qrcode.make(row.qr_data).save(qr_stream, format="PNG")
        qr_image_data_uri = "data:image/png;base64," + base64.b64encode(qr_stream.getvalue()).decode("ascii")
    return {
        "document_type": "TAX INVOICE",
        "document_version": 3,
        "document_source": "standalone_invoice",
        "entry_mode": "manual",
        "company": {
            "name": seller.get("company_name"), "address": seller.get("address"),
            "gstin": seller.get("gstin"), "pan": seller.get("pan"),
            "msme_registration": seller.get("msme_registration"), "email": seller.get("email"),
            "phone": seller.get("phone"), "website": seller.get("website"), "hsn_sac": None,
            "bank_name": bank.get("bank_name"), "bank_account_name": bank.get("account_name"),
            "bank_account_number": bank.get("account_number"), "bank_ifsc": bank.get("ifsc_code"),
            "bank_swift": bank.get("swift_code"), "bank_branch": bank.get("bank_address"),
            "data_source": "standalone_invoice_snapshot",
        },
        "client": {
            "code": None, "name": bill.get("company_name"), "address": bill.get("address"),
            "country": None, "gstin": bill.get("gstin"), "pan": bill.get("pan"),
            "contact_person": None, "phone": bill.get("phone"), "email": bill.get("email"),
            "data_source": "standalone_invoice_snapshot",
        },
        "ship_to": {
            "name": ship.get("company_name"), "address": ship.get("address"),
            "gstin": ship.get("gstin"), "pan": ship.get("pan"), "phone": ship.get("phone"),
            "email": ship.get("email"),
        },
        "project": None,
        "invoice": {
            "id": row.id, "invoice_number": row.invoice_number,
            "invoice_date": row.invoice_date.isoformat(), "due_date": row.due_date.isoformat() if row.due_date else None,
            "payment_terms": row.terms, "po_wo_reference": row.reference_work_order,
            "work_order_date": None, "dispatch_details": None, "dispatch_date": None,
            "place_of_supply": row.place_of_supply, "created_at": row.created_at.isoformat(),
            "notes": row.notes,
        },
        "line_items": [{
            "sequence": item.sequence, "description": item.description, "detail": item.detail,
            "hsn_sac": item.hsn_sac, "quantity": Decimal(item.quantity), "unit": item.unit,
            "rate": _money(item.rate), "tax_percent": _money(item.tax_percent),
            "tax_amount": _money(item.tax_amount), "taxable_amount": _money(item.amount),
            "source": "standalone_invoice_line_item",
        } for item in row.line_items],
        "tax_lines": tax_lines,
        "totals": {
            "subtotal": _money(row.subtotal), "taxable_amount": _money(row.taxable_amount),
            "tax_amount": _money(Decimal(row.cgst_amount) + Decimal(row.sgst_amount) + Decimal(row.igst_amount)),
            "invoice_total": _money(row.total), "balance_due": _money(row.balance_due),
            "amount_in_words": row.amount_in_words, "currency": "INR",
        },
        "notes": row.notes,
        "terms_conditions": row.terms_conditions,
        "authorized_signatory_name": row.authorized_signatory_name,
        "qr_data": row.qr_data,
        "qr_image_data_uri": qr_image_data_uri,
    }


def standalone_history(db: Session) -> list[dict]:
    rows = list(db.scalars(_invoice_query().order_by(StandaloneInvoice.created_at.desc(), StandaloneInvoice.id.desc())))
    creator_ids = {row.created_by_id for row in rows}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(creator_ids)))} if creator_ids else {}
    return [{
        "id": row.id, "invoice_number": row.invoice_number, "invoice_date": row.invoice_date.isoformat(),
        "party": (row.bill_to_snapshot or {}).get("company_name") or "-", "total": float(row.total),
        "created_by": users[row.created_by_id].full_name if row.created_by_id in users else "Unknown",
        "created_at": row.created_at.isoformat(),
    } for row in rows]
