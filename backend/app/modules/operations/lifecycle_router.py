from __future__ import annotations

import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import TECHNICAL_PM_ROLES
from app.core.department_access import ensure_project_department_access
from app.modules.commercial.fx_service import FxUnavailableError
from app.modules.employee_portal.service import record_audit
from app.modules.finance.attachments import (
    FINANCE_ATTACHMENT_MAX_BYTES,
    FinanceAttachmentStorageError,
    FinanceAttachmentValidationError,
    delete_finance_attachment_object,
    store_finance_attachment,
    validate_finance_attachment_bytes,
)
from app.modules.operations.lifecycle_models import ProjectFeedbackAttachment, ProjectReworkCycle
from app.modules.operations.invoice_documents import build_invoice_a4_pdf, invoice_document_payload
from app.modules.operations.lifecycle_schemas import (
    BadDebtDecision,
    BadDebtProposalCreate,
    BadDebtRecoveryCreate,
    ChangeRequestDecision,
    DeemedAcceptanceCreate,
    FeedbackClassification,
    FeedbackRequestCreate,
    FeedbackResponseCreate,
    InvoiceClose,
    InvoiceDraftCreate,
    InvoicePaymentCreate,
    InvoiceRaise,
    ManualFeedbackResponseCreate,
    NoFeedbackRecommendation,
    ProjectMessageCreate,
    ReworkStageUpdate,
)
from app.modules.operations.lifecycle_service import (
    CLIENT_ACCEPTANCE_PENDING_BD,
    FEEDBACK_NEGATIVE,
    advance_rework,
    authorize_deemed_acceptance,
    decide_bad_debt,
    classify_feedback_response,
    close_invoice,
    confirm_client_acceptance,
    create_feedback_request,
    create_invoice_draft,
    create_project_message,
    invoice_auto_fill,
    decide_change_request,
    feedback_response_for_attachment_token,
    lifecycle_dashboard,
    list_bad_debts,
    list_project_messages,
    mark_invoice_overdue,
    project_360,
    propose_bad_debt,
    public_feedback_payload,
    raise_invoice,
    record_bad_debt_recovery,
    record_manual_feedback_response,
    recommend_no_feedback_closure,
    record_invoice_payment,
    reconcile_rework_cycle,
    resubmit_rework,
    send_feedback_reminder,
    send_feedback_request_email,
    submit_feedback_response,
)

router = APIRouter(prefix="/lifecycle", tags=["Client Feedback, Rework and Billing Lifecycle"])


def _role(auth: CurrentAuth) -> str:
    return (auth.effective_role or "").strip().lower()


def _roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this lifecycle action")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, FxUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc), "attempts": exc.attempts},
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(
    request: Request,
    db: Session,
    auth: CurrentAuth,
    event_type: str,
    target_type: str,
    target_id: int | str | None,
    details: dict | None = None,
) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="project_lifecycle",
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )


@router.get("/public/feedback/{token}")
def public_feedback_form(token: str, db: Session = Depends(get_db)):
    try:
        return public_feedback_payload(db, token=token)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Feedback link is invalid or unavailable") from exc


@router.post("/public/feedback/{token}", status_code=status.HTTP_201_CREATED)
def public_feedback_submit(
    token: str,
    payload: FeedbackResponseCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    try:
        row = submit_feedback_response(db, token=token, payload=payload)
        record_audit(
            db,
            event_type="CLIENT_FEEDBACK_RESPONSE_SUBMITTED",
            request=request,
            actor_email=str(payload.client_email) if payload.client_email else None,
            module="project_lifecycle",
            target_type="project_feedback_response",
            target_id=row.id,
            details={"project_id": row.project_id, "feedback_request_id": row.feedback_request_id, "response_type": row.response_type},
        )
        db.commit()
        return {"response_id": row.id, "response_type": row.response_type, "received": True}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/public/feedback/{token}/attachments", status_code=status.HTTP_201_CREATED)
async def public_feedback_attachments(
    token: str,
    request: Request,
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files or len(files) > 20:
        raise HTTPException(status_code=422, detail="Attach between 1 and 20 files")
    stored_keys: list[str] = []
    try:
        request_row, response = feedback_response_for_attachment_token(db, token=token)
        existing_count = int(db.scalar(select(func.count(ProjectFeedbackAttachment.id)).where(
            ProjectFeedbackAttachment.feedback_response_id == response.id
        )) or 0)
        if existing_count + len(files) > 20:
            raise ValueError("A feedback response can contain at most 20 attachments")
        validated = []
        for upload in files:
            data = await upload.read(FINANCE_ATTACHMENT_MAX_BYTES + 1)
            validated.append(validate_finance_attachment_bytes(
                filename=upload.filename,
                declared_mime_type=upload.content_type,
                data=data,
            ))
            await upload.close()
        created = []
        for item in validated:
            storage_key = store_finance_attachment(
                request_row.id, item, namespace="client-feedback"
            )
            stored_keys.append(storage_key)
            attachment = ProjectFeedbackAttachment(
                project_id=response.project_id,
                feedback_response_id=response.id,
                original_filename=item.original_filename,
                storage_key=storage_key,
                mime_type=item.mime_type,
                file_size=item.file_size,
                content_sha256=item.content_sha256,
            )
            db.add(attachment)
            db.flush()
            created.append({"id": attachment.id, "filename": attachment.original_filename})
        record_audit(
            db,
            event_type="CLIENT_FEEDBACK_ATTACHMENTS_UPLOADED",
            request=request,
            module="project_lifecycle",
            target_type="project_feedback_response",
            target_id=response.id,
            details={"project_id": response.project_id, "count": len(created)},
        )
        db.commit()
        return {"attachments": created}
    except FinanceAttachmentValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    except FinanceAttachmentStorageError as exc:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        for key in stored_keys:
            delete_finance_attachment_object(key)
        raise _error(exc) from exc


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _roles(auth, "bd", "finance", *TECHNICAL_PM_ROLES, "management", "admin")
    return lifecycle_dashboard(db, actor=auth.user, role=_role(auth))


@router.get("/projects/{project_id}")
def project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "finance", *TECHNICAL_PM_ROLES, "management", "admin")
    try:
        return project_360(db, actor=auth.user, role=_role(auth), project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/feedback-requests", status_code=status.HTTP_201_CREATED)
def feedback_request_create(
    project_id: int,
    payload: FeedbackRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row, token, external_url = create_feedback_request(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "CLIENT_FEEDBACK_REQUEST_SENT", "project_feedback_request", row.id, {
            "project_id": project_id, "request_code": row.request_code, "recipient_email": row.recipient_email
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    send_feedback_request_email(db, request_id=row.id, token=token)
    return {
        "id": row.id,
        "request_code": row.request_code,
        "recipient_email": row.recipient_email,
        "expires_at": row.expires_at.isoformat(),
        "external_url": external_url,
    }


@router.post("/projects/{project_id}/feedback-responses/manual", status_code=status.HTTP_201_CREATED)
def feedback_response_manual_record(
    project_id: int,
    payload: ManualFeedbackResponseCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """BD records an offline client outcome (call, email or letter) that never
    arrived through the secure portal link. Reuses the same BD confirmation /
    classification transitions as a portal response."""
    _roles(auth, "bd", "admin")
    try:
        row = record_manual_feedback_response(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "CLIENT_FEEDBACK_RESPONSE_RECORDED_BY_BD", "project_feedback_response", row.id, {
            "project_id": project_id, "response_type": row.response_type, "source": row.source
        })
        db.commit()
        return {
            "id": row.id,
            "project_id": row.project_id,
            "response_type": row.response_type,
            "source": row.source,
            "classification_status": row.classification_status,
            "workflow_status": CLIENT_ACCEPTANCE_PENDING_BD if row.response_type == "accepted" else FEEDBACK_NEGATIVE,
        }
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/feedback-requests/{request_id}/reminders")
def feedback_request_reminder(
    request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row, token, external_url = send_feedback_reminder(db, actor=auth.user, request_id=request_id)
        _audit(request, db, auth, "CLIENT_FEEDBACK_REMINDER_SENT", "project_feedback_request", row.id, {
            "project_id": row.project_id, "reminder_count": row.reminder_count
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    send_feedback_request_email(db, request_id=row.id, token=token, reminder=True)
    return {"id": row.id, "reminder_count": row.reminder_count, "expires_at": row.expires_at.isoformat(), "external_url": external_url}


@router.post("/feedback-responses/{response_id}/confirm-acceptance")
def feedback_acceptance_confirm(
    response_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = confirm_client_acceptance(db, actor=auth.user, response_id=response_id)
        _audit(request, db, auth, "CLIENT_ACCEPTANCE_CONFIRMED_BY_BD", "project_feedback_response", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "classification_status": row.classification_status, "workflow_status": "READY_FOR_BILLING"}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/feedback-responses/{response_id}/classification")
def feedback_response_classify(
    response_id: int,
    payload: FeedbackClassification,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = classify_feedback_response(db, actor=auth.user, response_id=response_id, payload=payload)
        _audit(request, db, auth, "CLIENT_FEEDBACK_CLASSIFIED", type(row).__name__, row.id, {
            "classification": payload.classification, "project_id": row.project_id
        })
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "classification": payload.classification, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/rework-cycles/{cycle_id}/stage")
def rework_stage_update(
    cycle_id: int,
    payload: ReworkStageUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, "employee", "admin")
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Rework cycle not found")
    ensure_project_department_access(db, auth.user, _role(auth), cycle.project_id)
    try:
        row = advance_rework(db, actor=auth.user, cycle_id=cycle_id, payload=payload)
        _audit(request, db, auth, "REWORK_STAGE_UPDATED", "project_rework_cycle", row.id, {
            "project_id": row.project_id, "stage": payload.stage, "status": row.status
        })
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "cycle_number": row.cycle_number, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/rework-cycles/{cycle_id}/sync")
def rework_cycle_sync(
    cycle_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Idempotent: move the rework cycle to the status its work packages already justify (no rows are duplicated)."""
    _roles(auth, *TECHNICAL_PM_ROLES, "employee", "bd", "admin")
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Rework cycle not found")
    ensure_project_department_access(db, auth.user, _role(auth), cycle.project_id)
    try:
        cycle, before, after = reconcile_rework_cycle(db, actor=auth.user, cycle_id=cycle_id)
        _audit(request, db, auth, "REWORK_CYCLE_RECONCILED", "project_rework_cycle", cycle.id, {
            "project_id": cycle.project_id, "from_status": before, "status": after
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"id": cycle.id, "project_id": cycle.project_id, "cycle_number": cycle.cycle_number, "from_status": before, "status": after, "changed": before != after}


@router.post("/rework-cycles/{cycle_id}/resubmit")
def rework_resubmit(
    cycle_id: int,
    payload: FeedbackRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        cycle, feedback_request, token, external_url = resubmit_rework(
            db, actor=auth.user, cycle_id=cycle_id, payload=payload
        )
        _audit(request, db, auth, "REWORK_RESUBMITTED_TO_CLIENT", "project_rework_cycle", cycle.id, {
            "project_id": cycle.project_id, "feedback_request_id": feedback_request.id
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    send_feedback_request_email(db, request_id=feedback_request.id, token=token)
    return {"cycle_id": cycle.id, "status": cycle.status, "feedback_request_id": feedback_request.id, "external_url": external_url}


@router.post("/feedback-requests/{request_id}/no-feedback-recommendation")
def no_feedback_recommend(
    request_id: int,
    payload: NoFeedbackRecommendation,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = recommend_no_feedback_closure(db, actor=auth.user, request_id=request_id, payload=payload)
        _audit(request, db, auth, "NO_FEEDBACK_CLOSURE_RECOMMENDED", "project_feedback_request", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/feedback-requests/{request_id}/deemed-acceptance")
def deemed_acceptance_authorize(
    request_id: int,
    payload: DeemedAcceptanceCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin")
    try:
        row = authorize_deemed_acceptance(db, actor=auth.user, request_id=request_id, payload=payload)
        _audit(request, db, auth, "DEEMED_ACCEPTANCE_AUTHORIZED", "project_feedback_request", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status, "workflow_status": "READY_FOR_BILLING"}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/change-requests/{change_request_id}/decision")
def change_request_decide(
    change_request_id: int,
    payload: ChangeRequestDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin", "bd", "finance")
    try:
        row = decide_change_request(db, actor=auth.user, change_request_id=change_request_id, payload=payload)
        _audit(request, db, auth, "CHANGE_REQUEST_DECIDED", "project_change_request", row.id, {
            "project_id": row.project_id, "decision": payload.decision
        })
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/projects/{project_id}/invoices/auto-fill")
def invoice_auto_fill_endpoint(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Invoice Generation V2 — Auto Fill mode. Read-only; creates and changes nothing."""
    _roles(auth, "finance", "admin")
    try:
        return invoice_auto_fill(db, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/invoices", status_code=status.HTTP_201_CREATED)
def invoice_create(
    project_id: int,
    payload: InvoiceDraftCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = create_invoice_draft(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_DRAFT_CREATED", "project_invoice", row.id, {"project_id": project_id, "invoice_number": row.invoice_number})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "invoice_number": row.invoice_number, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/invoices/{invoice_id}/document")
def invoice_document_preview(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Canonical read-only payload used by the A4 preview and PDF renderer."""
    _roles(auth, "finance", "management", "admin")
    try:
        payload = invoice_document_payload(db, invoice_id)
        _audit(
            request, db, auth, "INVOICE_GENERATED", "project_invoice", invoice_id,
            {"project_id": payload["invoice"]["project_id"], "format": "preview"},
        )
        db.commit()
        return payload
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/invoices/{invoice_id}/document.pdf")
def invoice_document_pdf(
    invoice_id: int,
    request: Request,
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Render the same canonical payload as A4 PDF, inline for print or as a download."""
    _roles(auth, "finance", "management", "admin")
    try:
        payload = invoice_document_payload(db, invoice_id)
        output = build_invoice_a4_pdf(payload)
        event = "INVOICE_DOWNLOADED" if download else "INVOICE_GENERATED"
        _audit(
            request, db, auth, event, "project_invoice", invoice_id,
            {"project_id": payload["invoice"]["project_id"], "format": "pdf", "download": download},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc

    safe_number = re.sub(r"[^A-Za-z0-9._-]+", "_", payload["invoice"]["invoice_number"]).strip("._") or f"invoice-{invoice_id}"
    disposition = "attachment" if download else "inline"
    return StreamingResponse(
        output,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe_number}_A4_Invoice.pdf"',
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/invoices/{invoice_id}/raise")
def invoice_raise(
    invoice_id: int,
    payload: InvoiceRaise,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = raise_invoice(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_RAISED", "project_invoice", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status, "raised_at": row.raised_at.isoformat() if row.raised_at else None}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/invoices/{invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def invoice_payment(
    invoice_id: int,
    payload: InvoicePaymentCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = record_invoice_payment(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_PAYMENT_RECORDED", "project_invoice_payment", row.id, {
            "project_id": row.project_id, "invoice_id": row.invoice_id, "amount": str(row.amount)
        })
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "invoice_id": row.invoice_id, "amount": float(row.amount)}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/invoices/{invoice_id}/overdue")
def invoice_overdue(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = mark_invoice_overdue(db, actor=auth.user, invoice_id=invoice_id)
        _audit(request, db, auth, "PROJECT_INVOICE_MARKED_OVERDUE", "project_invoice", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/bad-debts")
def bad_debt_register(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "management", "admin")
    return list_bad_debts(db)


@router.post("/invoices/{invoice_id}/bad-debt")
def bad_debt_propose(
    invoice_id: int,
    payload: BadDebtProposalCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = propose_bad_debt(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_BAD_DEBT_PROPOSED", "project_invoice", invoice_id, {"project_id": row.project_id, "bad_debt_id": row.id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "invoice_id": row.invoice_id, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/invoices/{invoice_id}/bad-debt/decision")
def bad_debt_decision(
    invoice_id: int,
    payload: BadDebtDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin")
    try:
        row = decide_bad_debt(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_BAD_DEBT_DECISION", "project_invoice", invoice_id, {"project_id": row.project_id, "bad_debt_id": row.id, "decision": row.status})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "invoice_id": row.invoice_id, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/invoices/{invoice_id}/bad-debt/recovery")
def bad_debt_recovery(
    invoice_id: int,
    payload: BadDebtRecoveryCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Book real cash recovered against an approved Bad Debt write-off."""
    _roles(auth, "finance", "admin")
    try:
        row = record_bad_debt_recovery(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(
            request,
            db,
            auth,
            "PROJECT_INVOICE_BAD_DEBT_RECOVERED",
            "project_invoice",
            invoice_id,
            {"project_id": row.project_id, "bad_debt_id": row.id, "recovered_amount": str(row.recovered_amount)},
        )
        db.commit()
        return {
            "id": row.id,
            "project_id": row.project_id,
            "invoice_id": row.invoice_id,
            "status": row.status,
            "recovered_amount": float(row.recovered_amount or 0),
        }
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/invoices/{invoice_id}/close")
def invoice_close(
    invoice_id: int,
    payload: InvoiceClose,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = close_invoice(db, actor=auth.user, invoice_id=invoice_id, payload=payload)
        _audit(request, db, auth, "PROJECT_INVOICE_CLOSED", "project_invoice", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "status": row.status, "closed_at": row.closed_at.isoformat() if row.closed_at else None}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/projects/{project_id}/messages")
def project_messages(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin", *TECHNICAL_PM_ROLES)
    try:
        rows = list_project_messages(db, actor=auth.user, role=_role(auth), project_id=project_id)
        db.commit()
        return rows
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/projects/{project_id}/messages", status_code=status.HTTP_201_CREATED)
def project_message_create(
    project_id: int,
    payload: ProjectMessageCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin", *TECHNICAL_PM_ROLES)
    try:
        row = create_project_message(db, actor=auth.user, role=_role(auth), project_id=project_id, payload=payload)
        _audit(request, db, auth, "PROJECT_CHAT_MESSAGE_SENT", "project_message", row.id, {"project_id": project_id})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "created_at": row.created_at.isoformat()}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
