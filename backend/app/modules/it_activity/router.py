from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import Asset, User
from app.modules.it_activity.approval_email import (
    approval_result_html,
    approval_review_html,
    channel_for_request,
    consume_channel_for_application_decision,
    enrich_purchase_request_payload,
    issue_purchase_approval_email,
    mark_channel_for_email_decision,
    normalize_approval_email,
    notify_requester_of_decision,
    resolve_approval_token,
)
from app.modules.it_activity.excel_service import (
    EXCEL_MIME,
    build_monthly_it_activity_workbook,
    build_purchase_request_workbook,
)
from app.modules.it_activity.import_service import import_handover_workbook, import_purchase_workbook
from app.modules.it_activity.models import ITHandoverRecord, ITPurchaseRecord, ITPurchaseRequest
from app.modules.it_activity.schemas import (
    HandoverCreate,
    HandoverResponse,
    PurchaseApprovalRecipient,
    PurchaseCreate,
    PurchaseRequestCreate,
    PurchaseRequestDecision,
    PurchaseRequestResponse,
    PurchaseRequestResubmit,
    PurchaseResponse,
)
from app.modules.it_activity.service import (
    create_handover_record,
    hydrate_handover_custody_movements,
    create_purchase_record,
    create_purchase_request,
    decide_purchase_request,
    month_bounds,
    monthly_activity_data,
    purchase_request_query,
    purchase_request_summary,
    purchase_request_to_dict,
    resubmit_purchase_request,
)
from app.services.asset_lifecycle_service import canonical_device_type

router = APIRouter(tags=["IT Activity"])


def _purchase_payload(
    db: Session,
    record: ITPurchaseRequest,
    *,
    include_history: bool = False,
    include_email_activity: bool = False,
) -> dict:
    return enrich_purchase_request_payload(
        db,
        record,
        purchase_request_to_dict(record, include_history=include_history),
        include_email_activity=include_email_activity,
    )


def _required_recipient(name: str | None, email: str | None, *, requester_email: str) -> tuple[str, str]:
    clean_name = (name or "").strip()
    if not clean_name or not (email or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Approval Recipient Name and Approval Email are mandatory for a Purchase Request",
        )
    return clean_name, normalize_approval_email(email or "", requester_email=requester_email)


def _public_error_page(title: str, detail: str) -> str:
    return f"""
<!doctype html>
<html><body style="margin:0;padding:32px;background:#eef4f8;font-family:Arial,Helvetica,sans-serif;color:#183b56;">
<div style="max-width:620px;margin:0 auto;background:#fff;border:1px solid #dbe5ef;border-radius:10px;overflow:hidden;">
<div style="padding:20px 26px;background:#0b6f8f;color:#fff;font-weight:800;letter-spacing:.08em;">NAKSHATECH</div>
<div style="padding:26px;"><h2 style="margin-top:0;">{escape(title)}</h2><p style="line-height:1.6;color:#526579;">{escape(detail)}</p></div>
</div></body></html>
""".strip()


@router.get("/summary")
def activity_summary(
    month: str = Query(..., description="YYYY-MM"),
    department: str | None = None,
    device_category: str | None = None,
    changed_by: str | None = None,
    action_type: str | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=5000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    return monthly_activity_data(
        db,
        month,
        department=department,
        device_category=device_category,
        changed_by=changed_by,
        action_type=action_type,
        search=search,
        limit=limit,
    )


@router.get("/handover-records", response_model=list[HandoverResponse])
def list_handover_records(
    month: str | None = None,
    device_category: str | None = None,
    action_type: str | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[ITHandoverRecord]:
    query = select(ITHandoverRecord)
    if month:
        start, end, _utc_start, _utc_end = month_bounds(month)
        query = query.where(or_(
            ITHandoverRecord.reporting_month == month,
            and_(ITHandoverRecord.reporting_month.is_(None), ITHandoverRecord.activity_date >= start, ITHandoverRecord.activity_date <= end),
        ))
    if device_category:
        query = query.where(ITHandoverRecord.device_category == device_category.strip().lower())
    if action_type:
        query = query.where(ITHandoverRecord.action_type == action_type.strip().lower())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(
            ITHandoverRecord.activity_code.ilike(pattern),
            ITHandoverRecord.employee_name.ilike(pattern),
            ITHandoverRecord.dc_number.ilike(pattern),
            ITHandoverRecord.internal_asset_no.ilike(pattern),
            ITHandoverRecord.serial_number.ilike(pattern),
            ITHandoverRecord.department.ilike(pattern),
        ))
    records = list(db.scalars(
        query.order_by(ITHandoverRecord.activity_date.desc(), ITHandoverRecord.activity_time.desc(), ITHandoverRecord.id.desc()).limit(limit)
    ).all())
    return hydrate_handover_custody_movements(db, records)


@router.get("/custody-employees")
def search_custody_employees(
    search: str = Query(..., min_length=2, max_length=120),
    limit: int = Query(default=15, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> list[dict]:
    """Autocomplete active organization users for Handover/Transfer.

    Manual entry remains supported in the UI for legitimate legacy/external
    custodians that do not yet have an application account.
    """
    query = search.strip().lower()
    if len(query) < 2:
        return []
    pattern = f"%{query}%"
    rows = list(db.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            or_(
                func.lower(func.coalesce(User.full_name, "")).like(pattern),
                func.lower(func.coalesce(User.email, "")).like(pattern),
                func.lower(func.coalesce(User.employee_id, "")).like(pattern),
                func.lower(func.coalesce(User.department, "")).like(pattern),
            ),
        )
        .order_by(User.full_name.asc(), User.email.asc())
        .limit(limit)
    ).all())
    return [
        {
            "id": row.id,
            "full_name": row.full_name,
            "email": row.email,
            "employee_id": row.employee_id,
            "department": row.department,
        }
        for row in rows
    ]


@router.post("/handover-records", response_model=HandoverResponse)
def add_handover_record(
    payload: HandoverCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> ITHandoverRecord:
    # The live custody screen is deliberately limited to Laptop/Desktop assets.
    # Historical Excel imports use their own import endpoint and remain untouched.
    asset = db.get(Asset, payload.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Linked asset was not found")
    canonical = canonical_device_type(asset.device_type)
    if canonical not in {"Computer", "Laptop"}:
        raise HTTPException(
            status_code=400,
            detail="Laptop & Desktop Handover / Return accepts only Laptop and Desktop / Computer assets",
        )
    expected_category = "laptop" if canonical == "Laptop" else "desktop"
    if payload.device_category != expected_category:
        raise HTTPException(
            status_code=400,
            detail=f"Device category must be {expected_category} for the selected asset",
        )

    record = create_handover_record(db, payload, user)
    return hydrate_handover_custody_movements(db, [record])[0]


@router.get("/purchase-requests/summary")
def purchase_requests_summary(
    month: str | None = None,
    department: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    return purchase_request_summary(
        db,
        month,
        department=department,
        priority=priority,
        search=search,
    )


@router.get("/purchase-requests.xlsx")
def download_purchase_requests(
    month: str | None = None,
    status: str | None = None,
    department: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
):
    stream, count = build_purchase_request_workbook(
        db,
        month=month,
        status=status,
        department=department,
        priority=priority,
        search=search,
    )
    suffix = month or "all-months"
    filename = f"NakshaTech Purchase Requests - {suffix}.xlsx"
    return StreamingResponse(
        stream,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{quote(filename)}',
            "X-Row-Counts": f"purchase_requests:{count}",
        },
    )


@router.get("/purchase-requests", response_model=list[PurchaseRequestResponse])
def list_purchase_requests(
    month: str | None = None,
    status: str | None = None,
    department: str | None = None,
    priority: str | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    records = list(db.scalars(
        purchase_request_query(
            month,
            status=status,
            department=department,
            priority=priority,
            search=search,
        )
        .order_by(ITPurchaseRequest.requested_at.desc(), ITPurchaseRequest.id.desc())
        .limit(limit)
    ).unique().all())
    return [_purchase_payload(db, record) for record in records]


@router.get("/purchase-requests/{request_id}", response_model=PurchaseRequestResponse)
def get_purchase_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    record = db.get(ITPurchaseRequest, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.post("/purchase-requests", response_model=PurchaseRequestResponse)
def add_purchase_request(
    payload: PurchaseRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    recipient_name, recipient_email = _required_recipient(
        payload.approval_recipient_name,
        payload.approval_recipient_email,
        requester_email=user.email,
    )
    record = create_purchase_request(db, payload, user)
    issue_purchase_approval_email(db, record, recipient_name, recipient_email)
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.put("/purchase-requests/{request_id}/resubmit", response_model=PurchaseRequestResponse)
def resubmit_request(
    request_id: int,
    payload: PurchaseRequestResubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    existing = db.get(ITPurchaseRequest, request_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    existing_channel = channel_for_request(db, request_id)
    recipient_name = payload.approval_recipient_name or (existing_channel.approver_name if existing_channel else None)
    recipient_email = payload.approval_recipient_email or (existing_channel.approver_email if existing_channel else None)
    recipient_name, recipient_email = _required_recipient(
        recipient_name,
        recipient_email,
        requester_email=existing.requested_by_email,
    )
    record = resubmit_purchase_request(db, request_id, payload, user)
    issue_purchase_approval_email(
        db,
        record,
        recipient_name,
        recipient_email,
        resubmitted=True,
    )
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.post("/purchase-requests/{request_id}/approval-email", response_model=PurchaseRequestResponse)
def set_purchase_approval_email(
    request_id: int,
    payload: PurchaseApprovalRecipient,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    record = db.get(ITPurchaseRequest, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    recipient_name, recipient_email = _required_recipient(
        payload.approval_recipient_name,
        payload.approval_recipient_email,
        requester_email=record.requested_by_email,
    )
    issue_purchase_approval_email(db, record, recipient_name, recipient_email)
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.post("/purchase-requests/{request_id}/approval-email/resend", response_model=PurchaseRequestResponse)
def resend_purchase_approval_email(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    record = db.get(ITPurchaseRequest, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    channel = channel_for_request(db, request_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="This Purchase Request has no approval email recipient")
    issue_purchase_approval_email(db, record, channel.approver_name, channel.approver_email)
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.post("/purchase-requests/{request_id}/decision", response_model=PurchaseRequestResponse)
def make_purchase_request_decision(
    request_id: int,
    payload: PurchaseRequestDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    record = decide_purchase_request(db, request_id, payload, user)
    if channel_for_request(db, record.id) is not None:
        consume_channel_for_application_decision(db, record)
        notify_requester_of_decision(db, record, source="Asset Management System")
    return _purchase_payload(db, record, include_history=True, include_email_activity=True)


@router.get(
    "/purchase-approval-email/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def review_purchase_approval_email(
    token: str,
    action: str = Query(default="approve"),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        channel, record = resolve_approval_token(db, token)
    except HTTPException as exc:
        return HTMLResponse(
            _public_error_page("Purchase approval link unavailable", str(exc.detail)),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )
    return HTMLResponse(
        approval_review_html(record, channel, token, action),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.post(
    "/purchase-approval-email/{token}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def decide_purchase_approval_email(
    token: str,
    action: str = Form(...),
    approved_amount: str = Form(default=""),
    management_remarks: str = Form(default=""),
    db: Session = Depends(get_db),
) -> HTMLResponse:
    try:
        channel, record = resolve_approval_token(db, token)
    except HTTPException as exc:
        return HTMLResponse(
            _public_error_page("Purchase approval link unavailable", str(exc.detail)),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    if record.status != "pending_approval":
        return HTMLResponse(
            approval_result_html(
                record,
                channel,
                title="Decision already completed",
                message=f"This Purchase Request is already {record.status.replace('_', ' ')}. No further decision was recorded.",
            ),
            headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
        )
    if channel.token_consumed_at is not None:
        return HTMLResponse(
            approval_result_html(record, channel, title="Approval link already used", message="This secure approval link has already been consumed."),
            status_code=409,
            headers={"Cache-Control": "no-store"},
        )
    if channel.token_expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
        return HTMLResponse(
            approval_result_html(record, channel, title="Approval link expired", message="This approval link has expired. IT must resend the approval email."),
            status_code=410,
            headers={"Cache-Control": "no-store"},
        )

    normalized_action = action.strip().lower()
    if normalized_action not in {"approve", "send_back", "reject"}:
        return HTMLResponse(_public_error_page("Invalid decision", "Use Approve, Send Back or Reject."), status_code=400)
    remarks = management_remarks.strip() or None
    if normalized_action in {"send_back", "reject"} and not remarks:
        return HTMLResponse(
            _public_error_page("Management remarks required", "Enter a reason before confirming Send Back or Reject."),
            status_code=400,
            headers={"Cache-Control": "no-store"},
        )
    amount: float | None = None
    if normalized_action == "approve":
        try:
            amount = float(approved_amount) if approved_amount.strip() else record.estimated_total_amount
        except ValueError:
            return HTMLResponse(
                _public_error_page("Invalid approved amount", "Approved Amount must be a valid number."),
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )
        if amount is not None and amount < 0:
            return HTMLResponse(
                _public_error_page("Invalid approved amount", "Approved Amount cannot be negative."),
                status_code=400,
                headers={"Cache-Control": "no-store"},
            )

    email_actor = User(
        email=channel.approver_email,
        full_name=channel.approver_name,
        password_hash="email-approval-not-persisted",
        role="management",
        branch=record.branch or "Head Office",
    )
    mark_channel_for_email_decision(db, channel)
    try:
        record = decide_purchase_request(
            db,
            record.id,
            PurchaseRequestDecision(
                action=normalized_action,
                approved_amount=amount,
                management_remarks=remarks,
            ),
            email_actor,
        )
    except HTTPException as exc:
        db.rollback()
        current = db.get(ITPurchaseRequest, record.id)
        current_channel = channel_for_request(db, record.id)
        if current is not None and current_channel is not None and current.status != "pending_approval":
            return HTMLResponse(
                approval_result_html(
                    current,
                    current_channel,
                    title="Decision already completed",
                    message=f"Another valid decision completed this request first. Current status: {current.status.replace('_', ' ')}.",
                ),
                status_code=409,
                headers={"Cache-Control": "no-store"},
            )
        return HTMLResponse(
            _public_error_page("Decision could not be saved", str(exc.detail)),
            status_code=exc.status_code,
            headers={"Cache-Control": "no-store"},
        )

    notify_requester_of_decision(db, record, source="Email Approval")
    final_channel = channel_for_request(db, record.id) or channel
    return HTMLResponse(
        approval_result_html(
            record,
            final_channel,
            title=f"Purchase Request {record.status.replace('_', ' ').title()}",
            message="Your email decision was recorded successfully and the Asset Management System has been updated.",
        ),
        headers={"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"},
    )


@router.get("/purchases", response_model=list[PurchaseResponse])
def list_purchases(
    month: str | None = None,
    search: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[ITPurchaseRecord]:
    query = select(ITPurchaseRecord)
    if month:
        start, end, _utc_start, _utc_end = month_bounds(month)
        query = query.where(or_(
            ITPurchaseRecord.reporting_month == month,
            and_(ITPurchaseRecord.reporting_month.is_(None), ITPurchaseRecord.purchase_date >= start, ITPurchaseRecord.purchase_date <= end),
        ))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(
            ITPurchaseRecord.purchase_code.ilike(pattern),
            ITPurchaseRecord.po_number.ilike(pattern),
            ITPurchaseRecord.asset_number.ilike(pattern),
            ITPurchaseRecord.supplier_name.ilike(pattern),
            ITPurchaseRecord.item_description.ilike(pattern),
            ITPurchaseRecord.warranty_number.ilike(pattern),
            ITPurchaseRecord.department.ilike(pattern),
        ))
    return list(db.scalars(query.order_by(ITPurchaseRecord.purchase_date.desc(), ITPurchaseRecord.id.desc()).limit(limit)).all())


@router.post("/purchases", response_model=PurchaseResponse)
def add_purchase(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> ITPurchaseRecord:
    return create_purchase_record(db, payload, user)


@router.post("/imports/handover.xlsx")
async def import_handover_excel(
    device_category: str = Query(..., pattern="^(laptop|desktop)$"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload an .xlsx workbook")
    content = await file.read()
    return import_handover_workbook(db, content, file.filename or "handover.xlsx", device_category, user)


@router.post("/imports/purchases.xlsx")
async def import_purchase_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload an .xlsx workbook")
    content = await file.read()
    return import_purchase_workbook(db, content, file.filename or "purchases.xlsx", user)


@router.get("/monthly.xlsx")
def download_monthly_activity(
    month: str = Query(..., description="YYYY-MM"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
):
    stream, counts = build_monthly_it_activity_workbook(db, month)
    start, _end, _utc_start, _utc_end = month_bounds(month)
    filename = f"NakshaTech IT Monthly Activity - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type=EXCEL_MIME,
        headers={
            "Content-Disposition": f'attachment; filename*=UTF-8\'\'{quote(filename)}',
            "X-Row-Counts": ",".join(f"{key}:{value}" for key, value in counts.items()),
        },
    )
