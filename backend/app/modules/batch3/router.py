from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.api.router import (
    _next_code,
    _record_history,
    _replacement_response,
    create_asset as legacy_create_asset,
)
from app.core.database import get_db
from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import Asset, ReplacementRecord, User
from app.modules.batch3.models import ReplacementWorkflowState
from app.modules.batch3.service import (
    acquire_asset_code_lock,
    approve_replacement_batch3,
    complete_monthly_activity_data,
    enrich_external_hdd_import_actor,
    create_purchase_record_batch3,
    get_or_create_replacement_state,
    reconciliation_report,
    record_import_audit,
    snapshot_assets,
)
from app.modules.it_activity.models import ITPurchaseRequest
from app.modules.it_activity.schemas import PurchaseCreate, PurchaseResponse
from app.schemas.asset import AssetCreate, AssetResponse
from app.schemas.replacement import ReplacementApproval, ReplacementCreate
from app.services.approval_notification_service import notify_management_approval_required
from app.services.approval_workflow_service import WORKFLOW_REPLACEMENT, record_approval_history
from app.services.excel_import_service import (
    import_assets_workbook,
    import_external_hdd_assets_workbook,
    import_printer_assets_workbook,
)


router = APIRouter(tags=["Batch 3 Complete"])


@router.post("/assets", response_model=AssetResponse)
def create_asset_batch3(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    acquire_asset_code_lock(db)
    return legacy_create_asset(payload, db, user)


@router.post("/imports/assets.xlsx")
async def import_assets_batch3(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Excel file is larger than 25 MB")
    acquire_asset_code_lock(db)
    before = snapshot_assets(db)
    result = import_assets_workbook(db, content)
    result.update(record_import_audit(
        db,
        before=before,
        user=user,
        source_label="Asset Excel Import",
        update_change_type="asset_import_update",
        source_sheet=result.get("sheet"),
    ))
    return result


@router.post("/imports/printers.xlsx")
async def import_printers_batch3(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx printer register")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Printer Excel file is larger than 10 MB")
    acquire_asset_code_lock(db)
    before = snapshot_assets(db)
    try:
        result = import_printer_assets_workbook(db, content, performed_by=user.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result.update(record_import_audit(
        db,
        before=before,
        user=user,
        source_label="Printer Excel Import",
        update_change_type="printer_import_update",
        source_sheet=result.get("sheet"),
    ))
    return result


@router.post("/imports/external-hdds.xlsx")
async def import_external_hdds_batch3(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx External HDD register")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="External HDD Excel file is larger than 10 MB")
    acquire_asset_code_lock(db)
    try:
        result = import_external_hdd_assets_workbook(db, content, performed_by=user.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result["audit_actor_enriched"] = enrich_external_hdd_import_actor(
        db, user=user, source_sheet=result.get("sheet")
    )
    return result


@router.post("/replacements")
def create_replacement_batch3(
    payload: ReplacementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    acquire_asset_code_lock(db)
    old_asset = db.scalar(select(Asset).where(Asset.id == payload.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=404, detail="Old asset not found")
    existing = db.scalar(
        select(ReplacementRecord.id)
        .where(
            ReplacementRecord.old_asset_id == old_asset.id,
            ReplacementRecord.approval_status.in_(["pending", "returned"]),
        )
        .limit(1)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This asset already has an active replacement request")

    if payload.new_asset_id is not None:
        candidate = db.scalar(select(Asset).where(Asset.id == payload.new_asset_id).with_for_update())
        if candidate is None:
            raise HTTPException(status_code=404, detail="Selected replacement asset was not found")
        if candidate.id == old_asset.id:
            raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
        if candidate.status != "available":
            raise HTTPException(status_code=400, detail="Selected replacement asset is not available")
        if candidate.device_type != old_asset.device_type:
            raise HTTPException(status_code=400, detail="Replacement asset must use the same device type as the old asset")

    previous_status = old_asset.status
    values = payload.model_dump()
    values["reporting_month"] = normalize_reporting_month(values.get("reporting_month"))
    record = ReplacementRecord(
        replacement_code=_next_code(db, ReplacementRecord, ReplacementRecord.replacement_code, "RPL"),
        **values,
        requested_by_user_id=user.id,
        requested_by=user.full_name,
        requested_by_email=user.email,
        requested_by_role=user.role,
        approval_status="pending",
    )
    old_asset.status = "replacement_pending"
    db.add(record)
    db.flush()
    get_or_create_replacement_state(db, record, old_asset, previous_status=previous_status)
    record_approval_history(
        db,
        workflow_type=WORKFLOW_REPLACEMENT,
        record_id=record.id,
        record_code=record.replacement_code,
        action="submitted",
        from_status=None,
        to_status="pending",
        user=user,
        remarks=payload.reason,
    )
    notify_management_approval_required(
        db,
        workflow="replacement",
        record_id=record.id,
        record_code=record.replacement_code,
        reporting_month=record.reporting_month,
        submitted_by_name=user.full_name,
        event_token=record.created_at,
    )
    _record_history(
        db,
        old_asset,
        "Replacement requested",
        user,
        old_value=previous_status,
        new_value="replacement_pending",
        remarks=payload.reason,
        change_type="replacement_requested",
        reason=payload.reason,
        batch_code=record.replacement_code,
        field_count=1,
        reporting_month=record.reporting_month,
    )
    db.commit()
    db.refresh(record)
    return _replacement_response(record)


@router.patch("/replacements/{replacement_id}")
def decide_replacement_batch3(
    replacement_id: int,
    payload: ReplacementApproval,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    record = approve_replacement_batch3(
        db,
        replacement_id=replacement_id,
        approval_status=payload.approval_status,
        selected_new_asset_id=payload.new_asset_id,
        final_action=payload.final_action,
        remarks=payload.remarks,
        user=user,
    )
    return _replacement_response(record)


@router.post("/it-activity/purchases", response_model=PurchaseResponse)
def create_purchase_batch3(
    payload: PurchaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    return create_purchase_record_batch3(db, payload, user)


@router.get("/it-activity/summary")
def recent_changes_batch3(
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
    return complete_monthly_activity_data(
        db,
        month,
        department=department,
        device_category=device_category,
        changed_by=changed_by,
        action_type=action_type,
        search=search,
        limit=limit,
    )


@router.get("/batch3/reconciliation")
def batch3_reconciliation(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    return reconciliation_report(db)


@router.get("/batch3/replacements/{replacement_id}/lifecycle")
def batch3_replacement_lifecycle(
    replacement_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    state = db.scalar(select(ReplacementWorkflowState).where(
        ReplacementWorkflowState.replacement_record_id == replacement_id
    ))
    if state is None:
        raise HTTPException(status_code=404, detail="Batch 3 replacement lifecycle state was not found")
    request = db.get(ITPurchaseRequest, state.purchase_request_id) if state.purchase_request_id else None
    spare = db.get(Asset, state.spare_asset_id) if state.spare_asset_id else None
    return {
        "replacement_record_id": replacement_id,
        "previous_asset_status": state.previous_asset_status,
        "procurement_mode": state.procurement_mode,
        "spare_asset_id": state.spare_asset_id,
        "spare_asset_code": spare.asset_code if spare else None,
        "purchase_request_id": state.purchase_request_id,
        "purchase_request_code": request.request_code if request else None,
        "purchase_request_status": request.status if request else None,
        "updated_at": state.updated_at,
    }
