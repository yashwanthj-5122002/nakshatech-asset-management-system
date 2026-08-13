from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import Asset, User
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
    return [purchase_request_to_dict(record) for record in records]


@router.get("/purchase-requests/{request_id}", response_model=PurchaseRequestResponse)
def get_purchase_request(
    request_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    record = db.get(ITPurchaseRequest, request_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    return purchase_request_to_dict(record, include_history=True)


@router.post("/purchase-requests", response_model=PurchaseRequestResponse)
def add_purchase_request(
    payload: PurchaseRequestCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    record = create_purchase_request(db, payload, user)
    return purchase_request_to_dict(record, include_history=True)


@router.put("/purchase-requests/{request_id}/resubmit", response_model=PurchaseRequestResponse)
def resubmit_request(
    request_id: int,
    payload: PurchaseRequestResubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    record = resubmit_purchase_request(db, request_id, payload, user)
    return purchase_request_to_dict(record, include_history=True)


@router.post("/purchase-requests/{request_id}/decision", response_model=PurchaseRequestResponse)
def make_purchase_request_decision(
    request_id: int,
    payload: PurchaseRequestDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    record = decide_purchase_request(db, request_id, payload, user)
    return purchase_request_to_dict(record, include_history=True)


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
