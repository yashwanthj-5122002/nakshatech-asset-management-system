from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.finance.standalone_invoice_schemas import StandaloneInvoiceCreate
from app.modules.finance.standalone_invoice_service import (
    create_standalone_invoice,
    standalone_invoice_edit_payload,
    update_standalone_invoice,
    standalone_history,
    standalone_invoice_document_payload,
)
from app.modules.operations.invoice_documents import build_invoice_a4_pdf

router = APIRouter(prefix="/generated-invoices", tags=["Standalone Invoice Documents"])


def _finance_only(auth: CurrentAuth) -> None:
    if (auth.effective_role or "").strip().lower() != "finance":
        raise HTTPException(status_code=403, detail="Generate Invoice is restricted to Finance")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError) and "not found" in str(exc).lower():
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.get("")
def list_generated_invoices(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _finance_only(auth)
    return {"invoices": standalone_history(db)}


@router.post("", status_code=201)
def generate_invoice(
    payload: StandaloneInvoiceCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    try:
        row = create_standalone_invoice(db, actor=auth.user, payload=payload)
        record_audit(
            db, event_type="STANDALONE_INVOICE_CREATED", request=request, user=auth.user,
            module="finance", target_type="standalone_invoice", target_id=row.id,
            details={"invoice_number": row.invoice_number, "total": str(row.total)},
        )
        db.commit()
        return standalone_invoice_document_payload(db, row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/{invoice_id}/edit")
def get_generated_invoice_edit_form(
    invoice_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)
):
    _finance_only(auth)
    try:
        return standalone_invoice_edit_payload(db, invoice_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.put("/{invoice_id}")
def edit_generated_invoice(
    invoice_id: int,
    payload: StandaloneInvoiceCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    try:
        before = standalone_invoice_document_payload(db, invoice_id)
        row = update_standalone_invoice(db, invoice_id=invoice_id, payload=payload)
        record_audit(
            db, event_type="STANDALONE_INVOICE_EDITED", request=request, user=auth.user,
            module="finance", target_type="standalone_invoice", target_id=row.id,
            details={
                "invoice_number": row.invoice_number,
                "before_total": str(before["totals"]["invoice_total"]),
                "after_total": str(row.total),
                "before_tax": str(before["totals"]["tax_amount"]),
                "after_tax": str(row.cgst_amount + row.sgst_amount + row.igst_amount),
                "edited_by": auth.user.id,
            },
        )
        db.commit()
        return standalone_invoice_document_payload(db, invoice_id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/{invoice_id}")
def get_generated_invoice(
    invoice_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)
):
    _finance_only(auth)
    try:
        return standalone_invoice_document_payload(db, invoice_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/{invoice_id}/document")
def preview_generated_invoice(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    try:
        payload = standalone_invoice_document_payload(db, invoice_id)
        record_audit(
            db, event_type="STANDALONE_INVOICE_GENERATED", request=request, user=auth.user,
            module="finance", target_type="standalone_invoice", target_id=invoice_id,
            details={"format": "preview"},
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/{invoice_id}/document.pdf")
def generated_invoice_pdf(
    invoice_id: int,
    request: Request,
    download: bool = Query(default=False),
    template: Literal["green_gold", "modern_teal", "geospatial_blue"] | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _finance_only(auth)
    try:
        payload = standalone_invoice_document_payload(db, invoice_id)
        output = build_invoice_a4_pdf(payload, template=template)
        record_audit(
            db, event_type="STANDALONE_INVOICE_DOWNLOADED" if download else "STANDALONE_INVOICE_GENERATED",
            request=request, user=auth.user, module="finance", target_type="standalone_invoice",
            target_id=invoice_id, details={"format": "pdf", "download": download, "template": template or "classic"},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "_", payload["invoice"]["invoice_number"]).strip("._") or f"invoice-{invoice_id}"
    template_name = template or "classic"
    return StreamingResponse(
        output, media_type="application/pdf",
        headers={
            "Content-Disposition": f'{"attachment" if download else "inline"}; filename="{safe_number}_{template_name}_A4_Invoice.pdf"',
            "Cache-Control": "private, no-store, max-age=0", "X-Content-Type-Options": "nosniff",
        },
    )
