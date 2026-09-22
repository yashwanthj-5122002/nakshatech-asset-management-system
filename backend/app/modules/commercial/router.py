from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import TECHNICAL_PM_ROLES
from app.core.roles import role_is_allowed
from app.modules.commercial.fx_service import FxUnavailableError
from app.modules.commercial.models import (
    ProjectCommercialAttachment,
    ProjectCommercialEstimateRevision,
    ProjectExpense,
    ProjectVendorInvoice,
)
from app.modules.commercial.schemas import (
    AttachmentMetadataInput,
    BillingBasisInput,
    CommercialEstimateDecision,
    CommercialEstimateInput,
    FxPreviewRequest,
    ProjectExpenseDecision,
    ProjectExpenseDeclarationInput,
    ProjectExpenseInput,
    ProjectExpenseReimbursement,
    VendorInvoiceInput,
    VendorPaymentInput,
)
from app.modules.commercial.service import (
    attachment_payload,
    billing_recommendation,
    list_billing_basis,
    pm_billing_basis_view,
    record_billing_basis,
    create_estimate_revision,
    create_project_expense,
    create_vendor_invoice,
    currencies_payload,
    decide_estimate_revision,
    decide_project_expense,
    declare_project_expenses,
    fx_preview,
    list_estimates,
    list_estimate_queue,
    list_project_expenses,
    list_vendor_invoices,
    management_analytics,
    project_cost_summary,
    record_vendor_payment,
    reimburse_project_expense,
    submit_baseline_estimate,
    submit_project_expense,
    update_project_expense,
    upsert_baseline_estimate,
    validate_attachment_owner,
)
from app.modules.employee_portal.service import record_audit
from app.modules.finance.attachments import (
    FINANCE_ATTACHMENT_MAX_BYTES,
    FinanceAttachmentStorageError,
    FinanceAttachmentValidationError,
    delete_finance_attachment_object,
    store_finance_attachment,
    stream_finance_attachment,
    validate_finance_attachment_bytes,
)

router = APIRouter(prefix="/commercial", tags=["Project Commercial and Cost Control"])


def _role(auth: CurrentAuth) -> str:
    return (auth.effective_role or "").strip().lower()


def _service_role(auth: CurrentAuth) -> str:
    # Software Team inherits Admin permissions throughout the application.
    return "admin" if _role(auth) == "software_team" else _role(auth)


def _roles(auth: CurrentAuth, *roles: str) -> None:
    if not role_is_allowed(_role(auth), set(roles)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this commercial action")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, HTTPException):
        return exc
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, FxUnavailableError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc), "attempts": exc.attempts},
        )
    if isinstance(exc, FinanceAttachmentValidationError):
        return HTTPException(status_code=exc.status_code, detail=str(exc))
    if isinstance(exc, FinanceAttachmentStorageError):
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    if isinstance(exc, FileNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment content was not found")
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
        module="project_commercial",
        target_type=target_type,
        target_id=target_id,
        details=details or {},
    )


def _authorize_attachment(
    db: Session,
    *,
    auth: CurrentAuth,
    project_id: int,
    owner_type: str,
    owner_id: int,
    write: bool,
) -> None:
    validate_attachment_owner(db, project_id=project_id, owner_type=owner_type, owner_id=owner_id)
    role = _service_role(auth)

    if owner_type == "EXPENSE":
        row = db.get(ProjectExpense, owner_id)
        if row is None:
            raise ValueError("Project expense not found")
        if write:
            if role != "admin" and row.employee_id != auth.user.id:
                raise PermissionError("Only the expense owner can upload or remove its receipt")
            if row.status not in {"DRAFT", "RETURNED"} and role != "admin":
                raise ValueError("Expense attachments can be changed only while Draft or Returned")
        elif role not in {"finance", "management", "admin", "bd"} and row.employee_id != auth.user.id:
            raise PermissionError("You cannot view another employee's project-expense attachment")
        return

    if owner_type == "ESTIMATE_REVISION":
        if write:
            _roles(auth, "bd", "admin")
            row = db.get(ProjectCommercialEstimateRevision, owner_id)
            if row is not None and row.is_locked and role != "admin":
                raise ValueError("Locked commercial-estimate attachments cannot be changed")
        else:
            _roles(auth, "bd", "finance", "management", "admin")
        return

    if owner_type == "VENDOR_INVOICE":
        if write:
            _roles(auth, "finance", "admin")
        else:
            _roles(auth, "finance", "management", "admin")
        return

    if owner_type == "CLIENT_INVOICE":
        if write:
            _roles(auth, "finance", "admin")
        else:
            _roles(auth, "bd", "finance", "management", "admin")
        return

    raise ValueError("Unsupported attachment owner type")


@router.get("/currencies")
def currencies(auth: CurrentAuth = Depends(get_current_auth)):
    del auth
    return currencies_payload()


@router.post("/fx/preview")
def preview_fx(payload: FxPreviewRequest, auth: CurrentAuth = Depends(get_current_auth)):
    del auth
    try:
        return fx_preview(
            amount=payload.amount,
            currency_code=payload.currency_code,
            event_date=payload.fx_rate_date or payload.event_date,
            manual_rate=payload.fx_rate_to_inr,
            manual_mode=payload.fx_rate_mode,
            manual_reason=payload.fx_override_reason,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/estimates")
def project_estimates(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "finance", "management", "admin")
    try:
        return list_estimates(db, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.put("/projects/{project_id}/estimates/baseline")
def save_baseline_estimate(
    project_id: int,
    payload: CommercialEstimateInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = upsert_baseline_estimate(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "COMMERCIAL_BASELINE_SAVED", "project_commercial_estimate", row.id, {"project_id": project_id, "revision_no": row.revision_no})
        db.commit()
        return list_estimates(db, project_id=project_id)[0]
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/projects/{project_id}/estimates/baseline/submit")
def submit_baseline(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = submit_baseline_estimate(db, actor=auth.user, project_id=project_id)
        _audit(request, db, auth, "COMMERCIAL_BASELINE_SUBMITTED", "project_commercial_estimate", row.id, {"project_id": project_id})
        db.commit()
        return next(item for item in list_estimates(db, project_id=project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/projects/{project_id}/estimates/revisions", status_code=status.HTTP_201_CREATED)
def new_estimate_revision(
    project_id: int,
    payload: CommercialEstimateInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "bd", "admin")
    try:
        row = create_estimate_revision(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "COMMERCIAL_REVISION_SUBMITTED", "project_commercial_estimate", row.id, {"project_id": project_id, "revision_no": row.revision_no})
        db.commit()
        return next(item for item in list_estimates(db, project_id=project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/estimates/revisions/queue")
def estimate_revision_queue(
    queue_status: str = Query(default="PENDING_APPROVAL", alias="status"),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    allowed = {"PENDING_APPROVAL", "RETURNED", "APPROVED", "REJECTED"}
    normalized = queue_status.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported commercial revision queue status")
    return list_estimate_queue(db, statuses=(normalized,))


@router.post("/estimates/revisions/{revision_id}/decision")
def estimate_revision_decision(
    revision_id: int,
    payload: CommercialEstimateDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = decide_estimate_revision(db, actor=auth.user, revision_id=revision_id, payload=payload)
        _audit(request, db, auth, f"COMMERCIAL_REVISION_{payload.decision.upper()}", "project_commercial_estimate", row.id, {"project_id": row.project_id, "revision_no": row.revision_no})
        db.commit()
        return next(item for item in list_estimates(db, project_id=row.project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/projects/{project_id}/pm-billing-basis")
def pm_billing_basis(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Assigned Project Manager only. Returns billing type, unit and milestone NAMES: never a rate, value, FX or margin."""
    _roles(auth, *TECHNICAL_PM_ROLES, "admin")
    try:
        return pm_billing_basis_view(db, actor=auth.user, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/pm-billing-basis", status_code=status.HTTP_201_CREATED)
def confirm_pm_billing_basis(
    project_id: int,
    payload: BillingBasisInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, "admin")
    try:
        row = record_billing_basis(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "COMMERCIAL_PM_BILLING_BASIS_CONFIRMED", "project_billing_basis", row.id, {"project_id": project_id, "entry_no": row.entry_no})
        db.commit()
        return next(item for item in list_billing_basis(db, project_id=project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/projects/{project_id}/billing-recommendation")
def project_billing_recommendation(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Finance / BD / Management: approved commercial basis + PM billing basis + recommended taxable amount (advisory)."""
    _roles(auth, "finance", "bd", "management", "admin")
    try:
        return billing_recommendation(db, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/expenses")
def expenses(
    project_id: int | None = Query(default=None, gt=0),
    expense_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        return list_project_expenses(
            db,
            actor=auth.user,
            role=_service_role(auth),
            project_id=project_id,
            status=expense_status,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/expenses", status_code=status.HTTP_201_CREATED)
def create_expense(
    project_id: int,
    payload: ProjectExpenseInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        row = create_project_expense(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "PROJECT_EXPENSE_CREATED", "project_expense", row.id, {"project_id": project_id, "amount_inr": float(row.amount)})
        db.commit()
        return next(item for item in list_project_expenses(db, actor=auth.user, role=_service_role(auth), project_id=project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.put("/expenses/{expense_id}")
def update_expense(
    expense_id: int,
    payload: ProjectExpenseInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        row = update_project_expense(db, actor=auth.user, expense_id=expense_id, payload=payload)
        _audit(request, db, auth, "PROJECT_EXPENSE_UPDATED", "project_expense", row.id, {"project_id": row.project_id, "amount_inr": float(row.amount)})
        db.commit()
        return next(item for item in list_project_expenses(db, actor=auth.user, role=_service_role(auth), project_id=row.project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/expenses/{expense_id}/submit")
def submit_expense(
    expense_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        row = submit_project_expense(db, actor=auth.user, expense_id=expense_id)
        _audit(request, db, auth, "PROJECT_EXPENSE_SUBMITTED", "project_expense", row.id, {"project_id": row.project_id})
        db.commit()
        return next(item for item in list_project_expenses(db, actor=auth.user, role=_service_role(auth), project_id=row.project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/expenses/{expense_id}/finance-decision")
def expense_finance_decision(
    expense_id: int,
    payload: ProjectExpenseDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = decide_project_expense(db, actor=auth.user, expense_id=expense_id, payload=payload)
        _audit(request, db, auth, f"PROJECT_EXPENSE_{payload.decision.upper()}", "project_expense", row.id, {"project_id": row.project_id, "approved_amount_inr": float(row.approved_amount) if row.approved_amount is not None else None})
        db.commit()
        return next(item for item in list_project_expenses(db, actor=auth.user, role=_service_role(auth), project_id=row.project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/expenses/{expense_id}/reimburse")
def mark_expense_reimbursed(
    expense_id: int,
    payload: ProjectExpenseReimbursement,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = reimburse_project_expense(db, actor=auth.user, expense_id=expense_id, payload=payload)
        _audit(request, db, auth, "PROJECT_EXPENSE_REIMBURSED", "project_expense", row.id, {"project_id": row.project_id, "reference": row.reimbursement_reference})
        db.commit()
        return next(item for item in list_project_expenses(db, actor=auth.user, role=_service_role(auth), project_id=row.project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/projects/{project_id}/expenses/declaration")
def expense_declaration(
    project_id: int,
    payload: ProjectExpenseDeclarationInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        row = declare_project_expenses(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "PROJECT_EXPENSE_DECLARATION", "project_expense_declaration", row.id, {"project_id": project_id, "phase_key": row.phase_key, "status": row.declaration_status})
        db.commit()
        return {
            "id": row.id,
            "project_id": row.project_id,
            "employee_id": row.employee_id,
            "phase_key": row.phase_key,
            "declaration_status": row.declaration_status,
            "declared_at": row.declared_at.isoformat(),
        }
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/vendor-invoices")
def vendor_invoices(
    project_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "management", "admin")
    try:
        return list_vendor_invoices(db, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/vendor-invoices", status_code=status.HTTP_201_CREATED)
def new_vendor_invoice(
    project_id: int,
    payload: VendorInvoiceInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = create_vendor_invoice(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "VENDOR_INVOICE_CREATED", "project_vendor_invoice", row.id, {"project_id": project_id, "currency": row.currency_code, "gross_amount": float(row.gross_amount)})
        db.commit()
        return next(item for item in list_vendor_invoices(db, project_id=project_id) if item["id"] == row.id)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/vendor-invoices/{vendor_invoice_id}/payments", status_code=status.HTTP_201_CREATED)
def new_vendor_payment(
    vendor_invoice_id: int,
    payload: VendorPaymentInput,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "admin")
    try:
        row = record_vendor_payment(db, actor=auth.user, vendor_invoice_id=vendor_invoice_id, payload=payload)
        _audit(request, db, auth, "VENDOR_PAYMENT_RECORDED", "project_vendor_payment", row.id, {"project_id": row.project_id, "vendor_invoice_id": row.vendor_invoice_id, "amount": float(row.amount), "amount_inr": float(row.amount_inr)})
        db.commit()
        return {
            "id": row.id,
            "vendor_invoice_id": row.vendor_invoice_id,
            "project_id": row.project_id,
            "amount": float(row.amount),
            "amount_inr": float(row.amount_inr),
            "payment_date": row.payment_date.isoformat(),
            "payment_reference": row.payment_reference,
            "payment_mode": row.payment_mode,
        }
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.get("/projects/{project_id}/cost-summary")
def cost_summary(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "finance", "management", "admin")
    try:
        return project_cost_summary(db, project_id=project_id)
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/management/analytics")
def commercial_analytics(
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = Query(default=None, gt=0),
    display_currency: str = Query(default="INR", min_length=3, max_length=3),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, "management", "admin")
    try:
        return management_analytics(
            db,
            date_from=date_from,
            date_to=date_to,
            project_id=project_id,
            display_currency=display_currency,
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.post("/projects/{project_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    project_id: int,
    request: Request,
    owner_type: str = Form(...),
    owner_id: int = Form(...),
    doc_type: str = Form("OTHER"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    storage_key: str | None = None
    try:
        meta = AttachmentMetadataInput(owner_type=owner_type, owner_id=owner_id, doc_type=doc_type)
        _authorize_attachment(
            db,
            auth=auth,
            project_id=project_id,
            owner_type=meta.owner_type,
            owner_id=meta.owner_id,
            write=True,
        )
        data = await file.read(FINANCE_ATTACHMENT_MAX_BYTES + 1)
        validated = validate_finance_attachment_bytes(
            filename=file.filename,
            declared_mime_type=file.content_type,
            data=data,
        )
        await file.close()
        storage_key = store_finance_attachment(
            meta.owner_id,
            validated,
            namespace=f"commercial-{meta.owner_type.lower()}",
        )
        row = ProjectCommercialAttachment(
            project_id=project_id,
            owner_type=meta.owner_type,
            owner_id=meta.owner_id,
            doc_type=meta.doc_type,
            original_filename=validated.original_filename,
            storage_key=storage_key,
            mime_type=validated.mime_type,
            file_size=validated.file_size,
            content_sha256=validated.content_sha256,
            uploaded_by_id=auth.user.id,
        )
        db.add(row)
        db.flush()
        _audit(request, db, auth, "COMMERCIAL_ATTACHMENT_UPLOADED", "project_commercial_attachment", row.id, {"project_id": project_id, "owner_type": row.owner_type, "owner_id": row.owner_id, "doc_type": row.doc_type})
        db.commit()
        return attachment_payload(row)
    except Exception as exc:
        db.rollback()
        if storage_key:
            delete_finance_attachment_object(storage_key)
        raise _error(exc) from exc


@router.get("/projects/{project_id}/attachments")
def list_attachments(
    project_id: int,
    owner_type: str = Query(...),
    owner_id: int = Query(..., gt=0),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    try:
        meta = AttachmentMetadataInput(owner_type=owner_type, owner_id=owner_id, doc_type="OTHER")
        _authorize_attachment(
            db,
            auth=auth,
            project_id=project_id,
            owner_type=meta.owner_type,
            owner_id=meta.owner_id,
            write=False,
        )
        rows = list(db.scalars(select(ProjectCommercialAttachment).where(
            ProjectCommercialAttachment.project_id == project_id,
            ProjectCommercialAttachment.owner_type == meta.owner_type,
            ProjectCommercialAttachment.owner_id == meta.owner_id,
        ).order_by(ProjectCommercialAttachment.created_at.desc())).all())
        return [attachment_payload(row) for row in rows]
    except Exception as exc:
        raise _error(exc) from exc


@router.get("/attachments/{attachment_id}/content")
def attachment_content(
    attachment_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    row = db.get(ProjectCommercialAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Commercial attachment not found")
    try:
        _authorize_attachment(
            db,
            auth=auth,
            project_id=row.project_id,
            owner_type=row.owner_type,
            owner_id=row.owner_id,
            write=False,
        )
        content_disposition = f"inline; filename*=UTF-8''{quote(row.original_filename)}"
        return StreamingResponse(
            stream_finance_attachment(row.storage_key),
            media_type=row.mime_type,
            headers={"Content-Disposition": content_disposition},
        )
    except Exception as exc:
        raise _error(exc) from exc


@router.delete("/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_attachment(
    attachment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    row = db.get(ProjectCommercialAttachment, attachment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Commercial attachment not found")
    storage_key = row.storage_key
    try:
        _authorize_attachment(
            db,
            auth=auth,
            project_id=row.project_id,
            owner_type=row.owner_type,
            owner_id=row.owner_id,
            write=True,
        )
        _audit(request, db, auth, "COMMERCIAL_ATTACHMENT_DELETED", "project_commercial_attachment", row.id, {"project_id": row.project_id, "owner_type": row.owner_type, "owner_id": row.owner_id})
        db.delete(row)
        db.commit()
        delete_finance_attachment_object(storage_key)
        return None
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
