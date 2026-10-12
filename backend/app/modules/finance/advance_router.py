from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.finance.advance_notification_service import refresh_advance_notifications
from app.modules.finance.advance_schemas import (
    ClientAdvanceApplyToInvoice,
    ClientAdvanceFollowUpCreate,
    ClientAdvanceTransactionCreate,
)
from app.modules.finance.advance_settlement_service import (
    apply_advance_to_invoice,
    project_collection_summary,
)
from app.modules.finance.advance_service import (
    add_advance_followup,
    advance_project_detail,
    advance_projects,
    advance_status_history,
    advance_summary,
    record_advance_transaction,
)

router = APIRouter(prefix="/advance-payments", tags=["Finance Client Advance Payments"])


def _forbidden(exc: PermissionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/summary")
def get_advance_payment_summary(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        return advance_summary(db, user=auth.user, effective_role=auth.effective_role)
    except PermissionError as exc:
        raise _forbidden(exc) from exc


@router.get("/projects")
def get_advance_payment_projects(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        return {"projects": advance_projects(db, user=auth.user, effective_role=auth.effective_role)}
    except PermissionError as exc:
        raise _forbidden(exc) from exc


@router.get("/{project_id}/history")
def get_advance_payment_history(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        rows = advance_status_history(
            db,
            project_id=project_id,
            user=auth.user,
            effective_role=auth.effective_role,
        )
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    if rows is None:
        raise HTTPException(status_code=404, detail="Client advance project not found")
    return {"history": rows}


@router.post("/{project_id}/transactions", status_code=status.HTTP_201_CREATED)
def create_advance_payment_transaction(
    project_id: int,
    payload: ClientAdvanceTransactionCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        result = record_advance_transaction(
            db,
            project_id=project_id,
            payload=payload,
            actor=auth.user,
            effective_role=auth.effective_role,
        )
        record_audit(
            db,
            event_type="CLIENT_ADVANCE_TRANSACTION_RECORDED",
            request=request,
            user=auth.user,
            module="finance",
            target_type="client_advance_transaction",
            target_id=result["transaction"]["id"],
            details={"project_id": project_id, "status": result["status"]},
        )
        db.commit()
        return result
    except PermissionError as exc:
        db.rollback()
        raise _forbidden(exc) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{project_id}/collection")
def get_advance_project_collection(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    """ADVANCE COLLECTION + PROJECT COLLECTION read model for one project.

    Central helper ``project_collection_summary`` is the single source of truth:
        advance received + invoice cash payments = total collected
    An advance already applied to an invoice is never counted twice, and access
    follows the existing Client Advance matrix (PM roles stay redacted).
    """
    try:
        return project_collection_summary(
            db, project_id=project_id, user=auth.user, effective_role=auth.effective_role,
        )
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{project_id}/apply-to-invoice")
def apply_advance_to_invoice_endpoint(
    project_id: int,
    payload: ClientAdvanceApplyToInvoice,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    """Settle an invoice with client-advance money already received (Finance only).

    Writes the allocation onto the existing client-advance receipt rows
    (``adjusted_invoice_id`` / ``adjusted_amount_inr`` / ``adjusted_at``) and
    re-derives the invoice payment status from
    ``invoice cash payments + advance applied``. The invoice face value, project
    commercial value, Sales, Revenue rule and Employee Advance are untouched, and
    no duplicate row is written to ``project_invoice_payments``.
    """
    try:
        result = apply_advance_to_invoice(
            db,
            project_id=project_id,
            invoice_id=payload.invoice_id,
            amount_inr=payload.amount,
            actor=auth.user,
            effective_role=auth.effective_role,
            remarks=payload.remarks,
        )
        record_audit(
            db,
            event_type="CLIENT_ADVANCE_APPLIED_TO_INVOICE",
            request=request,
            user=auth.user,
            module="finance",
            target_type="client_advance_transaction",
            target_id=result["invoice_id"],
            details={
                "project_id": project_id,
                "invoice_id": result["invoice_id"],
                "invoice_number": result["invoice_number"],
                "applied_inr": result["applied_inr"],
                "allocations": result["allocations"],
                "invoice_status": result["invoice_status"],
                "invoice_balance": result["invoice_balance"],
                "advance_status": result["advance_status"],
            },
        )
        db.commit()
        result["collection"] = project_collection_summary(
            db, project_id=project_id, user=auth.user, effective_role=auth.effective_role,
        )
        return result
    except PermissionError as exc:
        db.rollback()
        raise _forbidden(exc) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{project_id}/followups", status_code=status.HTTP_201_CREATED)
def create_advance_payment_followup(
    project_id: int,
    payload: ClientAdvanceFollowUpCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        result = add_advance_followup(
            db,
            project_id=project_id,
            payload=payload,
            actor=auth.user,
            effective_role=auth.effective_role,
        )
        record_audit(
            db,
            event_type="CLIENT_ADVANCE_FOLLOWUP_RECORDED",
            request=request,
            user=auth.user,
            module="finance",
            target_type="client_advance_followup",
            target_id=result["id"],
            details={"project_id": project_id},
        )
        db.commit()
        return result
    except PermissionError as exc:
        db.rollback()
        raise _forbidden(exc) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/refresh-notifications")
def refresh_advance_payment_notifications(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    """Calculate due/overdue/partial/high-value advances and create notifications.

    Idempotent per project, per rule, per calendar day through dedupe keys
    (advance_due_project_{project_id}_{date}, advance_overdue_project_..., etc.).
    No background scheduler: the Finance Command Center calls this on load.
    Permissions (Finance full / Management+BD scoped / PM amounts hidden /
    Production-QC-QA denied) are enforced backend side by resolve_advance_access.
    """
    try:
        result = refresh_advance_notifications(
            db,
            user=auth.user,
            effective_role=auth.effective_role,
        )
    except PermissionError as exc:
        db.rollback()
        raise _forbidden(exc) from exc
    record_audit(
        db,
        event_type="CLIENT_ADVANCE_NOTIFICATIONS_REFRESHED",
        request=request,
        user=auth.user,
        module="finance",
        target_type="advance_notifications",
        details={
            "created": result["created"],
            "matched": result["matched"],
            "as_of": result["as_of"],
        },
    )
    db.commit()
    return result


@router.get("/{project_id}")
def get_advance_payment_detail(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    try:
        result = advance_project_detail(
            db,
            project_id=project_id,
            user=auth.user,
            effective_role=auth.effective_role,
        )
    except PermissionError as exc:
        raise _forbidden(exc) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Client advance project not found")
    return result
