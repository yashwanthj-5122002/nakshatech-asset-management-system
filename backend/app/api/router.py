from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from io import BytesIO
from ipaddress import ip_address as parse_ip_address
import json
import re

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.models.entities import Asset, AssetHistory, ComponentReplacement, Drone, DroneLocation, MonthlySnapshotRun, ReplacementRecord, User, WorkRecord
from app.schemas.asset import (
    AssetAssignment, AssetCreate, AssetResponse, AssetReturn, AssetStatusUpdate, AssetUpdate,
)
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.schemas.drone import DroneLocationCreate, DroneLocationResponse
from app.schemas.component_replacement import ComponentChangeBatchCreate, ComponentChangeBatchResponse, ComponentReplacementCreate, ComponentReplacementResponse
from app.schemas.replacement import ReplacementApproval, ReplacementCreate, ReplacementResponse
from app.schemas.work import WorkRecordCreate, WorkRecordResponse, WorkRecordUpdate
from app.services.excel_import_service import import_assets_workbook
from app.services.excel_service import (
    build_asset_report, build_dashboard_report, build_monthly_asset_report,
    build_monthly_change_history_report, build_monthly_summary_report,
    build_replacement_history_report, build_upload_template,
)
from app.services.monthly_snapshot_service import (
    assets_for_month, available_months, ensure_previous_month_snapshot, finalize_month_snapshot,
    month_end, month_start, parse_month_key,
)

router = APIRouter()
VALID_ROLES = {"admin", "management", "it", "drone"}
VALID_WORK_MODULES = {"it", "drone"}
VALID_STATUSES = {
    "available", "assigned", "in_use", "wfh", "field_deployment", "under_inspection", "repair",
    "replacement_pending", "replaced", "damaged", "beyond_repair", "returned", "missing", "retired",
    "for_parts", "disposal_pending", "disposed",
}

COMPONENT_FIELD_MAP = {
    "monitor": "monitor_asset_tags",
    "mouse": "mouse_asset_tag",
    "keyboard": "keyboard_asset_tag",
    "processor": "processor",
    "memory": "memory_gb",
    "ram": "memory_gb",
    "ssd": "ssd",
    "hdd": "hdd",
    "graphics card": "graphics_card",
    "gpu": "graphics_card",
    "network type": "network_type",
    "ip address": "ip_address",
    "mac address": "mac_address",
    "operating system": "operating_system",
    "os": "operating_system",
    "antivirus": "antivirus",
    "used by": "used_by",
    "department": "department",
    "workstation": "workstation_no",
    "workstation no": "workstation_no",
    "price": "price",
    "approved by": "approved_by",
    "remarks": "remarks",
}
COMPONENT_TAG_FIELDS = {"monitor_asset_tags", "mouse_asset_tag", "keyboard_asset_tag"}


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[int, list[WebSocket]] = {}

    async def connect(self, drone_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.setdefault(drone_id, []).append(websocket)

    def disconnect(self, drone_id: int, websocket: WebSocket) -> None:
        connections = self.active.get(drone_id, [])
        if websocket in connections:
            connections.remove(websocket)

    async def broadcast(self, drone_id: int, payload: dict) -> None:
        for websocket in list(self.active.get(drone_id, [])):
            try:
                await websocket.send_json(payload)
            except Exception:
                self.disconnect(drone_id, websocket)


manager = ConnectionManager()


def _asset_response(asset: Asset) -> dict:
    return AssetResponse.model_validate(asset).model_dump(mode="json")


def _work_response(work: WorkRecord) -> dict:
    payload = WorkRecordResponse.model_validate(work).model_dump(mode="json")
    payload["asset_code"] = work.asset.asset_code if work.asset else None
    return payload




def _component_replacement_response(record: ComponentReplacement) -> dict:
    return ComponentReplacementResponse(
        id=record.id,
        replacement_code=record.replacement_code,
        asset_id=record.asset_id,
        asset_code=record.asset.asset_code,
        cpu_asset_tag=record.cpu_asset_tag,
        workstation_no=record.workstation_no,
        component_type=record.component_type,
        change_type=record.change_type or "replacement",
        batch_code=record.batch_code,
        sequence_no=record.sequence_no or 1,
        field_name=record.field_name,
        old_value=record.old_value,
        new_value=record.new_value,
        reason=record.reason,
        old_condition=record.old_condition,
        technician=record.technician,
        replacement_date=record.replacement_date,
        performed_by=record.performed_by,
        approved_by=record.approved_by,
        remarks=record.remarks,
        work_record_id=record.work_record_id,
        work_code=record.work_record.work_code if record.work_record else None,
        created_at=record.created_at,
    ).model_dump(mode="json")


def _replacement_response(record: ReplacementRecord) -> dict:
    return ReplacementResponse(
        id=record.id,
        replacement_code=record.replacement_code,
        old_asset_id=record.old_asset_id,
        old_asset_code=record.old_asset.asset_code,
        new_asset_id=record.new_asset_id,
        new_asset_code=record.new_asset.asset_code if record.new_asset else None,
        reason=record.reason,
        damage_category=record.damage_category,
        inspection_finding=record.inspection_finding,
        approval_status=record.approval_status,
        final_action=record.final_action,
        requested_by=record.requested_by,
        approved_by=record.approved_by,
        created_at=record.created_at,
        approved_at=record.approved_at,
    ).model_dump(mode="json")


def _next_code(db: Session, model, field, prefix: str) -> str:
    codes = db.scalars(select(field).where(field.like(f"{prefix}-%"))).all()
    highest = 0
    for code in codes:
        match = re.search(r"(\d+)$", code)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}-{highest + 1:04d}"


ASSIGNED_STATUSES = {"assigned", "in_use", "wfh", "field_deployment"}
FINAL_STATUSES = {"replaced", "retired", "disposed", "missing"}
WORK_MODES = {"office", "wfh", "field"}
IGNORED_UNIQUE_TAGS = {"OWN", "N/A", "NA", "-", "--"}
ASSET_EDIT_FIELDS = [
    "used_by", "workstation_no", "department", "cpu_asset_tag", "monitor_asset_tags",
    "mouse_asset_tag", "keyboard_asset_tag", "system_name", "device_type", "processor",
    "memory_gb", "ssd", "hdd", "ip_address", "mac_address", "graphics_card",
    "operating_system", "antivirus", "network_type", "approved_by", "price", "remarks",
    "asset_date", "location", "work_mode", "status",
]


def _normalised(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _asset_state(asset: Asset) -> dict:
    return {field: getattr(asset, field) for field in ASSET_EDIT_FIELDS}


def _serialise_changes(changes: dict) -> str:
    return json.dumps(changes, default=str, ensure_ascii=False)


def _validate_asset_data(db: Session, values: dict, exclude_asset_id: int | None = None) -> None:
    status = str(values.get("status") or "available").strip().lower()
    if status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid asset status")
    device_type = str(values.get("device_type") or "").strip()
    if device_type not in {"Computer", "Laptop", "Smartphone", "Printer", "Server", "Network Device", "Other"}:
        raise HTTPException(status_code=400, detail="Select a valid device type")
    work_mode = str(values.get("work_mode") or "office").strip().lower()
    if work_mode not in WORK_MODES:
        raise HTTPException(status_code=400, detail="Work mode must be office, wfh or field")

    used_by = _normalised(values.get("used_by"))
    department = _normalised(values.get("department"))
    workstation = _normalised(values.get("workstation_no"))
    if status == "available" and used_by:
        raise HTTPException(
            status_code=400,
            detail="Available assets cannot have an employee. A workstation may be recorded for physical placement.",
        )
    if status in ASSIGNED_STATUSES and (not used_by or not department or not workstation):
        raise HTTPException(
            status_code=400,
            detail="Assigned, in-use, WFH and field assets require Used By, Department and Workstation Number.",
        )

    ip_value = _normalised(values.get("ip_address"))
    network_type = str(values.get("network_type") or "").strip().lower()
    if ip_value and ip_value.lower() not in {"dynamic", "dhcp", "-"}:
        try:
            parse_ip_address(ip_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Enter a valid IP address, for example 192.168.1.100") from exc

    mac_value = _normalised(values.get("mac_address"))
    if mac_value and not re.fullmatch(r"(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", mac_value):
        raise HTTPException(status_code=400, detail="Enter a valid MAC address, for example AA:BB:CC:DD:EE:01")

    def ensure_unique(field, value: str | None, label: str) -> None:
        if not value or value.upper() in IGNORED_UNIQUE_TAGS:
            return
        query = select(Asset.id).where(func.lower(field) == value.lower())
        if exclude_asset_id is not None:
            query = query.where(Asset.id != exclude_asset_id)
        if db.scalar(query.limit(1)):
            raise HTTPException(status_code=409, detail=f"{label} already exists: {value}")

    ensure_unique(Asset.cpu_asset_tag, _normalised(values.get("cpu_asset_tag")), "CPU / Asset Tag")
    ensure_unique(Asset.mac_address, mac_value, "MAC address")
    if ip_value and "static" in network_type:
        ensure_unique(Asset.ip_address, ip_value, "Static IP address")


def _record_history(
    db: Session,
    asset: Asset,
    action: str,
    changed_by: str,
    old_value: str | None = None,
    new_value: str | None = None,
    remarks: str | None = None,
) -> None:
    db.add(
        AssetHistory(
            asset_id=asset.id,
            action=action,
            old_value=old_value,
            new_value=new_value,
            remarks=remarks,
            changed_by=changed_by,
        )
    )


@router.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "nakshatech-asset-management-backend"}


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    requested_role = payload.role.lower().strip() if payload.role else None
    if requested_role and requested_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role selected")
    user = db.scalar(select(User).where(func.lower(User.email) == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if requested_role and user.role != requested_role:
        raise HTTPException(status_code=403, detail=f"This account is registered as {user.role.title()}, not {requested_role.title()}")
    token = create_access_token(user.email, user.role)
    return LoginResponse(
        access_token=token,
        user=UserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            branch=user.branch,
        ),
    )


@router.get("/auth/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, role=user.role, branch=user.branch)


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    assets = list(db.scalars(select(Asset)).all())
    drones = list(db.scalars(select(Drone)).all())
    pending_work = db.scalar(select(func.count(WorkRecord.id)).where(WorkRecord.status.in_(["open", "pending", "in_progress"]))) or 0
    return {
        "role": user.role,
        "assets_total": len(assets),
        "available_assets": sum(asset.status == "available" for asset in assets),
        "repair_assets": sum(asset.status == "repair" for asset in assets),
        "drones_total": len(drones),
        "deployed_drones": sum(drone.status == "deployed" for drone in drones),
        "pending_work": pending_work,
    }


@router.get("/dashboard/it")
def it_dashboard(
    month: str | None = Query(default=None, description="Dashboard month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    try:
        selected_start = parse_month_key(month) if month else month_start()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assets, source = assets_for_month(db, selected_start)
    if source == "missing":
        raise HTTPException(status_code=404, detail="No asset register is available for the selected month")

    selected_end = month_end(selected_start)
    start_dt = datetime.combine(selected_start, datetime.min.time())
    end_dt = datetime.combine(selected_end + (date.resolution), datetime.min.time())
    is_live = selected_start == month_start()

    work_query = (
        select(WorkRecord)
        .where(
            WorkRecord.module == "it",
            WorkRecord.created_at >= start_dt,
            WorkRecord.created_at < end_dt,
        )
        .order_by(WorkRecord.created_at.desc())
        .limit(8)
    )
    replacement_query = (
        select(ReplacementRecord)
        .where(ReplacementRecord.created_at >= start_dt, ReplacementRecord.created_at < end_dt)
        .order_by(ReplacementRecord.created_at.desc())
        .limit(6)
    )
    work_records = list(db.scalars(work_query).all()) if source != "template" else []
    replacements = list(db.scalars(replacement_query).all()) if source != "template" else []

    status_counts = Counter(asset.status for asset in assets)
    device_counts = Counter(asset.device_type for asset in assets)
    department_counts = Counter(asset.department or "Unassigned" for asset in assets)
    location_counts = Counter(asset.location or "Unknown" for asset in assets)
    memory_counts = Counter(asset.memory_gb or "Not recorded" for asset in assets)
    os_counts = Counter(asset.operating_system or "Not recorded" for asset in assets)

    ip_counts = Counter(asset.ip_address for asset in assets if asset.ip_address and asset.ip_address not in {"-", "Dynamic"})
    duplicate_ips = sorted([ip for ip, count in ip_counts.items() if count > 1])
    pending_approvals = 0
    component_changes = 0
    complete_replacements = 0
    new_assets = 0
    if source != "template":
        pending_approvals = db.scalar(
            select(func.count(WorkRecord.id)).where(
                WorkRecord.module == "it",
                WorkRecord.approval_status == "pending",
                WorkRecord.created_at >= start_dt,
                WorkRecord.created_at < end_dt,
            )
        ) or 0
        component_changes = db.scalar(
            select(func.count(ComponentReplacement.id)).where(
                ((ComponentReplacement.replacement_date >= selected_start) & (ComponentReplacement.replacement_date <= selected_end))
                | ((ComponentReplacement.replacement_date.is_(None)) & (ComponentReplacement.created_at >= start_dt) & (ComponentReplacement.created_at < end_dt))
            )
        ) or 0
        complete_replacements = db.scalar(
            select(func.count(ReplacementRecord.id)).where(
                ReplacementRecord.created_at >= start_dt,
                ReplacementRecord.created_at < end_dt,
            )
        ) or 0
        new_assets = sum(
            not getattr(asset, "source_sheet", None)
            and getattr(asset, "created_at", start_dt) >= start_dt
            and getattr(asset, "created_at", start_dt) < end_dt
            for asset in assets
        )

    alerts = [
        {"severity": "high", "title": "Replacement pending", "count": status_counts.get("replacement_pending", 0), "filter": "replacement_pending"},
        {"severity": "high", "title": "Assets under repair", "count": status_counts.get("repair", 0), "filter": "repair"},
        {"severity": "medium", "title": "Missing employee assignment", "count": sum(not asset.used_by for asset in assets), "filter": "unassigned"},
        {"severity": "medium", "title": "MAC address not recorded", "count": sum(not asset.mac_address for asset in assets), "filter": "missing_mac"},
        {"severity": "high", "title": "Duplicate IP addresses", "count": len(duplicate_ips), "details": duplicate_ips},
        {"severity": "medium", "title": "Approvals waiting", "count": pending_approvals, "filter": "approval_pending"},
    ]

    return {
        "month": {
            "key": selected_start.strftime("%Y-%m"),
            "label": selected_start.strftime("%B %Y"),
            "status": "live" if is_live else ("finalized" if source == "snapshot" else "historical"),
            "source": source,
            "is_live": is_live,
            "read_only": not is_live,
        },
        "kpis": {
            "total": len(assets),
            "computers": device_counts.get("Computer", 0),
            "laptops": device_counts.get("Laptop", 0),
            "smartphones": device_counts.get("Smartphone", 0),
            "assigned": status_counts.get("assigned", 0) + status_counts.get("in_use", 0),
            "available": status_counts.get("available", 0),
            "repair": status_counts.get("repair", 0),
            "replacement_pending": status_counts.get("replacement_pending", 0),
            "wfh": status_counts.get("wfh", 0),
            "field": status_counts.get("field_deployment", 0),
            "returned": status_counts.get("returned", 0),
            "damaged": status_counts.get("damaged", 0) + status_counts.get("beyond_repair", 0),
        },
        "monthly_activity": {
            "new_assets": new_assets,
            "work_records": len(work_records),
            "component_changes": component_changes,
            "complete_replacements": complete_replacements,
        },
        "device_distribution": [{"name": key, "value": value} for key, value in device_counts.most_common()],
        "status_distribution": [{"name": key.replace("_", " ").title(), "value": value} for key, value in status_counts.most_common()],
        "department_distribution": [{"name": key, "value": value} for key, value in department_counts.most_common(12)],
        "location_distribution": [{"name": key, "value": value} for key, value in location_counts.most_common(8)],
        "memory_distribution": [{"name": key, "value": value} for key, value in memory_counts.most_common(8)],
        "os_distribution": [{"name": key, "value": value} for key, value in os_counts.most_common(8)],
        "alerts": [alert for alert in alerts if alert["count"] > 0],
        "recent_work": [_work_response(work) for work in work_records],
        "recent_replacements": [_replacement_response(record) for record in replacements],
    }


@router.get("/assets")
def list_assets(
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    work_mode: str | None = None,
    month: str | None = Query(default=None, description="Asset register month in YYYY-MM format"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    if not month:
        query = select(Asset)
        if search:
            pattern = f"%{search.strip()}%"
            query = query.where(
                or_(
                    Asset.asset_code.ilike(pattern), Asset.used_by.ilike(pattern),
                    Asset.workstation_no.ilike(pattern), Asset.department.ilike(pattern),
                    Asset.cpu_asset_tag.ilike(pattern), Asset.monitor_asset_tags.ilike(pattern),
                    Asset.mouse_asset_tag.ilike(pattern), Asset.keyboard_asset_tag.ilike(pattern),
                    Asset.system_name.ilike(pattern), Asset.ip_address.ilike(pattern),
                    Asset.mac_address.ilike(pattern),
                )
            )
        if department:
            query = query.where(Asset.department == department)
        if device_type:
            query = query.where(Asset.device_type == device_type)
        if status:
            query = query.where(Asset.status == status)
        if work_mode:
            query = query.where(Asset.work_mode == work_mode)
        query = query.order_by(Asset.asset_code).limit(limit)
        return [_asset_response(asset) for asset in db.scalars(query).all()]

    try:
        selected_start = parse_month_key(month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    assets, source = assets_for_month(db, selected_start)
    if source == "missing":
        raise HTTPException(status_code=404, detail="No asset register is available for the selected month")

    query_text = (search or "").strip().lower()
    result = []
    for asset in assets:
        searchable = " ".join(str(value or "") for value in (
            asset.asset_code, asset.used_by, asset.workstation_no, asset.department,
            asset.cpu_asset_tag, asset.monitor_asset_tags, asset.mouse_asset_tag,
            asset.keyboard_asset_tag, asset.system_name, asset.ip_address, asset.mac_address,
        )).lower()
        if query_text and query_text not in searchable:
            continue
        if department and asset.department != department:
            continue
        if device_type and asset.device_type != device_type:
            continue
        if status and asset.status != status:
            continue
        if work_mode and asset.work_mode != work_mode:
            continue
        result.append(_asset_response(asset))
        if len(result) >= limit:
            break
    return result


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    history = list(
        db.scalars(
            select(AssetHistory)
            .where(AssetHistory.asset_id == asset_id)
            .order_by(AssetHistory.created_at.desc())
        ).all()
    )
    works = list(
        db.scalars(
            select(WorkRecord)
            .where(WorkRecord.asset_id == asset_id)
            .order_by(WorkRecord.created_at.desc())
        ).all()
    )
    replacements = list(
        db.scalars(
            select(ReplacementRecord)
            .where(or_(ReplacementRecord.old_asset_id == asset_id, ReplacementRecord.new_asset_id == asset_id))
            .order_by(ReplacementRecord.created_at.desc())
        ).all()
    )
    payload = _asset_response(asset)
    payload["history"] = [
        {
            "action": item.action,
            "old_value": item.old_value,
            "new_value": item.new_value,
            "remarks": item.remarks,
            "changed_by": item.changed_by,
            "created_at": item.created_at.isoformat(),
        }
        for item in history
    ]
    payload["work_records"] = [_work_response(work) for work in works]
    component_replacements = list(
        db.scalars(
            select(ComponentReplacement)
            .where(ComponentReplacement.asset_id == asset_id)
            .order_by(ComponentReplacement.created_at.desc())
        ).all()
    )
    payload["replacement_records"] = [_replacement_response(record) for record in replacements]
    payload["component_replacements"] = [_component_replacement_response(record) for record in component_replacements]
    payload["can_delete_test_record"] = asset.source_sheet is None and any(
        str(value or "").upper().startswith("QA-")
        for value in (asset.cpu_asset_tag, asset.system_name)
    )
    return payload


@router.post("/assets", response_model=AssetResponse)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    values = payload.model_dump()
    values["status"] = str(values.get("status") or "available").lower()
    values["work_mode"] = str(values.get("work_mode") or "office").lower()
    values["performed_by"] = user.full_name
    values["asset_date"] = values.get("asset_date") or date.today()
    _validate_asset_data(db, values)

    prefix = {"computer": "NT-PC", "laptop": "NT-LAP", "smartphone": "NT-MOB"}.get(
        values["device_type"].lower(), "NT-IT"
    )
    code = _next_code(db, Asset, Asset.asset_code, prefix)
    asset = Asset(asset_code=code, **values)
    db.add(asset)
    db.flush()
    _record_history(
        db,
        asset,
        "Asset created",
        user.email,
        new_value=_serialise_changes({"asset_code": code, **values}),
        remarks="Manual asset registration",
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        return asset
    before = _asset_state(asset)
    merged = {**before, **updates}
    merged["status"] = str(merged.get("status") or "available").lower()
    merged["work_mode"] = str(merged.get("work_mode") or "office").lower()
    _validate_asset_data(db, merged, exclude_asset_id=asset.id)
    changed = {}
    for key, value in updates.items():
        old = getattr(asset, key)
        if old != value:
            changed[key] = {"from": old, "to": value}
            setattr(asset, key, value)
    asset.performed_by = user.full_name
    if changed:
        _record_history(
            db,
            asset,
            "Asset details updated",
            user.email,
            old_value=_serialise_changes({key: value["from"] for key, value in changed.items()}),
            new_value=_serialise_changes({key: value["to"] for key, value in changed.items()}),
            remarks=f"Updated fields: {', '.join(changed)}",
        )
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}/status", response_model=AssetResponse)
def update_asset_status(
    asset_id: int,
    payload: AssetStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    next_status = payload.status.strip().lower()
    merged = _asset_state(asset)
    merged["status"] = next_status
    _validate_asset_data(db, merged, exclude_asset_id=asset.id)
    old_status = asset.status
    asset.status = next_status
    if payload.remarks:
        asset.remarks = f"{asset.remarks or ''} | {payload.remarks}".strip(" |")
    _record_history(
        db,
        asset,
        "Status changed",
        user.email,
        old_value=old_status,
        new_value=next_status,
        remarks=payload.remarks,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/assets/{asset_id}/assign", response_model=AssetResponse)
def assign_asset(
    asset_id: int,
    payload: AssetAssignment,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    if asset.status in FINAL_STATUSES:
        raise HTTPException(status_code=400, detail=f"A {asset.status.replace('_', ' ')} asset cannot be assigned")
    work_mode = payload.work_mode.strip().lower()
    status = {"office": "assigned", "wfh": "wfh", "field": "field_deployment"}.get(work_mode)
    if not status:
        raise HTTPException(status_code=400, detail="Work mode must be office, wfh or field")
    old_assignment = {
        "used_by": asset.used_by,
        "department": asset.department,
        "workstation_no": asset.workstation_no,
        "location": asset.location,
        "status": asset.status,
    }
    asset.used_by = payload.used_by.strip()
    asset.department = payload.department.strip()
    asset.workstation_no = _normalised(payload.workstation_no)
    asset.location = _normalised(payload.location) or asset.location or "Head Office"
    asset.work_mode = work_mode
    asset.status = status
    asset.asset_date = payload.assigned_date or asset.asset_date or date.today()
    _validate_asset_data(db, _asset_state(asset), exclude_asset_id=asset.id)
    _record_history(
        db,
        asset,
        "Asset assigned / transferred",
        user.email,
        old_value=_serialise_changes(old_assignment),
        new_value=_serialise_changes({
            "used_by": asset.used_by,
            "department": asset.department,
            "workstation_no": asset.workstation_no,
            "location": asset.location,
            "work_mode": asset.work_mode,
            "status": asset.status,
        }),
        remarks=payload.remarks,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/assets/{asset_id}/return", response_model=AssetResponse)
def return_asset(
    asset_id: int,
    payload: AssetReturn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    final_status = payload.final_status.strip().lower()
    if final_status not in {"available", "repair", "damaged", "returned"}:
        raise HTTPException(status_code=400, detail="Return status must be available, repair, damaged or returned")
    old_assignment = {
        "used_by": asset.used_by,
        "department": asset.department,
        "workstation_no": asset.workstation_no,
        "work_mode": asset.work_mode,
        "status": asset.status,
    }
    asset.used_by = None
    asset.workstation_no = None
    asset.work_mode = "office"
    asset.status = final_status
    note = f"Returned on {payload.return_date or date.today()}; condition: {payload.condition}; all components returned: {'Yes' if payload.all_components_returned else 'No'}"
    if payload.remarks:
        note = f"{note}; {payload.remarks}"
    asset.remarks = f"{asset.remarks or ''} | {note}".strip(" |")
    _record_history(
        db,
        asset,
        "Asset returned",
        user.email,
        old_value=_serialise_changes(old_assignment),
        new_value=_serialise_changes({"used_by": None, "workstation_no": None, "status": final_status}),
        remarks=note,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}/archive", response_model=AssetResponse)
def archive_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    old_status = asset.status
    asset.status = "retired"
    asset.used_by = None
    asset.workstation_no = None
    _record_history(db, asset, "Asset archived / retired", user.email, old_value=old_status, new_value="retired")
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/assets/{asset_id}", status_code=204)
def delete_test_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    is_qa = asset.source_sheet is None and any(
        str(value or "").upper().startswith("QA-") for value in (asset.cpu_asset_tag, asset.system_name)
    )
    if not is_qa:
        raise HTTPException(
            status_code=400,
            detail="Only manually created QA test assets can be permanently deleted. Retire or dispose real assets instead.",
        )
    db.execute(delete(ComponentReplacement).where(ComponentReplacement.asset_id == asset.id))
    db.execute(delete(WorkRecord).where(WorkRecord.asset_id == asset.id))
    db.execute(
        delete(ReplacementRecord).where(
            or_(ReplacementRecord.old_asset_id == asset.id, ReplacementRecord.new_asset_id == asset.id)
        )
    )
    db.execute(delete(AssetHistory).where(AssetHistory.asset_id == asset.id))
    db.delete(asset)
    db.commit()
    return None


@router.get("/work-records")
def list_work_records(
    module: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    query = select(WorkRecord).order_by(WorkRecord.created_at.desc())
    effective_module = module
    if user.role in {"it", "drone"}:
        effective_module = user.role
    if effective_module:
        query = query.where(WorkRecord.module == effective_module)
    return [_work_response(record) for record in db.scalars(query).all()]


@router.post("/work-records")
def create_work_record(
    payload: WorkRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    module = payload.module.strip().lower()
    if module not in VALID_WORK_MODULES:
        raise HTTPException(status_code=400, detail="Work module must be IT or Drone")
    if user.role in {"it", "drone"} and module != user.role:
        raise HTTPException(status_code=403, detail="You can create work only for your department")
    asset = db.get(Asset, payload.asset_id) if payload.asset_id else None
    if payload.asset_id and not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    prefix = "ITW" if module == "it" else "DRW"
    work = WorkRecord(
        work_code=_next_code(db, WorkRecord, WorkRecord.work_code, prefix),
        **payload.model_dump(),
        status="open",
    )
    db.add(work)
    db.flush()
    if asset:
        _record_history(
            db,
            asset,
            "Work record created",
            user.email,
            new_value=work.work_code,
            remarks=f"{work.work_type}: {work.title}",
        )
    db.commit()
    db.refresh(work)
    return _work_response(work)


@router.patch("/work-records/{work_id}")
def update_work_record(
    work_id: int,
    payload: WorkRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    work = db.get(WorkRecord, work_id)
    if not work:
        raise HTTPException(status_code=404, detail="Work record not found")
    if user.role in {"it", "drone"} and work.module != user.role:
        raise HTTPException(status_code=403, detail="You cannot update another department's work")
    values = payload.model_dump(exclude_unset=True)
    old_status = work.status
    changed = {}
    for key, value in values.items():
        old = getattr(work, key)
        if old != value:
            changed[key] = {"from": old, "to": value}
            setattr(work, key, value)
    if payload.status == "completed":
        work.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if work.asset and changed:
        _record_history(
            db,
            work.asset,
            "Work record updated",
            user.email,
            old_value=_serialise_changes({"work_code": work.work_code, "status": old_status}),
            new_value=_serialise_changes({"work_code": work.work_code, **{k: v["to"] for k, v in changed.items()}}),
            remarks=work.resolution or work.issue_description,
        )
    db.commit()
    db.refresh(work)
    return _work_response(work)


@router.get("/component-replacements")
def list_component_replacements(
    asset_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    query = select(ComponentReplacement).order_by(ComponentReplacement.created_at.desc())
    if asset_id is not None:
        query = query.where(ComponentReplacement.asset_id == asset_id)
    return [_component_replacement_response(record) for record in db.scalars(query).all()]


def _active_component_tag_owner(db: Session, tag: str, exclude_asset_id: int | None = None) -> Asset | None:
    normalised = tag.strip().lower()
    if not normalised or normalised in {"-", "own", "na", "n/a", "not recorded", "not previously recorded"}:
        return None
    for candidate in db.scalars(select(Asset)).all():
        if exclude_asset_id is not None and candidate.id == exclude_asset_id:
            continue
        values = [candidate.mouse_asset_tag, candidate.keyboard_asset_tag]
        values.extend(part.strip() for part in (candidate.monitor_asset_tags or "").split(","))
        if any(str(value or "").strip().lower() == normalised for value in values):
            return candidate
    return None


@router.post("/component-replacements/batch")
def create_component_change_batch(
    payload: ComponentChangeBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    asset = db.get(Asset, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    batch_code = _next_code(db, ComponentReplacement, ComponentReplacement.batch_code, "CHG")
    state = _asset_state(asset)
    prepared: list[dict] = []
    used_fields: set[str] = set()
    reserved_new_tags: set[str] = set()

    for index, item in enumerate(payload.items, start=1):
        component_key = item.component_type.strip().lower()
        field_name = COMPONENT_FIELD_MAP.get(component_key)
        if not field_name:
            raise HTTPException(status_code=400, detail=f"Unsupported component or field: {item.component_type}")
        if field_name != "monitor_asset_tags" and field_name in used_fields:
            raise HTTPException(status_code=400, detail=f"{item.component_type} was added more than once in the same change record")
        used_fields.add(field_name)

        row_change_type = item.change_type or payload.change_type
        if payload.change_type != "upgrade_replacement":
            row_change_type = payload.change_type
        if row_change_type not in {"upgrade", "replacement", "upgrade_replacement"}:
            raise HTTPException(status_code=400, detail="Invalid change type")

        new_value_text = str(item.new_value).strip()
        if not new_value_text:
            raise HTTPException(status_code=400, detail=f"New value is required for {item.component_type}")
        current_value = state.get(field_name)
        supplied_old = (item.old_value or "").strip()
        old_value_for_history = supplied_old or (
            str(current_value).strip() if current_value not in (None, "") else "Not Previously Recorded"
        )
        if supplied_old and supplied_old.lower() == new_value_text.lower():
            raise HTTPException(status_code=400, detail=f"Old and new values cannot be the same for {item.component_type}")

        if field_name in COMPONENT_TAG_FIELDS:
            tag_key = new_value_text.lower()
            if tag_key in reserved_new_tags:
                raise HTTPException(status_code=409, detail=f"Component tag {new_value_text} is repeated in this change record")
            reserved_new_tags.add(tag_key)
            current_tags = [str(state.get("mouse_asset_tag") or "").strip(), str(state.get("keyboard_asset_tag") or "").strip()]
            current_tags.extend(part.strip() for part in str(state.get("monitor_asset_tags") or "").split(",") if part.strip())
            old_key = supplied_old.lower() if supplied_old else ""
            conflict = next((tag for tag in current_tags if tag.lower() == tag_key and tag.lower() != old_key), None)
            if conflict:
                raise HTTPException(status_code=409, detail=f"Component tag {new_value_text} is already active on this system")
            owner = _active_component_tag_owner(db, new_value_text, exclude_asset_id=asset.id)
            if owner:
                raise HTTPException(status_code=409, detail=f"Component tag {new_value_text} is already active on CPU / Asset Tag {owner.cpu_asset_tag or owner.asset_code}")

        if field_name == "monitor_asset_tags":
            monitor_tags = [part.strip() for part in str(current_value or "").split(",") if part.strip()]
            if supplied_old and supplied_old.lower() not in {"not recorded", "not previously recorded", "-"}:
                match_index = next((i for i, tag in enumerate(monitor_tags) if tag.lower() == supplied_old.lower()), None)
                if match_index is None:
                    raise HTTPException(status_code=400, detail=f"Old monitor tag {supplied_old} is not currently linked to this system")
                monitor_tags[match_index] = new_value_text
            else:
                monitor_tags.append(new_value_text)
            updated_value = ", ".join(dict.fromkeys(monitor_tags))
        elif field_name == "price":
            try:
                updated_value = float(new_value_text.replace(",", ""))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Price must be a valid number") from exc
        else:
            updated_value = new_value_text

        if field_name != "monitor_asset_tags" and str(current_value or "").strip().lower() == str(updated_value).strip().lower():
            raise HTTPException(status_code=400, detail=f"{item.component_type} already has the entered value")

        state[field_name] = updated_value
        prepared.append({
            "sequence_no": index,
            "component_type": item.component_type,
            "change_type": row_change_type,
            "field_name": field_name,
            "old_value": old_value_for_history,
            "new_value": new_value_text,
            "updated_value": updated_value,
            "reason": item.reason,
            "old_condition": item.old_condition,
        })

    _validate_asset_data(db, state, exclude_asset_id=asset.id)
    work_type_label = {
        "upgrade": "Multi-component Upgrade",
        "replacement": "Multi-component Replacement",
        "upgrade_replacement": "Upgrade and Replacement",
    }[payload.change_type]
    work = WorkRecord(
        work_code=_next_code(db, WorkRecord, WorkRecord.work_code, "ITW"),
        module="it",
        asset_id=asset.id,
        title=f"{work_type_label} for {asset.cpu_asset_tag or asset.asset_code} / {asset.workstation_no or 'workstation not recorded'}",
        work_type=work_type_label,
        assigned_to=asset.used_by,
        technician=payload.technician or user.full_name,
        priority="medium",
        issue_description="; ".join(f"{row['component_type']}: {row['reason']}" for row in prepared),
        details=json.dumps(prepared, ensure_ascii=False, default=str),
        status="completed",
        root_cause="Multiple component or configuration changes recorded",
        resolution="; ".join(f"{row['component_type']}: {row['old_value']} -> {row['new_value']}" for row in prepared),
        replaced_component=", ".join(row["component_type"] for row in prepared),
        approval_status="not_required",
        start_date=payload.replacement_date or date.today(),
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(work)
    db.flush()

    records: list[ComponentReplacement] = []
    for row in prepared:
        record = ComponentReplacement(
            replacement_code=_next_code(db, ComponentReplacement, ComponentReplacement.replacement_code, "CR"),
            batch_code=batch_code,
            sequence_no=row["sequence_no"],
            change_type=row["change_type"],
            asset_id=asset.id,
            work_record_id=work.id,
            cpu_asset_tag=asset.cpu_asset_tag,
            workstation_no=asset.workstation_no,
            component_type=row["component_type"],
            field_name=row["field_name"],
            old_value=row["old_value"],
            new_value=row["new_value"],
            reason=row["reason"],
            old_condition=row["old_condition"],
            technician=payload.technician or user.full_name,
            replacement_date=payload.replacement_date or date.today(),
            performed_by=user.full_name,
            approved_by=payload.approved_by,
            remarks=payload.remarks,
        )
        db.add(record)
        db.flush()
        records.append(record)

    changed_fields = {}
    for row in prepared:
        field_name = row["field_name"]
        changed_fields[field_name] = {"from": row["old_value"], "to": row["new_value"]}
        setattr(asset, field_name, state[field_name])
    asset.performed_by = user.full_name
    _record_history(
        db,
        asset,
        "Multi-component upgrade / replacement",
        user.email,
        old_value=_serialise_changes({key: value["from"] for key, value in changed_fields.items()}),
        new_value=_serialise_changes({key: value["to"] for key, value in changed_fields.items()}),
        remarks=f"Batch {batch_code}; Work record {work.work_code}; {payload.remarks or work_type_label}",
    )
    db.commit()
    for record in records:
        db.refresh(record)
    return ComponentChangeBatchResponse(
        batch_code=batch_code,
        work_code=work.work_code,
        asset_id=asset.id,
        asset_code=asset.asset_code,
        cpu_asset_tag=asset.cpu_asset_tag,
        workstation_no=asset.workstation_no,
        change_type=payload.change_type,
        records=[ComponentReplacementResponse(**_component_replacement_response(record)) for record in records],
    ).model_dump(mode="json")


@router.post("/component-replacements")
def create_component_replacement(
    payload: ComponentReplacementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    asset = db.get(Asset, payload.asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    component_key = payload.component_type.strip().lower()
    field_name = COMPONENT_FIELD_MAP.get(component_key)
    if not field_name:
        raise HTTPException(status_code=400, detail="Select a supported component or configuration field")

    new_value_text = str(payload.new_value).strip()
    if not new_value_text:
        raise HTTPException(status_code=400, detail="New value is required")

    current_value = getattr(asset, field_name)
    supplied_old = (payload.old_value or "").strip()
    old_value_for_history = supplied_old or (str(current_value).strip() if current_value not in (None, "") else "Not Previously Recorded")
    if supplied_old and supplied_old.lower() == new_value_text.lower():
        raise HTTPException(status_code=400, detail="Old and new values cannot be the same")

    if field_name in COMPONENT_TAG_FIELDS:
        selected_old_tag = (supplied_old or (str(current_value or "") if field_name != "monitor_asset_tags" else "")).strip().lower()
        same_asset_tags = [str(asset.mouse_asset_tag or "").strip(), str(asset.keyboard_asset_tag or "").strip()]
        same_asset_tags.extend(part.strip() for part in str(asset.monitor_asset_tags or "").split(",") if part.strip())
        conflicting_same_asset = next(
            (tag for tag in same_asset_tags if tag.lower() == new_value_text.lower() and tag.lower() != selected_old_tag),
            None,
        )
        if conflicting_same_asset:
            raise HTTPException(
                status_code=409,
                detail=f"Component tag {new_value_text} is already active on this same CPU / Asset Tag as another component",
            )
        owner = _active_component_tag_owner(db, new_value_text, exclude_asset_id=asset.id)
        if owner:
            raise HTTPException(
                status_code=409,
                detail=f"Component tag {new_value_text} is already active on CPU / Asset Tag {owner.cpu_asset_tag or owner.asset_code}",
            )

    if field_name == "monitor_asset_tags":
        current_tags = [part.strip() for part in str(current_value or "").split(",") if part.strip()]
        if supplied_old and supplied_old.lower() not in {"not recorded", "not previously recorded", "-"}:
            match_index = next((i for i, tag in enumerate(current_tags) if tag.lower() == supplied_old.lower()), None)
            if match_index is None:
                raise HTTPException(status_code=400, detail=f"Old monitor tag {supplied_old} is not currently linked to this asset")
            current_tags[match_index] = new_value_text
        else:
            current_tags.append(new_value_text)
        updated_value = ", ".join(dict.fromkeys(current_tags))
    elif field_name == "price":
        try:
            updated_value = float(new_value_text.replace(",", ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Price must be a valid number") from exc
    else:
        updated_value = new_value_text

    if field_name != "monitor_asset_tags" and str(current_value or "").strip().lower() == str(updated_value).strip().lower():
        raise HTTPException(status_code=400, detail="Old and new values cannot be the same")

    merged = _asset_state(asset)
    merged[field_name] = updated_value
    _validate_asset_data(db, merged, exclude_asset_id=asset.id)

    work = WorkRecord(
        work_code=_next_code(db, WorkRecord, WorkRecord.work_code, "ITW"),
        module="it",
        asset_id=asset.id,
        title=f"{payload.component_type} change for {asset.cpu_asset_tag or asset.asset_code} / {asset.workstation_no or 'workstation not recorded'}",
        work_type="Component Replacement" if field_name in COMPONENT_TAG_FIELDS or component_key in {"processor", "memory", "ram", "ssd", "hdd", "graphics card", "gpu"} else "Configuration Change",
        assigned_to=asset.used_by,
        technician=payload.technician or user.full_name,
        priority="medium",
        issue_description=payload.reason,
        details=f"Old: {old_value_for_history}; New: {new_value_text}",
        status="completed",
        root_cause=payload.reason,
        resolution=f"{payload.component_type}: {old_value_for_history} -> {new_value_text}",
        replaced_component=payload.component_type,
        replacement_asset_tag=new_value_text if field_name in COMPONENT_TAG_FIELDS else None,
        approval_status="not_required",
        start_date=payload.replacement_date or date.today(),
        completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(work)
    db.flush()

    record = ComponentReplacement(
        replacement_code=_next_code(db, ComponentReplacement, ComponentReplacement.replacement_code, "CR"),
        asset_id=asset.id,
        work_record_id=work.id,
        cpu_asset_tag=asset.cpu_asset_tag,
        workstation_no=asset.workstation_no,
        component_type=payload.component_type,
        change_type=payload.change_type,
        batch_code=None,
        sequence_no=1,
        field_name=field_name,
        old_value=old_value_for_history,
        new_value=new_value_text,
        reason=payload.reason,
        old_condition=payload.old_condition,
        technician=payload.technician or user.full_name,
        replacement_date=payload.replacement_date or date.today(),
        performed_by=user.full_name,
        approved_by=payload.approved_by,
        remarks=payload.remarks,
    )
    db.add(record)
    setattr(asset, field_name, updated_value)
    asset.performed_by = user.full_name
    _record_history(
        db,
        asset,
        "Component / configuration changed",
        user.email,
        old_value=_serialise_changes({field_name: old_value_for_history}),
        new_value=_serialise_changes({field_name: new_value_text}),
        remarks=f"{payload.component_type}: {payload.reason}; Work record {work.work_code}",
    )
    db.commit()
    db.refresh(record)
    return _component_replacement_response(record)


@router.get("/replacements")
def list_replacements(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    records = db.scalars(select(ReplacementRecord).order_by(ReplacementRecord.created_at.desc())).all()
    return [_replacement_response(record) for record in records]


@router.post("/replacements")
def create_replacement(
    payload: ReplacementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    old_asset = db.get(Asset, payload.old_asset_id)
    if not old_asset:
        raise HTTPException(status_code=404, detail="Old asset not found")
    new_asset = db.get(Asset, payload.new_asset_id) if payload.new_asset_id else None
    if new_asset and new_asset.id == old_asset.id:
        raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
    if new_asset and new_asset.status != "available":
        raise HTTPException(status_code=400, detail="Selected replacement asset is not available")
    record = ReplacementRecord(
        replacement_code=_next_code(db, ReplacementRecord, ReplacementRecord.replacement_code, "RPL"),
        **payload.model_dump(),
        requested_by=user.email,
        approval_status="pending",
    )
    old_status = old_asset.status
    old_asset.status = "replacement_pending"
    db.add(record)
    db.flush()
    db.add(
        AssetHistory(
            asset_id=old_asset.id,
            action="Replacement requested",
            old_value=old_status,
            new_value="replacement_pending",
            remarks=payload.reason,
            changed_by=user.email,
        )
    )
    db.commit()
    db.refresh(record)
    return _replacement_response(record)


@router.patch("/replacements/{replacement_id}")
def approve_replacement(
    replacement_id: int,
    payload: ReplacementApproval,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management")),
) -> dict:
    record = db.get(ReplacementRecord, replacement_id)
    if not record:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    record.approval_status = payload.approval_status
    record.approved_by = user.email
    record.approved_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if payload.new_asset_id is not None:
        new_asset = db.get(Asset, payload.new_asset_id)
        if not new_asset:
            raise HTTPException(status_code=404, detail="Replacement asset not found")
        if new_asset.id == record.old_asset_id:
            raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
        if new_asset.status != "available":
            raise HTTPException(status_code=400, detail="Replacement asset must be available")
        record.new_asset_id = new_asset.id
    if payload.final_action:
        record.final_action = payload.final_action

    if payload.approval_status == "approved" and record.final_action == "replace_and_retire" and not record.new_asset:
        raise HTTPException(status_code=400, detail="Select an available replacement asset before approval")

    if payload.approval_status == "approved":
        record.old_asset.status = "replaced"
        if record.new_asset:
            record.new_asset.status = "assigned"
            record.new_asset.used_by = record.old_asset.used_by
            record.new_asset.department = record.old_asset.department
            record.new_asset.location = record.old_asset.location
            record.new_asset.workstation_no = record.old_asset.workstation_no
            record.new_asset.work_mode = record.old_asset.work_mode
            _record_history(
                db,
                record.new_asset,
                "Assigned as replacement asset",
                user.email,
                old_value="available",
                new_value="assigned",
                remarks=f"Replaces {record.old_asset.asset_code}",
            )
        db.add(
            AssetHistory(
                asset_id=record.old_asset.id,
                action="Replacement approved",
                old_value="replacement_pending",
                new_value="replaced",
                remarks=payload.remarks,
                changed_by=user.email,
            )
        )
    elif payload.approval_status == "rejected":
        previous_status = "assigned" if record.old_asset.used_by else "available"
        record.old_asset.status = previous_status
        _record_history(
            db,
            record.old_asset,
            "Replacement rejected",
            user.email,
            old_value="replacement_pending",
            new_value=previous_status,
            remarks=payload.remarks,
        )

    db.commit()
    db.refresh(record)
    return _replacement_response(record)


@router.post("/imports/assets.xlsx")
async def import_assets_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx file")
    content = await file.read()
    if len(content) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Excel file is larger than 25 MB")
    return import_assets_workbook(db, content)


@router.get("/reports/months")
def report_months(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    return available_months(db)


@router.post("/monthly-snapshots/finalize")
def finalize_month(
    month: str | None = Query(default=None, description="Month in YYYY-MM format"),
    replace_existing: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> dict:
    try:
        start = parse_month_key(month) if month else month_start()
        run = finalize_month_snapshot(
            db,
            start,
            finalized_by=user.email,
            source="manual",
            replace_existing=replace_existing,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "month": run.month_start.strftime("%Y-%m"),
        "status": run.status,
        "opening_count": run.opening_count,
        "closing_count": run.closing_count,
        "finalized_by": run.finalized_by,
        "finalized_at": run.finalized_at.isoformat(),
    }


@router.get("/reports/monthly-assets.xlsx")
def monthly_asset_excel_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    ensure_previous_month_snapshot(db)
    try:
        start = parse_month_key(month)
        stream = build_monthly_asset_report(db, month)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    filename = f"NakshaTech Asset Register - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/monthly-changes.xlsx")
def monthly_changes_excel_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        start = parse_month_key(month)
        stream = build_monthly_change_history_report(db, month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"NakshaTech Upgrade Replacement History - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/monthly-summary.xlsx")
def monthly_summary_excel_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        start = parse_month_key(month)
        stream = build_monthly_summary_report(db, month)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"NakshaTech Monthly Asset Summary - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/nakshatech-assets.xlsx")
def nakshatech_asset_excel_report(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_asset_report(db)
    filename = f"NakshaTech Asset Details - {datetime.now().strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/assets.xlsx")
def legacy_asset_excel_report(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    return nakshatech_asset_excel_report(db, user)


@router.get("/reports/dashboard.xlsx")
def dashboard_excel_report(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_dashboard_report(db)
    filename = f"NakshaTech IT Dashboard - {datetime.now().date().isoformat()}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/replacement-history.xlsx")
def replacement_history_excel_report(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_replacement_history_report(db)
    filename = f"NakshaTech Replacement History - {datetime.now().strftime('%B %Y')}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/upload-template.xlsx")
def upload_template(user: User = Depends(require_roles("admin"))) -> StreamingResponse:
    stream = build_upload_template()
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="NakshaTech IT Asset Upload Template.xlsx"'},
    )


@router.get("/drones")
def list_drones(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "drone")),
) -> list[dict]:
    result = []
    for drone in db.scalars(select(Drone).order_by(Drone.asset_code)).all():
        latest = db.scalar(
            select(DroneLocation)
            .where(DroneLocation.drone_id == drone.id)
            .order_by(DroneLocation.recorded_at.desc())
            .limit(1)
        )
        result.append(
            {
                "id": drone.id,
                "asset_code": drone.asset_code,
                "name": drone.name,
                "model": drone.model,
                "pilot": drone.pilot,
                "project": drone.project,
                "status": drone.status,
                "battery_percent": drone.battery_percent,
                "latest_location": DroneLocationResponse.model_validate(latest).model_dump(mode="json") if latest else None,
            }
        )
    return result


@router.post("/drones/{drone_id}/location", response_model=DroneLocationResponse)
async def create_drone_location(
    drone_id: int,
    payload: DroneLocationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "drone")),
) -> DroneLocationResponse:
    drone = db.get(Drone, drone_id)
    if not drone:
        raise HTTPException(status_code=404, detail="Drone not found")
    location = DroneLocation(drone_id=drone_id, **payload.model_dump())
    if payload.battery_percent is not None:
        drone.battery_percent = payload.battery_percent
    db.add(location)
    db.commit()
    db.refresh(location)
    response = DroneLocationResponse.model_validate(location)
    await manager.broadcast(drone_id, response.model_dump(mode="json"))
    return response


@router.websocket("/ws/drones/{drone_id}")
async def drone_location_socket(websocket: WebSocket, drone_id: int) -> None:
    await manager.connect(drone_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(drone_id, websocket)
