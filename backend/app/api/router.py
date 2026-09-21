from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from ipaddress import ip_address as parse_ip_address
import json
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth, get_current_user, require_roles
from app.core.roles import VALID_ROLES, role_display_name
from app.core.management_access import (
    FIRST_LOGIN_PRIVILEGED_ROLES,
    is_authorized_privileged_email,
    management_account_payload,
    privileged_account_payload,
)
from app.core.database import get_db
from app.core.security import create_temporary_token, hash_password, verify_password
from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import (
    Asset, AssetHistory, ComponentReplacement, Drone, DroneLocation, MonthlySnapshotRun,
    ReplacementRecord, User, WorkRecord,
)
from app.schemas.asset import (
    AssetAssignment, AssetCreate, AssetResponse, AssetReturn, AssetStatusUpdate, AssetUpdate,
)
from app.schemas.auth import LoginRequest, LoginResponse, PasswordChangeRequest, ProfileUpdateRequest, UserResponse
from app.schemas.drone import DroneLocationCreate, DroneLocationResponse
from app.schemas.component_replacement import ComponentChangeBatchCreate, ComponentChangeBatchResponse, ComponentReplacementCreate, ComponentReplacementResponse
from app.schemas.replacement import ReplacementApproval, ReplacementCreate, ReplacementResubmit, ReplacementResponse
from app.schemas.work import WorkApprovalDecision, WorkRecordCreate, WorkRecordResponse, WorkRecordUpdate
from app.services.excel_import_service import (
    import_assets_workbook, import_external_hdd_assets_workbook, import_printer_assets_workbook,
)
from app.services.excel_service import (
    build_asset_report, build_dashboard_report, build_monthly_asset_report,
    build_monthly_change_history_report, build_monthly_summary_report,
    build_external_hdd_asset_report, build_printer_asset_report, build_replacement_history_report, build_upload_template,
)
from app.services.monthly_snapshot_service import (
    assets_for_month, available_months, ensure_previous_month_snapshot, finalize_month_snapshot,
    month_end, month_start, parse_month_key,
)
from app.services.periodic_reporting_service import (
    build_complete_period_report, monthly_period, yearly_period,
)
from app.services.asset_drilldown_service import build_asset_drilldown_workbook, query_asset_drilldown
from app.services.asset_lifecycle_service import (
    canonical_device_type,
    device_distribution as canonical_device_distribution,
    inventory_integrity,
    inventory_summary,
    is_primary_device_type,
    is_supported_device_type,
    lifecycle_status_distribution,
    AssetLifecycleTransitionError,
    apply_assignment_transition,
    apply_return_transition,
    custody_state,
)
from app.services.approval_workflow_service import (
    WORKFLOW_IT_WORK,
    WORKFLOW_REPLACEMENT,
    record_approval_history,
    utc_now_naive,
    validate_it_work_operational_transition,
)
from app.services.approval_notification_service import (
    notify_approval_decision,
    notify_management_approval_required,
)
from app.modules.employee_portal.service import (
    create_or_replace_authenticator,
    ensure_allowed_email,
    get_confirmed_authenticator,
    issue_access_for_user,
    record_audit,
)
from app.modules.employee_portal.models import Branch

router = APIRouter()
IST = ZoneInfo("Asia/Kolkata")
VALID_WORK_MODULES = {"it", "drone"}
VALID_STATUSES = {
    "available", "assigned", "in_use", "wfh", "field_deployment", "under_inspection", "repair",
    "replacement_pending", "replaced", "damaged", "beyond_repair", "returned", "missing", "retired",
    "for_parts", "disposal_pending", "disposed", "issued", "permanently_issued",
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
    "brand": "brand",
    "model": "model",
    "serial number": "serial_number",
    "connection type": "connection_type",
    "used by": "used_by",
    "department": "department",
    "workstation": "workstation_no",
    "workstation no": "workstation_no",
    "price": "price",
    "approved by": "approved_by",
    "remarks": "remarks",
    "asset master remarks": "remarks",
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


def _attach_audit_summary(payload: dict, history: AssetHistory | None) -> dict:
    if history is None:
        payload.update({
            "last_change_at": None,
            "last_changed_by": None,
            "last_changed_by_role": None,
            "last_change_type": None,
            "last_change_reason": None,
            "last_field_count": 0,
        })
        return payload
    payload.update({
        "last_change_at": history.created_at.isoformat(),
        "last_changed_by": history.changed_by_name or history.changed_by,
        "last_changed_by_role": history.changed_by_role,
        "last_change_type": history.change_type,
        "last_change_reason": history.reason,
        "last_field_count": history.field_count or _count_changed_fields(history.old_value, history.new_value),
    })
    return payload


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
        performed_by_email=record.performed_by_email,
        performed_by_role=record.performed_by_role,
        approved_by=record.approved_by,
        remarks=record.remarks,
        work_record_id=record.work_record_id,
        work_code=record.work_record.work_code if record.work_record else None,
        reporting_month=record.reporting_month,
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
        requested_by_email=record.requested_by_email,
        requested_by_role=record.requested_by_role,
        approved_by=record.approved_by,
        approved_by_email=record.approved_by_email,
        approved_by_role=record.approved_by_role,
        reporting_month=record.reporting_month,
        created_at=record.created_at,
        approved_at=record.approved_at,
        decision_remarks=record.decision_remarks,
        updated_at=record.updated_at,
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
    "mouse_asset_tag", "keyboard_asset_tag", "system_name", "brand", "model",
    "serial_number", "connection_type", "capacity", "ownership", "client_name", "project_id",
    "current_holder", "device_type", "processor",
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
    if not is_supported_device_type(device_type):
        raise HTTPException(status_code=400, detail="Select a valid device type")
    device_type = canonical_device_type(device_type)
    work_mode = str(values.get("work_mode") or "office").strip().lower()
    if work_mode not in WORK_MODES:
        raise HTTPException(status_code=400, detail="Work mode must be office, wfh or field")

    used_by = _normalised(values.get("used_by"))
    department = _normalised(values.get("department"))
    workstation = _normalised(values.get("workstation_no"))
    location = _normalised(values.get("location"))
    if device_type == "Printer":
        if not _normalised(values.get("brand")) or not _normalised(values.get("model")):
            raise HTTPException(status_code=400, detail="Printer Brand and Model are required.")
    if device_type == "External HDD":
        required = {
            "External HDD Asset ID": _normalised(values.get("cpu_asset_tag")),
            "Brand": _normalised(values.get("brand")),
            "Capacity": _normalised(values.get("capacity")),
            "Serial Number": _normalised(values.get("serial_number")),
            "Ownership": _normalised(values.get("ownership")),
        }
        missing = [label for label, value in required.items() if not value]
        if missing:
            raise HTTPException(status_code=400, detail=f"External HDD requires: {', '.join(missing)}.")
        ownership = str(values.get("ownership") or "").strip().casefold()
        if ownership not in {"nakshatech", "client"}:
            raise HTTPException(status_code=400, detail="External HDD ownership must be NakshaTech or Client.")
        if ownership == "client" and not _normalised(values.get("client_name")):
            raise HTTPException(status_code=400, detail="Client Name is required for a client-owned External HDD.")
        if status in {"in_use", "issued", "permanently_issued"} and not _normalised(values.get("current_holder")):
            raise HTTPException(status_code=400, detail="Current Holder is required for an in-use or issued External HDD.")
    if status == "available" and used_by:
        raise HTTPException(
            status_code=400,
            detail="Available assets cannot have an employee. A workstation may be recorded for physical placement.",
        )
    if status in ASSIGNED_STATUSES:
        if device_type == "External HDD":
            pass
        elif device_type == "Printer":
            if not department or (not used_by and not location):
                raise HTTPException(
                    status_code=400,
                    detail="Assigned printers require Department and either Assigned User or Floor / Location.",
                )
        elif not used_by or not department or not workstation:
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
    ensure_unique(Asset.serial_number, _normalised(values.get("serial_number")), "Serial number")
    ensure_unique(Asset.mac_address, mac_value, "MAC address")
    if ip_value and "static" in network_type:
        ensure_unique(Asset.ip_address, ip_value, "Static IP address")


def _audit_batch_code(prefix: str = "AUD") -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{prefix}-{timestamp}-{uuid4().hex[:8].upper()}"


def _count_changed_fields(old_value: str | None, new_value: str | None) -> int:
    for raw in (new_value, old_value):
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            return len(parsed)
    return 1 if old_value != new_value else 0


def _record_history(
    db: Session,
    asset: Asset,
    action: str,
    changed_by: User | str,
    old_value: str | None = None,
    new_value: str | None = None,
    remarks: str | None = None,
    *,
    change_type: str = "asset_activity",
    reason: str | None = None,
    batch_code: str | None = None,
    field_count: int | None = None,
    reporting_month: str | None = None,
) -> AssetHistory:
    if isinstance(changed_by, User):
        changed_by_email = changed_by.email
        changed_by_name = changed_by.full_name
        changed_by_role = changed_by.role
    else:
        changed_by_email = changed_by
        changed_by_name = None
        changed_by_role = None
    history = AssetHistory(
        asset_id=asset.id,
        action=action,
        change_type=change_type,
        batch_code=batch_code or _audit_batch_code(),
        old_value=old_value,
        new_value=new_value,
        remarks=remarks,
        reason=reason,
        changed_by=changed_by_email,
        changed_by_name=changed_by_name,
        changed_by_role=changed_by_role,
        field_count=field_count if field_count is not None else _count_changed_fields(old_value, new_value),
        reporting_month=normalize_reporting_month(reporting_month),
    )
    db.add(history)
    return history


@router.get("/health")
def health() -> dict:
    return {"status": "healthy", "service": "nakshatech-asset-management-backend"}


@router.get("/auth/management/accounts")
def public_management_accounts() -> dict[str, list[dict[str, str]]]:
    """Backward-compatible Management selector endpoint."""
    return {"accounts": management_account_payload()}


@router.get("/auth/privileged/accounts")
def public_privileged_accounts(role: str = Query(...)) -> dict[str, list[dict[str, str]]]:
    """Return only the authoritative identities for a provisioned role selector."""
    normalized_role = role.strip().lower()
    if normalized_role not in FIRST_LOGIN_PRIVILEGED_ROLES:
        raise HTTPException(status_code=400, detail="This role does not use a provisioned account selector")
    return {"accounts": privileged_account_payload(normalized_role)}


@router.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    requested_role = payload.role.lower().strip() if payload.role else None
    access_mode = (payload.access_mode or "").strip().lower() or None
    if access_mode not in {None, "employee_support"}:
        raise HTTPException(status_code=400, detail="Invalid access mode")
    if requested_role and requested_role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role selected")
    email = ensure_allowed_email(str(payload.email))

    if requested_role in FIRST_LOGIN_PRIVILEGED_ROLES and not is_authorized_privileged_email(requested_role, email):
        record_audit(
            db,
            event_type="LOGIN_FAILED",
            request=request,
            actor_email=email,
            result="failed",
            module="authentication",
            details={"reason": "unauthorized_privileged_identity", "requested_role": requested_role},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail=f"{role_display_name(requested_role)} access is restricted to the authorized account",
        )

    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if not user or not verify_password(payload.password, user.password_hash):
        record_audit(
            db,
            event_type="LOGIN_FAILED",
            request=request,
            actor_email=email,
            result="failed",
            module="authentication",
            details={"reason": "invalid_credentials"},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.role in FIRST_LOGIN_PRIVILEGED_ROLES and not is_authorized_privileged_email(user.role, user.email):
        record_audit(
            db,
            event_type="LOGIN_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
            details={"reason": "disabled_privileged_identity", "stored_role": user.role},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail=f"{role_display_name(user.role)} access is restricted to the authorized account",
        )

    employee_support_mode = access_mode == "employee_support"
    if employee_support_mode and requested_role not in {None, "employee"}:
        raise HTTPException(status_code=400, detail="Employee Login must use the Employee Support role")
    management_as_employee = (
        employee_support_mode
        and user.role == "management"
        and is_authorized_privileged_email("management", user.email)
    )
    if employee_support_mode and user.role not in {"employee", "management"}:
        raise HTTPException(status_code=403, detail="Employee Login is available only to Employee Support users and authorized Management users")
    if management_as_employee and (user.must_change_password or not user.is_active or user.account_status not in {"active", ""}):
        raise HTTPException(status_code=403, detail="Complete the Management account activation before using Employee Login")
    if requested_role and user.role != requested_role and not management_as_employee:
        record_audit(
            db,
            event_type="LOGIN_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
            details={"reason": "role_mismatch", "requested_role": requested_role},
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail=f"This account is registered as {role_display_name(user.role)}, not {role_display_name(requested_role)}",
        )

    effective_role = "employee" if employee_support_mode else user.role
    response_user = UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=effective_role,
        branch=user.branch,
        employee_id=user.employee_id,
        department=user.department,
        designation=user.designation,
        email_verified=user.email_verified,
        mfa_enabled=get_confirmed_authenticator(db, user.id) is not None,
    )

    if user.role in FIRST_LOGIN_PRIVILEGED_ROLES and user.must_change_password:
        confirmed_authenticator = get_confirmed_authenticator(db, user.id)
        if user.account_status == "pending_password_change" and confirmed_authenticator is not None:
            password_token = create_temporary_token(
                user.email,
                "privileged_password_setup",
                role=user.role,
                extra={"uid": user.id},
            )
            return LoginResponse(
                user=response_user,
                password_change_required=True,
                password_change_token=password_token,
            )

        _credential, uri, qr = create_or_replace_authenticator(db, user)
        user.account_status = "pending_mfa"
        user.is_active = False
        user.mfa_required = True
        record_audit(
            db,
            event_type="PRIVILEGED_TEMPORARY_PASSWORD_ACCEPTED",
            request=request,
            user=user,
            module="authentication",
            details={"role": user.role, "next_step": "authenticator_verification"},
        )
        db.commit()
        setup_token = create_temporary_token(user.email, "mfa_setup", role=user.role, extra={"uid": user.id})
        return LoginResponse(
            user=response_user,
            mfa_setup_required=True,
            mfa_setup_token=setup_token,
            otpauth_uri=uri,
            qr_code_data_uri=qr,
        )

    if user.email_verified and user.account_status == "pending_mfa":
        _credential, uri, qr = create_or_replace_authenticator(db, user)
        setup_token = create_temporary_token(user.email, "mfa_setup", role=user.role, extra={"uid": user.id})
        return LoginResponse(
            user=response_user,
            mfa_setup_required=True,
            mfa_setup_token=setup_token,
            otpauth_uri=uri,
            qr_code_data_uri=qr,
        )

    if not user.is_active or user.account_status not in {"active", ""}:
        record_audit(
            db,
            event_type="LOGIN_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
            details={"reason": "inactive_account", "status": user.account_status},
        )
        db.commit()
        raise HTTPException(status_code=403, detail="This account is not active")

    if user.mfa_required:
        user.mfa_required = False
        db.commit()

    token, _session = issue_access_for_user(db, user=user, request=request, access_role=effective_role)
    return LoginResponse(
        access_token=token,
        user=response_user,
        branch_selection_required=effective_role == "employee",
    )


def _user_response(auth: CurrentAuth, db: Session) -> UserResponse:
    branch_id = auth.claims.get("branch_id")
    branch = db.get(Branch, int(branch_id)) if branch_id is not None else None
    user = auth.user
    return UserResponse(
        id=user.id, email=user.email, full_name=user.full_name, role=auth.effective_role,
        branch=branch.name if branch else user.branch, employee_id=user.employee_id,
        department=user.department, designation=user.designation,
        phone_number=user.phone_number,
        joining_date=user.joining_date,
        date_of_birth=user.date_of_birth,
        created_at=user.created_at,
        selected_branch_id=branch.id if branch else None,
        selected_branch_name=branch.name if branch else None,
        email_verified=user.email_verified,
        mfa_enabled=get_confirmed_authenticator(db, user.id) is not None,
    )


@router.get("/auth/me", response_model=UserResponse)
def me(auth: CurrentAuth = Depends(get_current_auth), db: Session = Depends(get_db)) -> UserResponse:
    return _user_response(auth, db)


@router.get("/auth/profile", response_model=UserResponse)
def get_profile(auth: CurrentAuth = Depends(get_current_auth), db: Session = Depends(get_db)) -> UserResponse:
    return _user_response(auth, db)


@router.patch("/auth/profile", response_model=UserResponse)
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> UserResponse:
    user = auth.user
    changed: list[str] = []
    if payload.full_name is not None and payload.full_name.strip() != user.full_name:
        user.full_name = payload.full_name.strip()
        changed.append("full_name")
    if payload.phone_number is not None and (payload.phone_number.strip() or None) != user.phone_number:
        user.phone_number = payload.phone_number.strip() or None
        changed.append("phone_number")
    if payload.date_of_birth is not None and payload.date_of_birth != user.date_of_birth:
        user.date_of_birth = payload.date_of_birth
        changed.append("date_of_birth")
    if not changed:
        return _user_response(auth, db)
    db.add(user)
    record_audit(
        db,
        event_type="USER_PROFILE_UPDATED",
        request=request,
        user=user,
        module="authentication",
        target_type="user",
        target_id=str(user.id),
        details={"fields": changed},
    )
    db.commit()
    db.refresh(user)
    return _user_response(auth, db)


@router.post("/auth/change-password")
def change_own_password(
    payload: PasswordChangeRequest,
    request: Request,
    auth: CurrentAuth = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    user = auth.user
    if not verify_password(payload.current_password, user.password_hash):
        record_audit(
            db,
            event_type="USER_PASSWORD_CHANGE_FAILED",
            request=request,
            user=user,
            result="failed",
            module="authentication",
            details={"reason": "invalid_current_password"},
        )
        db.commit()
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.new_password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="New password and confirmation do not match")
    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="Use at least 8 characters for the new password")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must be different from the current password")
    user.password_hash = hash_password(payload.new_password)
    user.must_change_password = False
    user.token_version = int(user.token_version or 0) + 1
    record_audit(
        db,
        event_type="USER_PASSWORD_CHANGED",
        request=request,
        user=user,
        module="authentication",
        details={"sessions_revoked": True},
    )
    db.commit()
    return {"message": "Password changed successfully. Sign in again using the new password."}


@router.get("/dashboard/summary")
def dashboard_summary(db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "management", "it", "drone"))) -> dict:
    assets = list(db.scalars(select(Asset)).all())
    primary_assets = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    primary_summary = inventory_summary(primary_assets)
    drones = list(db.scalars(select(Drone)).all())
    pending_work = db.scalar(select(func.count(WorkRecord.id)).where(WorkRecord.status.in_(["open", "pending", "in_progress"]))) or 0
    return {
        "role": user.role,
        "assets_total": primary_summary["total"],
        "available_assets": primary_summary["available"],
        "repair_assets": primary_summary["repair"],
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
    start_local = datetime.combine(selected_start, datetime.min.time(), tzinfo=IST)
    end_local = datetime.combine(selected_end + timedelta(days=1), datetime.min.time(), tzinfo=IST)
    start_dt = start_local.astimezone(timezone.utc).replace(tzinfo=None)
    end_dt = end_local.astimezone(timezone.utc).replace(tzinfo=None)
    is_live = selected_start == month_start()
    selected_key = selected_start.strftime("%Y-%m")
    work_month_filter = or_(
        WorkRecord.reporting_month == selected_key,
        and_(WorkRecord.reporting_month.is_(None), WorkRecord.created_at >= start_dt, WorkRecord.created_at < end_dt),
    )
    replacement_month_filter = or_(
        ReplacementRecord.reporting_month == selected_key,
        and_(ReplacementRecord.reporting_month.is_(None), ReplacementRecord.created_at >= start_dt, ReplacementRecord.created_at < end_dt),
    )
    component_month_filter = or_(
        ComponentReplacement.reporting_month == selected_key,
        and_(ComponentReplacement.reporting_month.is_(None), ComponentReplacement.created_at >= start_dt, ComponentReplacement.created_at < end_dt),
    )
    history_month_filter = or_(
        AssetHistory.reporting_month == selected_key,
        and_(AssetHistory.reporting_month.is_(None), AssetHistory.created_at >= start_dt, AssetHistory.created_at < end_dt),
    )

    work_query = (
        select(WorkRecord)
        .where(
            WorkRecord.module == "it",
            work_month_filter,
        )
        .order_by(WorkRecord.created_at.desc())
        .limit(8)
    )
    replacement_query = (
        select(ReplacementRecord)
        .where(replacement_month_filter)
        .order_by(ReplacementRecord.created_at.desc())
        .limit(6)
    )
    work_records = list(db.scalars(work_query).all()) if source != "template" else []
    replacements = list(db.scalars(replacement_query).all()) if source != "template" else []

    # External HDDs remain a dedicated portable-storage register. Dashboard KPIs,
    # drill-downs and reports share one canonical classification layer so aliases and
    # legacy values cannot silently disappear or be counted twice.
    primary_assets = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    primary_summary = inventory_summary(primary_assets)
    all_summary = inventory_summary(assets)
    integrity = inventory_integrity(primary_assets, assets)

    department_counts = Counter(asset.department or "Unassigned" for asset in primary_assets)
    location_counts = Counter(asset.location or "Unknown" for asset in primary_assets)
    memory_counts = Counter(asset.memory_gb or "Not recorded" for asset in primary_assets)
    os_counts = Counter(asset.operating_system or "Not recorded" for asset in primary_assets)

    ip_counts = Counter(
        asset.ip_address
        for asset in primary_assets
        if asset.ip_address and asset.ip_address not in {"-", "Dynamic"}
    )
    duplicate_ips = sorted([ip for ip, count in ip_counts.items() if count > 1])
    pending_approvals = 0
    component_changes = 0
    complete_replacements = 0
    asset_edit_operations = 0
    assets_edited = 0
    new_assets = 0
    if source != "template":
        pending_approvals = db.scalar(
            select(func.count(WorkRecord.id)).where(
                WorkRecord.module == "it",
                WorkRecord.approval_status == "pending",
                work_month_filter,
            )
        ) or 0
        component_changes = db.scalar(
            select(func.count(ComponentReplacement.id)).where(component_month_filter)
        ) or 0
        asset_edit_operations = db.scalar(
            select(func.count(AssetHistory.id)).where(
                AssetHistory.change_type == "full_edit",
                history_month_filter,
            )
        ) or 0
        assets_edited = db.scalar(
            select(func.count(func.distinct(AssetHistory.asset_id))).where(
                AssetHistory.change_type == "full_edit",
                history_month_filter,
            )
        ) or 0
        complete_replacements = db.scalar(
            select(func.count(ReplacementRecord.id)).where(replacement_month_filter)
        ) or 0
        new_assets = db.scalar(
            select(func.count(func.distinct(AssetHistory.asset_id))).where(
                AssetHistory.change_type == "asset_created",
                history_month_filter,
            )
        ) or 0

    alerts = [
        {"severity": "high", "title": "Replacement pending", "count": primary_summary["replacement_pending"], "filter": "replacement_pending"},
        {"severity": "high", "title": "Assets under repair", "count": primary_summary["repair"], "filter": "repair"},
        {"severity": "medium", "title": "Missing employee assignment", "count": sum(not asset.used_by and is_primary_device_type(asset.device_type) for asset in assets), "filter": "unassigned"},
        {"severity": "medium", "title": "MAC address not recorded", "count": sum(not asset.mac_address and is_primary_device_type(asset.device_type) for asset in assets), "filter": "missing_mac"},
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
            "total": primary_summary["total"],
            "computers": primary_summary["computers"],
            "laptops": primary_summary["laptops"],
            "smartphones": primary_summary["smartphones"],
            "printers": primary_summary["printers"],
            "external_hdds": all_summary["external_hdds"],
            "assigned": primary_summary["assigned"],
            "available": primary_summary["available"],
            "repair": primary_summary["repair"],
            "replacement_pending": primary_summary["replacement_pending"],
            "wfh": primary_summary["wfh"],
            "field": primary_summary["field"],
            "returned": primary_summary["returned"],
            "damaged": primary_summary["damaged"],
            "servers": primary_summary["servers"],
            "network_devices": primary_summary["network_devices"],
            "other_primary": primary_summary["other"],
            "terminal": primary_summary["terminal"],
        },
        "monthly_activity": {
            "new_assets": new_assets,
            "work_records": len(work_records),
            "component_changes": component_changes,
            "complete_replacements": complete_replacements,
            "asset_edit_operations": asset_edit_operations,
            "assets_edited": assets_edited,
        },
        "device_distribution": canonical_device_distribution(primary_assets),
        "status_distribution": lifecycle_status_distribution(primary_assets),
        "inventory_integrity": integrity,
        "department_distribution": [{"name": key, "value": value} for key, value in department_counts.most_common(12)],
        "location_distribution": [{"name": key, "value": value} for key, value in location_counts.most_common(8)],
        "memory_distribution": [{"name": key, "value": value} for key, value in memory_counts.most_common(8)],
        "os_distribution": [{"name": key, "value": value} for key, value in os_counts.most_common(8)],
        "alerts": [alert for alert in alerts if alert["count"] > 0],
        "recent_work": [_work_response(work) for work in work_records],
        "recent_replacements": [_replacement_response(record) for record in replacements],
    }


@router.get("/dashboard/it/assets")
def it_dashboard_asset_drilldown(
    month: str = Query(..., description="Reporting month in YYYY-MM format"),
    scope: str = Query(default="all", description="all, primary, device, status or department"),
    scope_value: str | None = None,
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    location: str | None = None,
    work_mode: str | None = None,
    ownership: str | None = None,
    client_name: str | None = None,
    project_id: str | None = None,
    current_holder: str | None = None,
    brand: str | None = None,
    capacity: str | None = None,
    sort_by: str = "asset_code",
    sort_dir: str = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    try:
        result = query_asset_drilldown(
            db,
            month_key=month,
            scope=scope,
            scope_value=scope_value,
            search=search,
            department=department,
            device_type=device_type,
            status=status,
            location=location,
            work_mode=work_mode,
            ownership=ownership,
            client_name=client_name,
            project_id=project_id,
            current_holder=current_holder,
            brand=brand,
            capacity=capacity,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "No asset register" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    result["assets"] = [_asset_response(asset) for asset in result["assets"]]
    result.pop("all_filtered_assets", None)
    return result


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
                    Asset.system_name.ilike(pattern), Asset.brand.ilike(pattern), Asset.model.ilike(pattern),
                    Asset.serial_number.ilike(pattern), Asset.connection_type.ilike(pattern),
                    Asset.capacity.ilike(pattern), Asset.ownership.ilike(pattern),
                    Asset.client_name.ilike(pattern), Asset.project_id.ilike(pattern),
                    Asset.current_holder.ilike(pattern), Asset.ip_address.ilike(pattern),
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
        live_assets = list(db.scalars(query).all())
        asset_ids = [asset.id for asset in live_assets]
        latest_history: dict[int, AssetHistory] = {}
        if asset_ids:
            rows = db.scalars(
                select(AssetHistory)
                .where(AssetHistory.asset_id.in_(asset_ids), AssetHistory.change_type != "asset_created")
                .order_by(AssetHistory.created_at, AssetHistory.id)
            ).all()
            for row in rows:
                latest_history[row.asset_id] = row
        return [_attach_audit_summary(_asset_response(asset), latest_history.get(asset.id)) for asset in live_assets]

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
            asset.keyboard_asset_tag, asset.system_name, getattr(asset, "brand", None),
            getattr(asset, "model", None), getattr(asset, "serial_number", None),
            getattr(asset, "connection_type", None), getattr(asset, "capacity", None),
            getattr(asset, "ownership", None), getattr(asset, "client_name", None),
            getattr(asset, "project_id", None), getattr(asset, "current_holder", None),
            asset.ip_address, asset.mac_address,
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
        result.append(_attach_audit_summary(_asset_response(asset), None))
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
    latest_operational_history = next((item for item in history if item.change_type != "asset_created"), None)
    payload = _attach_audit_summary(_asset_response(asset), latest_operational_history)
    payload["history"] = [
        {
            "action": item.action,
            "change_type": item.change_type,
            "batch_code": item.batch_code,
            "old_value": item.old_value,
            "new_value": item.new_value,
            "remarks": item.remarks,
            "reason": item.reason,
            "changed_by": item.changed_by,
            "changed_by_name": item.changed_by_name,
            "changed_by_role": item.changed_by_role,
            "field_count": item.field_count,
            "reporting_month": item.reporting_month,
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
    reporting_month = normalize_reporting_month(values.pop("reporting_month", None))
    values["status"] = str(values.get("status") or "available").lower()
    values["work_mode"] = str(values.get("work_mode") or "office").lower()
    if is_supported_device_type(values.get("device_type")):
        values["device_type"] = canonical_device_type(values.get("device_type"))
    values["performed_by"] = user.full_name
    values["asset_date"] = values.get("asset_date") or date.today()
    _validate_asset_data(db, values)

    prefix = {
        "computer": "NT-PC", "laptop": "NT-LAP", "smartphone": "NT-MOB",
        "printer": "NT-PRN", "external hdd": "NT-HDD",
    }.get(
        values["device_type"].lower(), "NT-IT"
    )
    code = _next_code(db, Asset, Asset.asset_code, prefix)
    asset = Asset(asset_code=code, original_asset_date=values.get("asset_date"), **values)
    db.add(asset)
    db.flush()
    _record_history(
        db,
        asset,
        "Asset created",
        user,
        new_value=_serialise_changes({"asset_code": code, **values}),
        remarks="Manual asset registration",
        change_type="asset_created",
        reason="Manual asset registration",
        reporting_month=reporting_month,
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
    reporting_month = normalize_reporting_month(updates.pop("reporting_month", None))
    audit_reason = _normalised(updates.pop("audit_reason", None))
    audit_remarks = _normalised(updates.pop("audit_remarks", None))
    if not updates:
        return asset

    before = _asset_state(asset)
    merged = {**before, **updates}
    merged["status"] = str(merged.get("status") or "available").lower()
    merged["work_mode"] = str(merged.get("work_mode") or "office").lower()
    if "device_type" in updates and is_supported_device_type(updates.get("device_type")):
        updates["device_type"] = canonical_device_type(updates.get("device_type"))
        merged["device_type"] = updates["device_type"]
    _validate_asset_data(db, merged, exclude_asset_id=asset.id)

    changed: dict[str, dict] = {}
    for key, value in updates.items():
        old = getattr(asset, key)
        if old != value:
            changed[key] = {"from": old, "to": value}

    if not changed:
        return asset

    for key, values in changed.items():
        setattr(asset, key, values["to"])
    asset.performed_by = user.full_name
    asset.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    batch_code = _audit_batch_code("EDIT")
    _record_history(
        db,
        asset,
        "Asset details updated",
        user,
        old_value=_serialise_changes({key: value["from"] for key, value in changed.items()}),
        new_value=_serialise_changes({key: value["to"] for key, value in changed.items()}),
        remarks=audit_remarks or f"Updated fields: {', '.join(changed)}",
        change_type="full_edit",
        reason=audit_reason,
        batch_code=batch_code,
        field_count=len(changed),
        reporting_month=reporting_month,
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
    # Status remarks are activity-level audit notes. They must not be copied into
    # the permanent Asset Master Remarks field or carried into later months.
    _record_history(
        db,
        asset,
        "Status changed",
        user,
        old_value=old_status,
        new_value=next_status,
        remarks=payload.remarks,
        change_type="status_change",
        reason=payload.remarks or "Asset status updated",
        reporting_month=payload.reporting_month,
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
    asset = db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    work_mode = payload.work_mode.strip().lower()
    if work_mode not in WORK_MODES:
        raise HTTPException(status_code=400, detail="Work mode must be office, wfh or field")
    old_assignment = custody_state(asset)
    assignment_action = "transfer" if old_assignment.get("used_by") else "assign"
    try:
        apply_assignment_transition(
            asset,
            used_by=_normalised(payload.used_by),
            department=payload.department,
            workstation_no=_normalised(payload.workstation_no),
            location=_normalised(payload.location) or asset.location or "Head Office",
            work_mode=work_mode,
            transition_date=payload.assigned_date or asset.asset_date or date.today(),
            action=assignment_action,
        )
    except AssetLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _validate_asset_data(db, _asset_state(asset), exclude_asset_id=asset.id)
    _record_history(
        db,
        asset,
        "Asset assigned / transferred",
        user,
        old_value=_serialise_changes(old_assignment),
        new_value=_serialise_changes(custody_state(asset)),
        remarks=payload.remarks,
        change_type="assignment_transfer",
        reason=payload.remarks or ("Asset transferred to a new custodian" if assignment_action == "transfer" else "Asset assigned to a custodian"),
        reporting_month=payload.reporting_month,
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
    asset = db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    final_status = payload.final_status.strip().lower()
    if final_status not in {"available", "repair", "damaged", "returned"}:
        raise HTTPException(status_code=400, detail="Return status must be available, repair, damaged or returned")
    old_assignment = custody_state(asset)
    try:
        apply_return_transition(
            asset,
            final_status=final_status,
            transition_date=payload.return_date or date.today(),
        )
    except AssetLifecycleTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    note = f"Returned on {payload.return_date or date.today()}; condition: {payload.condition}; all components returned: {'Yes' if payload.all_components_returned else 'No'}"
    if payload.remarks:
        note = f"{note}; {payload.remarks}"
    # Return notes belong only to this return activity. Asset Master Remarks are
    # changed only through an explicit full asset edit.
    _record_history(
        db,
        asset,
        "Asset returned",
        user,
        old_value=_serialise_changes(old_assignment),
        new_value=_serialise_changes(custody_state(asset)),
        remarks=note,
        change_type="asset_returned",
        reason=payload.remarks or f"Asset returned in {payload.condition} condition",
        reporting_month=payload.reporting_month,
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.patch("/assets/{asset_id}/archive", response_model=AssetResponse)
def archive_asset(
    asset_id: int,
    reporting_month: str | None = Query(default=None),
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
    _record_history(
        db, asset, "Asset archived / retired", user,
        old_value=old_status, new_value="retired",
        change_type="asset_retired", reason="Asset retired from active inventory",
        reporting_month=reporting_month,
    )
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
    user: User = Depends(require_roles("admin", "management", "it", "drone")),
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
    user: User = Depends(require_roles("admin", "it", "drone")),
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
    values = payload.model_dump()
    values["reporting_month"] = normalize_reporting_month(values.get("reporting_month")) if module == "it" else None
    work = WorkRecord(
        work_code=_next_code(db, WorkRecord, WorkRecord.work_code, prefix),
        **values,
        status="open",
    )
    db.add(work)
    db.flush()
    if asset:
        _record_history(
            db,
            asset,
            "Work record created",
            user,
            new_value=work.work_code,
            remarks=f"{work.work_type}: {work.title}",
            change_type="work_record_created",
            reason=work.issue_description or work.title,
            reporting_month=work.reporting_month,
        )
    db.commit()
    db.refresh(work)
    return _work_response(work)


@router.patch("/work-records/{work_id}")
def update_work_record(
    work_id: int,
    payload: WorkRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it", "drone")),
) -> dict:
    work = db.scalar(
        select(WorkRecord)
        .where(WorkRecord.id == work_id)
        .with_for_update()
    )
    if not work:
        raise HTTPException(status_code=404, detail="Work record not found")
    if user.role in {"it", "drone"} and work.module != user.role:
        raise HTTPException(status_code=403, detail="You cannot update another department's work")
    if work.module == "it" and user.role == "management":
        raise HTTPException(status_code=403, detail="Management must use the approval decision endpoint for IT work")

    values = payload.model_dump(exclude_unset=True)
    if "approval_status" in values:
        raise HTTPException(
            status_code=400,
            detail="Approval decisions must use the Management approval endpoint",
        )
    if work.module == "it" and work.status in {"completed", "closed"} and values:
        raise HTTPException(
            status_code=409,
            detail="Completed IT work is locked. Management must return it to IT before further operational edits.",
        )

    if "reporting_month" in values and work.module == "it":
        values["reporting_month"] = normalize_reporting_month(values["reporting_month"])
    elif work.module != "it":
        values.pop("reporting_month", None)

    target_status = values.get("status")
    if target_status and target_status != work.status:
        if work.module == "it":
            if user.role not in {"it", "admin"}:
                raise HTTPException(status_code=403, detail="Only IT can perform operational IT work transitions")
            validate_it_work_operational_transition(work.status, target_status)
        elif work.module == "drone" and user.role == "management":
            raise HTTPException(status_code=403, detail="Management cannot perform Drone operational work transitions")

    old_status = work.status
    changed: dict[str, dict[str, object]] = {}
    for key, value in values.items():
        old = getattr(work, key)
        if old != value:
            changed[key] = {"from": old, "to": value}
            setattr(work, key, value)

    if work.module == "it" and target_status == "completed" and old_status != "completed":
        now = utc_now_naive()
        previous_approval_status = work.approval_status
        work.completed_at = now
        work.approval_status = "pending"
        work.submitted_by_user_id = user.id
        work.submitted_by_name = user.full_name
        work.submitted_by_email = user.email
        work.submitted_by_role = user.role
        work.submitted_at = now
        work.approved_by_user_id = None
        work.approved_by_name = None
        work.approved_by_email = None
        work.approved_by_role = None
        work.approved_at = None
        work.approval_comments = None
        record_approval_history(
            db,
            workflow_type=WORKFLOW_IT_WORK,
            record_id=work.id,
            record_code=work.work_code,
            action="resubmitted" if previous_approval_status == "returned" else "submitted",
            from_status=previous_approval_status,
            to_status="pending",
            user=user,
            remarks=work.resolution or work.issue_description or work.title,
        )
        notify_management_approval_required(
            db,
            workflow="it_work",
            record_id=work.id,
            record_code=work.work_code,
            reporting_month=work.reporting_month,
            submitted_by_name=user.full_name,
            event_token=work.submitted_at,
            resubmitted=previous_approval_status == "returned",
        )
    elif target_status == "completed":
        work.completed_at = work.completed_at or utc_now_naive()

    if work.asset and changed:
        _record_history(
            db,
            work.asset,
            "Work record updated",
            user,
            old_value=_serialise_changes({"work_code": work.work_code, "status": old_status}),
            new_value=_serialise_changes({"work_code": work.work_code, **{k: v["to"] for k, v in changed.items()}}),
            remarks=work.resolution or work.issue_description,
            change_type="work_record_updated",
            reason=work.resolution or work.issue_description or "Work record updated",
            reporting_month=work.reporting_month,
        )
    db.commit()
    db.refresh(work)
    return _work_response(work)


@router.post("/work-records/{work_id}/decision")
def decide_work_record(
    work_id: int,
    payload: WorkApprovalDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    work = db.scalar(
        select(WorkRecord)
        .where(WorkRecord.id == work_id)
        .with_for_update()
    )
    if work is None:
        raise HTTPException(status_code=404, detail="Work record not found")
    if work.module != "it":
        raise HTTPException(status_code=400, detail="This Management approval workflow is only for IT work records")
    if work.status != "completed" or work.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only completed IT work pending Management approval can be decided")
    if work.submitted_by_user_id is not None and work.submitted_by_user_id == user.id:
        raise HTTPException(status_code=409, detail="A user cannot approve or return their own submitted IT work")

    comments = (payload.comments or "").strip() or None
    if payload.action == "return" and not comments:
        raise HTTPException(status_code=400, detail="Management comments are required when returning work to IT")

    now = utc_now_naive()
    from_status = work.approval_status
    if payload.action == "approve":
        work.status = "closed"
        work.approval_status = "approved"
        history_action = "approved"
        history_to_status = "approved"
    else:
        work.status = "in_progress"
        work.approval_status = "returned"
        history_action = "returned"
        history_to_status = "returned"

    work.approved_by_user_id = user.id
    work.approved_by_name = user.full_name
    work.approved_by_email = user.email
    work.approved_by_role = user.role
    work.approved_at = now
    work.approval_comments = comments

    record_approval_history(
        db,
        workflow_type=WORKFLOW_IT_WORK,
        record_id=work.id,
        record_code=work.work_code,
        action=history_action,
        from_status=from_status,
        to_status=history_to_status,
        user=user,
        remarks=comments,
    )
    notify_approval_decision(
        db,
        workflow="it_work",
        record_id=work.id,
        record_code=work.work_code,
        reporting_month=work.reporting_month,
        outcome=history_to_status,
        decided_by_name=user.full_name,
        remarks=comments,
        event_token=work.approved_at,
        recipient_user_id=work.submitted_by_user_id,
    )
    if work.asset:
        _record_history(
            db,
            work.asset,
            "IT work approved and closed" if payload.action == "approve" else "IT work returned by Management",
            user,
            old_value="completed / pending approval",
            new_value=f"{work.status} / {work.approval_status}",
            remarks=comments,
            change_type="work_approval_decision",
            reason=comments or work.resolution or work.issue_description or work.title,
            reporting_month=work.reporting_month,
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
    reporting_month = normalize_reporting_month(payload.reporting_month)

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
        if row_change_type not in {"upgrade", "replacement", "downgrade", "upgrade_replacement"}:
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
        "downgrade": "Multi-component Downgrade",
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
        reporting_month=reporting_month,
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
            performed_by_email=user.email,
            performed_by_role=user.role,
            approved_by=payload.approved_by,
            remarks=payload.remarks,
            reporting_month=reporting_month,
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
    asset.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _record_history(
        db,
        asset,
        work_type_label,
        user,
        old_value=_serialise_changes({key: value["from"] for key, value in changed_fields.items()}),
        new_value=_serialise_changes({key: value["to"] for key, value in changed_fields.items()}),
        remarks=f"Batch {batch_code}; Work record {work.work_code}; {payload.remarks or work_type_label}",
        change_type=f"component_{payload.change_type}",
        reason="; ".join(f"{row['component_type']}: {row['reason']}" for row in prepared),
        batch_code=batch_code,
        field_count=len(prepared),
        reporting_month=reporting_month,
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
    reporting_month = normalize_reporting_month(payload.reporting_month)

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
        reporting_month=reporting_month,
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
        performed_by_email=user.email,
        performed_by_role=user.role,
        approved_by=payload.approved_by,
        remarks=payload.remarks,
        reporting_month=reporting_month,
    )
    db.add(record)
    setattr(asset, field_name, updated_value)
    asset.performed_by = user.full_name
    asset.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _record_history(
        db,
        asset,
        "Component / configuration changed",
        user,
        old_value=_serialise_changes({field_name: old_value_for_history}),
        new_value=_serialise_changes({field_name: new_value_text}),
        remarks=f"{payload.component_type}: {payload.reason}; Work record {work.work_code}",
        change_type=f"component_{payload.change_type}",
        reason=payload.reason,
        batch_code=record.batch_code or record.replacement_code,
        field_count=1,
        reporting_month=reporting_month,
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
    old_asset = db.scalar(
        select(Asset).where(Asset.id == payload.old_asset_id).with_for_update()
    )
    if not old_asset:
        raise HTTPException(status_code=404, detail="Old asset not found")
    existing_open_request = db.scalar(
        select(ReplacementRecord.id)
        .where(
            ReplacementRecord.old_asset_id == old_asset.id,
            ReplacementRecord.approval_status.in_(["pending", "returned"]),
        )
        .limit(1)
    )
    if existing_open_request is not None:
        raise HTTPException(status_code=409, detail="This asset already has an active replacement request")

    new_asset = None
    if payload.new_asset_id:
        new_asset = db.scalar(select(Asset).where(Asset.id == payload.new_asset_id).with_for_update())
    if new_asset and new_asset.id == old_asset.id:
        raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
    if new_asset and new_asset.status != "available":
        raise HTTPException(status_code=400, detail="Selected replacement asset is not available")
    if new_asset and new_asset.device_type != old_asset.device_type:
        raise HTTPException(status_code=400, detail="Replacement asset must use the same device type as the old asset")
    replacement_values = payload.model_dump()
    replacement_values["reporting_month"] = normalize_reporting_month(replacement_values.get("reporting_month"))
    record = ReplacementRecord(
        replacement_code=_next_code(db, ReplacementRecord, ReplacementRecord.replacement_code, "RPL"),
        **replacement_values,
        requested_by_user_id=user.id,
        requested_by=user.full_name,
        requested_by_email=user.email,
        requested_by_role=user.role,
        approval_status="pending",
    )
    old_status = old_asset.status
    old_asset.status = "replacement_pending"
    db.add(record)
    db.flush()
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
        old_value=old_status,
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
def approve_replacement(
    replacement_id: int,
    payload: ReplacementApproval,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    record = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == replacement_id)
        .with_for_update()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    if record.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending replacement requests can receive a Management decision")
    if record.requested_by_user_id is not None and record.requested_by_user_id == user.id:
        raise HTTPException(status_code=409, detail="A user cannot decide their own replacement request")

    remarks = (payload.remarks or "").strip() or None
    if payload.approval_status in {"rejected", "returned"} and not remarks:
        raise HTTPException(status_code=400, detail="Management remarks are required for rejection or return")

    old_asset = db.scalar(select(Asset).where(Asset.id == record.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Replacement request references a missing old asset")

    effective_new_asset_id = payload.new_asset_id if payload.new_asset_id is not None else record.new_asset_id
    new_asset: Asset | None = None
    if effective_new_asset_id is not None:
        new_asset = db.scalar(select(Asset).where(Asset.id == effective_new_asset_id).with_for_update())
        if not new_asset:
            raise HTTPException(status_code=404, detail="Replacement asset not found")
        if new_asset.id == old_asset.id:
            raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
        if new_asset.device_type != old_asset.device_type:
            raise HTTPException(status_code=400, detail="Replacement asset must use the same device type as the old asset")
        if payload.approval_status == "approved" and new_asset.status != "available":
            raise HTTPException(status_code=409, detail="Replacement asset is no longer available")

    if payload.final_action:
        record.final_action = payload.final_action
    if payload.approval_status == "approved" and record.final_action == "replace_and_retire" and new_asset is None:
        raise HTTPException(status_code=400, detail="Select an available replacement asset before approval")

    now = utc_now_naive()
    record.approval_status = payload.approval_status
    record.approved_by_user_id = user.id
    record.approved_by = user.full_name
    record.approved_by_email = user.email
    record.approved_by_role = user.role
    record.approved_at = now
    record.decision_remarks = remarks
    record.updated_at = now
    if new_asset is not None:
        record.new_asset_id = new_asset.id

    if payload.approval_status == "approved":
        old_asset.status = "replaced"
        effective_new_asset = new_asset
        if effective_new_asset:
            effective_new_asset.status = "assigned"
            effective_new_asset.used_by = old_asset.used_by
            effective_new_asset.department = old_asset.department
            effective_new_asset.location = old_asset.location
            effective_new_asset.workstation_no = old_asset.workstation_no
            effective_new_asset.work_mode = old_asset.work_mode
            _record_history(
                db,
                effective_new_asset,
                "Assigned as replacement asset",
                user,
                old_value="available",
                new_value="assigned",
                remarks=f"Replaces {old_asset.asset_code}",
                change_type="complete_asset_replacement",
                reason=record.reason,
                reporting_month=record.reporting_month,
            )
        _record_history(
            db,
            old_asset,
            "Replacement approved",
            user,
            old_value="replacement_pending",
            new_value="replaced",
            remarks=remarks,
            change_type="replacement_approved",
            reason=remarks or record.reason,
            batch_code=record.replacement_code,
            field_count=1,
            reporting_month=record.reporting_month,
        )
        history_action = "approved"
    elif payload.approval_status == "rejected":
        previous_status = "assigned" if old_asset.used_by else "available"
        old_asset.status = previous_status
        _record_history(
            db,
            old_asset,
            "Replacement rejected",
            user,
            old_value="replacement_pending",
            new_value=previous_status,
            remarks=remarks,
            change_type="replacement_rejected",
            reason=remarks or record.reason,
            batch_code=record.replacement_code,
            field_count=1,
            reporting_month=record.reporting_month,
        )
        history_action = "rejected"
    else:
        # Returned requests stay in replacement_pending so the failed asset is not
        # accidentally placed back into normal service while IT corrects the request.
        old_asset.status = "replacement_pending"
        _record_history(
            db,
            old_asset,
            "Replacement returned to IT",
            user,
            old_value="replacement_pending",
            new_value="replacement_pending",
            remarks=remarks,
            change_type="replacement_returned",
            reason=remarks or record.reason,
            batch_code=record.replacement_code,
            field_count=0,
            reporting_month=record.reporting_month,
        )
        history_action = "returned"

    record_approval_history(
        db,
        workflow_type=WORKFLOW_REPLACEMENT,
        record_id=record.id,
        record_code=record.replacement_code,
        action=history_action,
        from_status="pending",
        to_status=payload.approval_status,
        user=user,
        remarks=remarks,
    )
    notify_approval_decision(
        db,
        workflow="replacement",
        record_id=record.id,
        record_code=record.replacement_code,
        reporting_month=record.reporting_month,
        outcome=payload.approval_status,
        decided_by_name=user.full_name,
        remarks=remarks,
        event_token=record.approved_at,
        recipient_user_id=record.requested_by_user_id,
    )
    db.commit()
    db.refresh(record)
    return _replacement_response(record)


@router.put("/replacements/{replacement_id}/resubmit")
def resubmit_replacement(
    replacement_id: int,
    payload: ReplacementResubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    record = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == replacement_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    if record.approval_status != "returned":
        raise HTTPException(status_code=409, detail="Only replacement requests returned by Management can be resubmitted")

    old_asset = db.scalar(select(Asset).where(Asset.id == record.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Replacement request references a missing old asset")
    new_asset = None
    if payload.new_asset_id:
        new_asset = db.scalar(select(Asset).where(Asset.id == payload.new_asset_id).with_for_update())
        if new_asset is None:
            raise HTTPException(status_code=404, detail="Selected replacement asset was not found")
    if new_asset and new_asset.id == old_asset.id:
        raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
    if new_asset and new_asset.status != "available":
        raise HTTPException(status_code=400, detail="Selected replacement asset is not available")
    if new_asset and new_asset.device_type != old_asset.device_type:
        raise HTTPException(status_code=400, detail="Replacement asset must use the same device type as the old asset")

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Replacement reason is required")

    record.reporting_month = normalize_reporting_month(payload.reporting_month)
    record.new_asset_id = new_asset.id if new_asset else None
    record.reason = reason
    record.damage_category = payload.damage_category
    record.inspection_finding = (payload.inspection_finding or "").strip() or None
    record.final_action = payload.final_action
    record.approval_status = "pending"
    record.approved_by_user_id = None
    record.approved_by = None
    record.approved_by_email = None
    record.approved_by_role = None
    record.approved_at = None
    record.decision_remarks = None
    record.updated_at = utc_now_naive()
    old_asset.status = "replacement_pending"

    record_approval_history(
        db,
        workflow_type=WORKFLOW_REPLACEMENT,
        record_id=record.id,
        record_code=record.replacement_code,
        action="resubmitted",
        from_status="returned",
        to_status="pending",
        user=user,
        remarks=record.reason,
    )
    notify_management_approval_required(
        db,
        workflow="replacement",
        record_id=record.id,
        record_code=record.replacement_code,
        reporting_month=record.reporting_month,
        submitted_by_name=user.full_name,
        event_token=record.updated_at,
        resubmitted=True,
    )
    _record_history(
        db,
        old_asset,
        "Replacement request resubmitted",
        user,
        old_value="returned for correction",
        new_value="pending management approval",
        remarks=record.reason,
        change_type="replacement_resubmitted",
        reason=record.reason,
        batch_code=record.replacement_code,
        field_count=1,
        reporting_month=record.reporting_month,
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


@router.post("/imports/printers.xlsx")
async def import_printers_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx printer register")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Printer Excel file is larger than 10 MB")
    try:
        return import_printer_assets_workbook(db, content, performed_by=user.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/external-hdds.xlsx")
async def import_external_hdds_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx External HDD register")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="External HDD Excel file is larger than 10 MB")
    try:
        return import_external_hdd_assets_workbook(db, content, performed_by=user.full_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.get("/reports/it-dashboard-assets.xlsx")
def it_dashboard_asset_drilldown_excel(
    month: str = Query(..., description="Reporting month in YYYY-MM format"),
    scope: str = Query(default="all", description="all, primary, device, status or department"),
    scope_value: str | None = None,
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    location: str | None = None,
    work_mode: str | None = None,
    ownership: str | None = None,
    client_name: str | None = None,
    project_id: str | None = None,
    current_holder: str | None = None,
    brand: str | None = None,
    capacity: str | None = None,
    sort_by: str = "asset_code",
    sort_dir: str = "asc",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        result = query_asset_drilldown(
            db,
            month_key=month,
            scope=scope,
            scope_value=scope_value,
            search=search,
            department=department,
            device_type=device_type,
            status=status,
            location=location,
            work_mode=work_mode,
            ownership=ownership,
            client_name=client_name,
            project_id=project_id,
            current_holder=current_holder,
            brand=brand,
            capacity=capacity,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=1,
            page_size=100,
        )
        stream = build_asset_drilldown_workbook(result)
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "No asset register" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc

    safe_scope = re.sub(r"[^A-Za-z0-9_-]+", "-", result["scope"]["label"]).strip("-") or "Assets"
    filename = f"NakshaTech {safe_scope} - {result['month']['label']}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/complete-monthly.xlsx")
def complete_monthly_excel_report(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    ensure_previous_month_snapshot(db)
    try:
        period = monthly_period(month)
        stream = build_complete_period_report(db, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"NakshaTech Complete IT Report - {period.label}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/complete-yearly.xlsx")
def complete_yearly_excel_report(
    year: int = Query(..., ge=2000, le=2100),
    period_type: str = Query(default="calendar", alias="period", description="calendar or financial"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    ensure_previous_month_snapshot(db)
    try:
        period = yearly_period(year, period_type)
        stream = build_complete_period_report(db, period)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"NakshaTech Complete IT Report - {period.label}.xlsx"
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    filename = f"NakshaTech IT Asset Changes - {start.strftime('%B %Y')}.xlsx"
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


@router.get("/reports/printers.xlsx")
def printer_asset_excel_report(
    month: str | None = Query(default=None, description="Reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        stream = build_printer_asset_report(db, month)
        label = parse_month_key(month).strftime("%B %Y") if month else month_start().strftime("%B %Y")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="NakshaTech Printer Asset Register - {label}.xlsx"'},
    )


@router.get("/reports/external-hdds.xlsx")
def external_hdd_asset_excel_report(
    month: str | None = Query(default=None, description="Reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        stream = build_external_hdd_asset_report(db, month)
        label = parse_month_key(month).strftime("%B %Y") if month else month_start().strftime("%B %Y")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="NakshaTech External HDD Asset Register - {label}.xlsx"'},
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
