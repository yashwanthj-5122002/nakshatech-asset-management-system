from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.operations.handover_service import DEMO_DEPARTMENT_EMAILS, DEMO_EMPLOYEE_IDS
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_DEPARTMENT_ROLE_MAP,
    TECHNICAL_ROLE_DEPARTMENT_MAP,
    normalize_role,
)
from app.modules.operations.technical_directory_models import TechnicalDepartmentMember
from app.modules.operations.technical_directory_schemas import (
    TechnicalDirectoryMemberCreate,
    TechnicalDirectoryMemberUpdate,
)
from app.modules.operations.technical_routing_service import (
    assert_department_live_integrity,
    current_routing_mode,
    live_routing_enabled,
    routing_status_payload,
)

# Phase 6 is intentionally a production-readiness phase, not the cutover itself.
# A later explicit go-live phase will consume this directory and enable real-team
# notification delivery only after the user approves the final real accounts.
LIVE_TECHNICAL_ROUTING_ENABLED = False
TECHNICAL_ROUTING_MODE = "uat_demo_locked"

TECHNICAL_ROLES = set(TECHNICAL_ROLE_DEPARTMENT_MAP)
GLOBAL_DIRECTORY_READ_ROLES = {"admin", "management", "bd"}


def _validate_department_code(department_code: str) -> str:
    code = str(department_code or "").strip().lower()
    if code not in TECHNICAL_DEPARTMENT_ROLE_MAP:
        raise ValueError("Unsupported technical department")
    return code


def _is_demo_user(user: User, department_code: str) -> bool:
    return bool(
        (user.email or "").strip().lower() == DEMO_DEPARTMENT_EMAILS.get(department_code, "").lower()
        or (user.employee_id or "") == DEMO_EMPLOYEE_IDS.get(department_code)
        or (user.employee_id or "").startswith("DEMO-V715-")
    )


def _validate_real_department_user(db: Session, *, department_code: str, user_id: int) -> User:
    code = _validate_department_code(department_code)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP[code]
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("Selected ERP user was not found")
    if not user.is_active or user.account_status != "active":
        raise ValueError("Select an active ERP technical user")
    if normalize_role(user.role) != expected_role:
        raise ValueError(
            f"Selected user must have the exact {TECHNICAL_DEPARTMENT_LABELS[code]} role ({expected_role})"
        )
    if _is_demo_user(user, code):
        raise ValueError("Reserved UAT demo accounts cannot be added to the production technical-team directory")
    return user


def _member_payload(db: Session, row: TechnicalDepartmentMember) -> dict:
    user = db.get(User, row.user_id)
    active_user = bool(user and user.is_active and user.account_status == "active")
    role_match = bool(
        user
        and normalize_role(user.role) == TECHNICAL_DEPARTMENT_ROLE_MAP.get(row.department_code)
    )
    return {
        "id": row.id,
        "department_code": row.department_code,
        "user_id": row.user_id,
        "full_name": user.full_name if user else None,
        "email": user.email if user else None,
        "employee_id": user.employee_id if user else None,
        "designation": user.designation if user else None,
        "stored_role": normalize_role(user.role) if user else None,
        "user_active": active_user,
        "role_match": role_match,
        "pm_eligible": bool(row.pm_eligible),
        "receive_sample_notifications": bool(row.receive_sample_notifications),
        "receive_handover_notifications": bool(row.receive_handover_notifications),
        "receive_completion_notifications": bool(row.receive_completion_notifications),
        "is_active": bool(row.is_active),
        "notes": row.notes,
        "ready_for_live_use": bool(row.is_active and active_user and role_match),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _eligible_users(db: Session, department_code: str) -> list[dict]:
    code = _validate_department_code(department_code)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP[code]
    users = list(db.scalars(select(User).where(
        User.role == expected_role,
        User.is_active.is_(True),
        User.account_status == "active",
    ).order_by(User.full_name.asc(), User.email.asc())).all())
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "employee_id": user.employee_id,
            "designation": user.designation,
            "role": normalize_role(user.role),
        }
        for user in users
        if not _is_demo_user(user, code)
    ]


def add_directory_member(
    db: Session,
    *,
    department_code: str,
    actor: User,
    payload: TechnicalDirectoryMemberCreate,
) -> TechnicalDepartmentMember:
    code = _validate_department_code(department_code)
    _validate_real_department_user(db, department_code=code, user_id=payload.user_id)
    row = db.scalar(select(TechnicalDepartmentMember).where(
        TechnicalDepartmentMember.department_code == code,
        TechnicalDepartmentMember.user_id == payload.user_id,
    ))
    if row is None:
        row = TechnicalDepartmentMember(
            department_code=code,
            user_id=payload.user_id,
            pm_eligible=payload.pm_eligible,
            receive_sample_notifications=payload.receive_sample_notifications,
            receive_handover_notifications=payload.receive_handover_notifications,
            receive_completion_notifications=payload.receive_completion_notifications,
            is_active=True,
            notes=(payload.notes or "").strip() or None,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        db.add(row)
    else:
        row.pm_eligible = payload.pm_eligible
        row.receive_sample_notifications = payload.receive_sample_notifications
        row.receive_handover_notifications = payload.receive_handover_notifications
        row.receive_completion_notifications = payload.receive_completion_notifications
        row.is_active = True
        row.notes = (payload.notes or "").strip() or None
        row.updated_by_id = actor.id
        row.updated_at = utc_now()
    db.flush()
    return row


def update_directory_member(
    db: Session,
    *,
    row: TechnicalDepartmentMember,
    actor: User,
    payload: TechnicalDirectoryMemberUpdate,
) -> TechnicalDepartmentMember:
    _validate_real_department_user(db, department_code=row.department_code, user_id=row.user_id)
    for field in (
        "pm_eligible",
        "receive_sample_notifications",
        "receive_handover_notifications",
        "receive_completion_notifications",
        "is_active",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    if payload.notes is not None:
        row.notes = payload.notes.strip() or None
    row.updated_by_id = actor.id
    row.updated_at = utc_now()
    db.flush()
    assert_department_live_integrity(db, department_code=row.department_code)
    return row


def deactivate_directory_member(
    db: Session,
    *,
    row: TechnicalDepartmentMember,
    actor: User,
) -> TechnicalDepartmentMember:
    row.is_active = False
    row.updated_by_id = actor.id
    row.updated_at = utc_now()
    db.flush()
    assert_department_live_integrity(db, department_code=row.department_code)
    return row


def _visible_department_codes(effective_role: str) -> tuple[str, list[str]]:
    role = normalize_role(effective_role)
    if role == "admin":
        return "admin_editor", list(TECHNICAL_DEPARTMENT_ROLE_MAP)
    if role in {"management", "bd"}:
        return "read_only", list(TECHNICAL_DEPARTMENT_ROLE_MAP)
    if role in TECHNICAL_ROLES:
        return "department_read_only", [TECHNICAL_ROLE_DEPARTMENT_MAP[role]]
    raise PermissionError("Technical Team Directory is not available for this role")


def directory_dashboard_payload(db: Session, *, effective_role: str) -> dict:
    viewer_mode, department_codes = _visible_department_codes(effective_role)
    routing_state = routing_status_payload(db)
    all_active_rows = list(db.scalars(select(TechnicalDepartmentMember).where(
        TechnicalDepartmentMember.is_active.is_(True)
    ).order_by(TechnicalDepartmentMember.department_code.asc(), TechnicalDepartmentMember.id.asc())).all())
    rows_by_department: dict[str, list[TechnicalDepartmentMember]] = {
        code: [] for code in TECHNICAL_DEPARTMENT_ROLE_MAP
    }
    for row in all_active_rows:
        if row.department_code in rows_by_department:
            rows_by_department[row.department_code].append(row)

    departments: list[dict] = []
    for code in department_codes:
        members = [_member_payload(db, row) for row in rows_by_department.get(code, [])]
        ready_members = [row for row in members if row["ready_for_live_use"]]
        sample_count = sum(1 for row in ready_members if row["receive_sample_notifications"])
        handover_count = sum(1 for row in ready_members if row["receive_handover_notifications"])
        completion_count = sum(1 for row in ready_members if row["receive_completion_notifications"])
        pm_count = sum(1 for row in ready_members if row["pm_eligible"])
        live_ready = bool(ready_members and sample_count and handover_count and completion_count and pm_count)
        demo_email = DEMO_DEPARTMENT_EMAILS.get(code)
        demo_user = db.scalar(select(User).where(func.lower(User.email) == str(demo_email or "").lower())) if demo_email else None
        departments.append({
            "department_code": code,
            "department_label": TECHNICAL_DEPARTMENT_LABELS[code],
            "role": TECHNICAL_DEPARTMENT_ROLE_MAP[code],
            "routing_mode": routing_state["routing_mode"],
            "demo_account": {
                "email": demo_email,
                "present": bool(demo_user),
                "active": bool(demo_user and demo_user.is_active and demo_user.account_status == "active"),
            },
            "configured_members": members,
            "eligible_users": _eligible_users(db, code) if viewer_mode == "admin_editor" else [],
            "readiness": {
                "configured_real_members": len(ready_members),
                "pm_candidates": pm_count,
                "sample_recipients": sample_count,
                "handover_recipients": handover_count,
                "completion_recipients": completion_count,
                "live_ready": live_ready,
            },
        })

    ready_departments = sum(1 for item in departments if item["readiness"]["live_ready"])
    return {
        "viewer_mode": viewer_mode,
        "routing_mode": routing_state["routing_mode"],
        "live_technical_routing_enabled": routing_state["live_technical_routing_enabled"],
        "go_live_activation_available": routing_state["can_activate"],
        "go_live_message": routing_state["message"],
        "cutover": routing_state,
        "summary": {
            "visible_departments": len(departments),
            "configured_real_members": sum(item["readiness"]["configured_real_members"] for item in departments),
            "live_ready_departments": ready_departments,
            "not_ready_departments": len(departments) - ready_departments,
        },
        "departments": departments,
    }
