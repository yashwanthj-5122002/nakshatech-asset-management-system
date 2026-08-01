from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import User
from app.modules.drone.import_service import ALL_ATTRIBUTE_GROUPS, load_template_bytes
from app.modules.drone.models import (
    DroneAssetAttributeDefinition,
    DroneAssetKit,
    DroneAuditLog,
    DroneImportBatch,
    DroneOperation,
    DroneAssetMovement,
    DroneWorkRecord,
    DroneProject,
    DroneSurveyAsset,
)
from app.modules.drone.schemas import (
    DroneAssetCreate,
    DroneAssetUpdate,
    DroneImportCommitRequest,
    DroneKitCreate,
    DroneProjectCreate,
    DroneProjectUpdate,
    DroneDispatchCreate,
    DroneAssignmentCreate,
    DroneReturnCreate,
    DroneTransferCreate,
    DroneWorkRecordCreate,
    DroneWorkRecordUpdate,
)
from app.modules.drone.service import (
    ASSET_STATUSES,
    PROJECT_STATUSES,
    asset_dict,
    batch_dict,
    commit_import_batch,
    create_import_preview,
    dashboard_data,
    kit_dict,
    next_code,
    project_dict,
    search_entities,
    create_dispatch_operation,
    create_assignment_operation,
    create_return_operation,
    create_transfer_operation,
    operation_dict,
    movement_dict,
    work_record_dict,
    project_detail_dict,
    WORK_STATUSES,
    WORK_PRIORITIES,
    utc_now,
)

router = APIRouter(tags=["Drone and Survey Asset Management"])
VIEW_ROLES = ("admin", "management", "drone")
OPERATE_ROLES = ("admin", "drone")


@router.get("/dashboard")
def drone_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    return dashboard_data(db)


@router.get("/assets")
def list_assets(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    filters = [DroneSurveyAsset.archived_at.is_(None)]
    if search:
        term = f"%{search.strip().lower()}%"
        filters.append(or_(
            func.lower(DroneSurveyAsset.asset_tag).like(term),
            func.lower(func.coalesce(DroneSurveyAsset.imported_equipment_id, "")).like(term),
            func.lower(DroneSurveyAsset.asset_name).like(term),
            func.lower(func.coalesce(DroneSurveyAsset.serial_number, "")).like(term),
            func.lower(func.coalesce(DroneSurveyAsset.model_number, "")).like(term),
            func.lower(func.coalesce(DroneSurveyAsset.manufacturer, "")).like(term),
            func.lower(func.coalesce(DroneSurveyAsset.current_custodian, "")).like(term),
        ))
    if category:
        filters.append(DroneSurveyAsset.category == category)
    if status:
        filters.append(DroneSurveyAsset.current_status == status)
    if project_id is not None:
        filters.append(DroneSurveyAsset.current_project_id == project_id)
    total = db.scalar(select(func.count(DroneSurveyAsset.id)).where(*filters)) or 0
    assets = db.scalars(
        select(DroneSurveyAsset).where(*filters).order_by(DroneSurveyAsset.asset_tag).offset(offset).limit(limit)
    ).all()
    return {"items": [asset_dict(asset, db) for asset in assets], "total": total, "offset": offset, "limit": limit}


@router.post("/assets")
def create_asset(
    payload: DroneAssetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    if payload.current_status not in ASSET_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid Drone asset status")
    if payload.next_calibration_date and payload.last_calibration_date and payload.next_calibration_date < payload.last_calibration_date:
        raise HTTPException(status_code=400, detail="Next calibration date cannot be before last calibration date")
    if payload.serial_number:
        duplicate = db.scalar(select(DroneSurveyAsset.id).where(func.lower(DroneSurveyAsset.serial_number) == payload.serial_number.lower()))
        if duplicate:
            raise HTTPException(status_code=409, detail="Serial number already exists and requires administrator reconciliation")
    from app.modules.drone.service import _prefix
    prefix = _prefix(payload.category, payload.asset_name)
    asset = DroneSurveyAsset(
        asset_tag=next_code(db, DroneSurveyAsset, DroneSurveyAsset.asset_tag, prefix),
        **payload.model_dump(),
        raw_serial_number=payload.serial_number,
        is_serialized=payload.tracking_type == "serialized_asset",
        reconciliation_status="manual",
        source_workbook="Manual Entry",
        source_sheet="Manual Entry",
    )
    db.add(asset)
    db.flush()
    db.add(DroneAuditLog(
        action="asset_created", entity_type="drone_asset", entity_id=asset.id,
        details={"asset_tag": asset.asset_tag, "asset_name": asset.asset_name}, performed_by=user.email,
    ))
    db.commit()
    db.refresh(asset)
    return asset_dict(asset, db)


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    asset = db.get(DroneSurveyAsset, asset_id)
    if not asset or asset.archived_at:
        raise HTTPException(status_code=404, detail="Drone/Survey asset not found")
    return asset_dict(asset, db)


@router.patch("/assets/{asset_id}")
def update_asset(
    asset_id: int,
    payload: DroneAssetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    asset = db.get(DroneSurveyAsset, asset_id)
    if not asset or asset.archived_at:
        raise HTTPException(status_code=404, detail="Drone/Survey asset not found")
    values = payload.model_dump(exclude_unset=True)
    if "current_status" in values and values["current_status"] not in ASSET_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid Drone asset status")
    last_date = values.get("last_calibration_date", asset.last_calibration_date)
    next_date = values.get("next_calibration_date", asset.next_calibration_date)
    if last_date and next_date and next_date < last_date:
        raise HTTPException(status_code=400, detail="Next calibration date cannot be before last calibration date")
    if values.get("serial_number"):
        duplicate = db.scalar(select(DroneSurveyAsset.id).where(
            func.lower(DroneSurveyAsset.serial_number) == values["serial_number"].lower(),
            DroneSurveyAsset.id != asset.id,
        ))
        if duplicate:
            raise HTTPException(status_code=409, detail="Serial number already exists")
    changed = {}
    for field, value in values.items():
        old = getattr(asset, field)
        if old != value:
            changed[field] = {"old": str(old) if old is not None else None, "new": str(value) if value is not None else None}
            setattr(asset, field, value)
    if changed:
        db.add(DroneAuditLog(
            action="asset_updated", entity_type="drone_asset", entity_id=asset.id,
            details=changed, performed_by=user.email,
        ))
    db.commit()
    db.refresh(asset)
    return asset_dict(asset, db)


@router.get("/projects")
def list_projects(
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    filters = [DroneProject.archived_at.is_(None)]
    if search:
        term = f"%{search.strip().lower()}%"
        filters.append(or_(func.lower(DroneProject.project_code).like(term), func.lower(DroneProject.project_name).like(term)))
    if status:
        filters.append(DroneProject.status == status)
    return [project_dict(project) for project in db.scalars(select(DroneProject).where(*filters).order_by(DroneProject.created_at.desc())).all()]


@router.post("/projects")
def create_project(
    payload: DroneProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    if payload.status not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid project status")
    if payload.expected_end_date and payload.start_date and payload.expected_end_date < payload.start_date:
        raise HTTPException(status_code=400, detail="Expected end date cannot be before project start date")
    code = payload.project_code or next_code(db, DroneProject, DroneProject.project_code, "DRN-PRJ")
    if db.scalar(select(DroneProject.id).where(func.lower(DroneProject.project_code) == code.lower())):
        raise HTTPException(status_code=409, detail="Project code already exists")
    project = DroneProject(project_code=code, **payload.model_dump(exclude={"project_code"}))
    db.add(project)
    db.flush()
    db.add(DroneAuditLog(
        action="project_created", entity_type="drone_project", entity_id=project.id,
        details={"project_code": project.project_code, "project_name": project.project_name}, performed_by=user.email,
    ))
    db.commit()
    db.refresh(project)
    return project_dict(project)


@router.get("/kits")
def list_kits(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    kits = db.scalars(select(DroneAssetKit).where(DroneAssetKit.archived_at.is_(None)).order_by(DroneAssetKit.kit_tag)).all()
    return [kit_dict(kit) for kit in kits]


@router.post("/kits")
def create_kit(
    payload: DroneKitCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    tag = payload.kit_tag or next_code(db, DroneAssetKit, DroneAssetKit.kit_tag, "NT-KIT")
    if db.scalar(select(DroneAssetKit.id).where(func.lower(DroneAssetKit.kit_tag) == tag.lower())):
        raise HTTPException(status_code=409, detail="Kit tag already exists")
    kit = DroneAssetKit(kit_tag=tag, **payload.model_dump(exclude={"kit_tag"}))
    db.add(kit)
    db.flush()
    db.add(DroneAuditLog(
        action="kit_created", entity_type="drone_kit", entity_id=kit.id,
        details={"kit_tag": kit.kit_tag, "kit_name": kit.kit_name}, performed_by=user.email,
    ))
    db.commit()
    db.refresh(kit)
    return kit_dict(kit)


@router.post("/import/preview")
async def import_preview(
    file: UploadFile = File(...),
    reporting_month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Upload an .xlsx Drone hardware inventory workbook")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Workbook exceeds the 25 MB pilot import limit")
    try:
        batch = create_import_preview(db, content, file.filename, reporting_month, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return batch_dict(batch)


@router.post("/import/template-preview")
def template_preview(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    batch = create_import_preview(db, load_template_bytes(), "drone_hardware_inventory_template.xlsx", "2026-05", user)
    return batch_dict(batch)


@router.get("/import/batches")
def list_import_batches(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management")),
) -> list[dict]:
    batches = db.scalars(select(DroneImportBatch).order_by(DroneImportBatch.created_at.desc()).limit(50)).all()
    return [batch_dict(batch, include_records=False) for batch in batches]


@router.get("/import/{batch_id}")
def get_import_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management")),
) -> dict:
    batch = db.get(DroneImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Drone import batch not found")
    return batch_dict(batch)


@router.post("/import/{batch_id}/commit")
def commit_import(
    batch_id: int,
    payload: DroneImportCommitRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    batch = db.get(DroneImportBatch, batch_id)
    if not batch:
        raise HTTPException(status_code=404, detail="Drone import batch not found")
    return commit_import_batch(db, batch, user, payload.allow_warnings, payload.selected_row_ids)


@router.get("/search")
def typeahead_search(
    q: str = Query(min_length=1, max_length=120),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    return search_entities(db, q, limit)


@router.get("/attributes")
def attribute_registry(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    definitions = db.scalars(select(DroneAssetAttributeDefinition).order_by(DroneAssetAttributeDefinition.source_sheet, DroneAssetAttributeDefinition.id)).all()
    return {
        "count": len(definitions),
        "expected_count": sum(len(value) for value in ALL_ATTRIBUTE_GROUPS.values()),
        "groups": ALL_ATTRIBUTE_GROUPS,
        "definitions": [
            {
                "source_sheet": item.source_sheet,
                "original_header": item.original_header,
                "display_label": item.display_label,
                "normalized_field": item.normalized_field,
                "data_type": item.data_type,
                "searchable": item.searchable,
                "included_in_excel": item.included_in_excel,
            }
            for item in definitions
        ],
    }


@router.get("/audit")
def audit_log(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management")),
) -> list[dict]:
    records = db.scalars(select(DroneAuditLog).order_by(DroneAuditLog.created_at.desc()).limit(limit)).all()
    return [
        {
            "id": record.id,
            "action": record.action,
            "entity_type": record.entity_type,
            "entity_id": record.entity_id,
            "details": record.details,
            "performed_by": record.performed_by,
            "created_at": record.created_at.isoformat(),
        }
        for record in records
    ]


@router.get("/reports/source-template.xlsx")
def download_source_template(
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(load_template_bytes()),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Hardware-Inventory Sheets - Preserved Template.xlsx"'},
    )


@router.get("/projects/{project_id}")
def get_project_detail(
    project_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    project = db.get(DroneProject, project_id)
    if not project or project.archived_at:
        raise HTTPException(status_code=404, detail="Drone project not found")
    return project_detail_dict(db, project)


@router.patch("/projects/{project_id}")
def update_project(
    project_id: int,
    payload: DroneProjectUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    project = db.get(DroneProject, project_id)
    if not project or project.archived_at:
        raise HTTPException(status_code=404, detail="Drone project not found")
    values = payload.model_dump(exclude_unset=True)
    new_status = values.get("status")
    if new_status and new_status not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid project status")
    start_date = values.get("start_date", project.start_date)
    expected_end = values.get("expected_end_date", project.expected_end_date)
    if start_date and expected_end and expected_end < start_date:
        raise HTTPException(status_code=400, detail="Expected end date cannot be before project start date")
    if new_status == "closed":
        active_assets = db.scalar(select(func.count(DroneSurveyAsset.id)).where(
            DroneSurveyAsset.current_project_id == project.id,
            DroneSurveyAsset.archived_at.is_(None),
        )) or 0
        active_kits = db.scalar(select(func.count(DroneAssetKit.id)).where(
            DroneAssetKit.current_project_id == project.id,
            DroneAssetKit.archived_at.is_(None),
        )) or 0
        open_operations = db.scalar(select(func.count(DroneOperation.id)).where(
            DroneOperation.project_id == project.id,
            DroneOperation.operation_type.in_(("dispatch", "assignment")),
            DroneOperation.status.in_(("active", "partial")),
        )) or 0
        if active_assets or active_kits or open_operations:
            raise HTTPException(
                status_code=409,
                detail="Return or resolve all project assets and open dispatches before closing the project",
            )
    changed = {}
    for field, value in values.items():
        old = getattr(project, field)
        if old != value:
            changed[field] = {"old": str(old) if old is not None else None, "new": str(value) if value is not None else None}
            setattr(project, field, value)
    if new_status == "completed" and not project.actual_completion_date:
        project.actual_completion_date = date.today()
    if new_status == "closed" and not project.closure_date:
        project.closure_date = date.today()
    if changed:
        db.add(DroneAuditLog(
            action="project_updated", entity_type="drone_project", entity_id=project.id,
            details=changed, performed_by=user.email,
        ))
    db.commit(); db.refresh(project)
    return project_detail_dict(db, project)


@router.get("/operations")
def list_operations(
    operation_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    filters = []
    if operation_type:
        filters.append(DroneOperation.operation_type == operation_type)
    if status:
        filters.append(DroneOperation.status == status)
    if project_id is not None:
        filters.append(or_(
            DroneOperation.project_id == project_id,
            DroneOperation.from_project_id == project_id,
            DroneOperation.to_project_id == project_id,
        ))
    operations = db.scalars(
        select(DroneOperation).where(*filters).order_by(DroneOperation.created_at.desc()).limit(limit)
    ).all()
    return [operation_dict(operation) for operation in operations]


@router.get("/operations/{operation_id}")
def get_operation(
    operation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> dict:
    operation = db.get(DroneOperation, operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="Drone operation not found")
    return operation_dict(operation)


@router.post("/operations/dispatch")
def dispatch_assets(
    payload: DroneDispatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    try:
        return create_dispatch_operation(db, payload, user)
    except Exception:
        db.rollback()
        raise


@router.post("/operations/assign")
def assign_assets(
    payload: DroneAssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    try:
        return create_assignment_operation(db, payload, user)
    except Exception:
        db.rollback()
        raise


@router.post("/operations/return")
def return_assets(
    payload: DroneReturnCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    try:
        return create_return_operation(db, payload, user)
    except Exception:
        db.rollback()
        raise


@router.post("/operations/transfer")
def transfer_assets(
    payload: DroneTransferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    try:
        return create_transfer_operation(db, payload, user)
    except Exception:
        db.rollback()
        raise


@router.get("/movements")
def list_movements(
    asset_id: int | None = Query(default=None),
    kit_id: int | None = Query(default=None),
    project_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    filters = []
    if asset_id is not None:
        filters.append(DroneAssetMovement.asset_id == asset_id)
    if kit_id is not None:
        filters.append(DroneAssetMovement.kit_id == kit_id)
    if project_id is not None:
        filters.append(or_(DroneAssetMovement.old_project_id == project_id, DroneAssetMovement.new_project_id == project_id))
    records = db.scalars(
        select(DroneAssetMovement).where(*filters).order_by(DroneAssetMovement.occurred_at.desc()).limit(limit)
    ).all()
    return [movement_dict(record) for record in records]


@router.get("/work-records")
def list_drone_work_records(
    status: str | None = Query(default=None),
    project_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*VIEW_ROLES)),
) -> list[dict]:
    filters = []
    if status:
        filters.append(DroneWorkRecord.status == status)
    if project_id is not None:
        filters.append(DroneWorkRecord.project_id == project_id)
    if search:
        term = f"%{search.strip().lower()}%"
        filters.append(or_(
            func.lower(DroneWorkRecord.work_code).like(term),
            func.lower(DroneWorkRecord.title).like(term),
            func.lower(DroneWorkRecord.work_type).like(term),
            func.lower(func.coalesce(DroneWorkRecord.assigned_to, "")).like(term),
        ))
    records = db.scalars(
        select(DroneWorkRecord).where(*filters).order_by(DroneWorkRecord.created_at.desc()).limit(limit)
    ).all()
    return [work_record_dict(record) for record in records]


@router.post("/work-records")
def create_drone_work_record(
    payload: DroneWorkRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    if payload.status not in WORK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid Drone work status")
    if payload.priority not in WORK_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    if payload.project_id:
        project = db.get(DroneProject, payload.project_id)
        if not project or project.archived_at:
            raise HTTPException(status_code=404, detail="Drone project not found")
    if payload.asset_id and not db.get(DroneSurveyAsset, payload.asset_id):
        raise HTTPException(status_code=404, detail="Drone asset not found")
    if payload.kit_id and not db.get(DroneAssetKit, payload.kit_id):
        raise HTTPException(status_code=404, detail="Drone kit not found")
    record = DroneWorkRecord(
        work_code=next_code(db, DroneWorkRecord, DroneWorkRecord.work_code, "DRW"),
        **payload.model_dump(),
        performed_by=user.email,
    )
    if record.status in {"completed", "closed"}:
        record.completed_at = utc_now()
    db.add(record); db.flush()
    db.add(DroneAuditLog(
        action="work_record_created", entity_type="drone_work_record", entity_id=record.id,
        details={"work_code": record.work_code, "title": record.title}, performed_by=user.email,
    ))
    db.commit(); db.refresh(record)
    return work_record_dict(record)


@router.patch("/work-records/{record_id}")
def update_drone_work_record(
    record_id: int,
    payload: DroneWorkRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*OPERATE_ROLES)),
) -> dict:
    record = db.get(DroneWorkRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Drone work record not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("status") and values["status"] not in WORK_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid Drone work status")
    if values.get("priority") and values["priority"] not in WORK_PRIORITIES:
        raise HTTPException(status_code=400, detail="Invalid priority")
    changed = {}
    for field, value in values.items():
        old = getattr(record, field)
        if old != value:
            changed[field] = {"old": str(old) if old is not None else None, "new": str(value) if value is not None else None}
            setattr(record, field, value)
    if record.status in {"completed", "closed"} and not record.completed_at:
        record.completed_at = utc_now()
    if changed:
        db.add(DroneAuditLog(
            action="work_record_updated", entity_type="drone_work_record", entity_id=record.id,
            details=changed, performed_by=user.email,
        ))
    db.commit(); db.refresh(record)
    return work_record_dict(record)
