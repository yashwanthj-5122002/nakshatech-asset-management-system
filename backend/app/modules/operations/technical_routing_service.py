from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.models import ProjectWorkstream
from app.modules.operations.sample_models import TechnicalSampleRequest
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_DEPARTMENT_ROLE_MAP,
    normalize_role,
)
from app.modules.operations.technical_directory_models import TechnicalDepartmentMember
from app.modules.operations.technical_routing_models import TechnicalRoutingControl

ROUTING_MODE_DEMO = "uat_demo_locked"
ROUTING_MODE_LIVE = "production_live"
ACTIVATION_CONFIRMATION = "ACTIVATE REAL TECHNICAL ROUTING"

_PURPOSE_COLUMNS = {
    "pm": TechnicalDepartmentMember.pm_eligible,
    "sample": TechnicalDepartmentMember.receive_sample_notifications,
    "handover": TechnicalDepartmentMember.receive_handover_notifications,
    "completion": TechnicalDepartmentMember.receive_completion_notifications,
}


def _control(db: Session) -> TechnicalRoutingControl | None:
    return db.get(TechnicalRoutingControl, 1)


def live_routing_enabled(db: Session) -> bool:
    row = _control(db)
    return bool(row and row.live_enabled and row.routing_mode == ROUTING_MODE_LIVE)


def current_routing_mode(db: Session) -> str:
    return ROUTING_MODE_LIVE if live_routing_enabled(db) else ROUTING_MODE_DEMO


def _valid_member_rows(db: Session, department_code: str) -> list[tuple[TechnicalDepartmentMember, User]]:
    code = str(department_code or "").strip().lower()
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(code)
    if expected_role is None:
        raise ValueError("Unsupported technical department")
    pairs = list(db.execute(
        select(TechnicalDepartmentMember, User)
        .join(User, User.id == TechnicalDepartmentMember.user_id)
        .where(
            TechnicalDepartmentMember.department_code == code,
            TechnicalDepartmentMember.is_active.is_(True),
            User.is_active.is_(True),
            User.account_status == "active",
            User.role == expected_role,
        )
        .order_by(User.full_name.asc(), User.email.asc(), User.id.asc())
    ).all())
    return [
        (member, user)
        for member, user in pairs
        if normalize_role(user.role) == expected_role
        and not (user.employee_id or "").startswith("DEMO-V715-")
    ]


def real_department_users(db: Session, *, department_code: str, purpose: str) -> list[User]:
    if purpose not in _PURPOSE_COLUMNS:
        raise ValueError("Unsupported technical routing purpose")
    attr = _PURPOSE_COLUMNS[purpose]
    return [user for member, user in _valid_member_rows(db, department_code) if bool(getattr(member, attr.key))]


def real_department_user_ids(db: Session, *, department_code: str, purpose: str) -> list[int]:
    return [user.id for user in real_department_users(db, department_code=department_code, purpose=purpose)]


def is_real_department_member(
    db: Session,
    *,
    department_code: str,
    user_id: int,
    purpose: str | None = None,
) -> bool:
    pairs = _valid_member_rows(db, department_code)
    for member, user in pairs:
        if user.id != user_id:
            continue
        if purpose is None:
            return True
        if purpose not in _PURPOSE_COLUMNS:
            return False
        return bool(getattr(member, _PURPOSE_COLUMNS[purpose].key))
    return False


def validate_live_project_manager(db: Session, *, department_code: str, user_id: int) -> User:
    if not is_real_department_member(db, department_code=department_code, user_id=user_id, purpose="pm"):
        label = TECHNICAL_DEPARTMENT_LABELS.get(department_code, department_code)
        raise ValueError(f"Select a Phase 7 live-ready {label} Project Manager from Technical Team Directory")
    user = db.get(User, user_id)
    if user is None:
        raise ValueError("Selected Project Manager was not found")
    return user


def department_readiness(db: Session, *, department_code: str) -> dict:
    pairs = _valid_member_rows(db, department_code)
    pm = sum(1 for member, _ in pairs if member.pm_eligible)
    sample = sum(1 for member, _ in pairs if member.receive_sample_notifications)
    handover = sum(1 for member, _ in pairs if member.receive_handover_notifications)
    completion = sum(1 for member, _ in pairs if member.receive_completion_notifications)
    return {
        "department_code": department_code,
        "department_label": TECHNICAL_DEPARTMENT_LABELS.get(department_code, department_code),
        "configured_real_members": len(pairs),
        "pm_candidates": pm,
        "sample_recipients": sample,
        "handover_recipients": handover,
        "completion_recipients": completion,
        "live_ready": bool(pairs and pm and sample and handover and completion),
    }


def all_departments_readiness(db: Session) -> list[dict]:
    return [department_readiness(db, department_code=code) for code in TECHNICAL_DEPARTMENT_ROLE_MAP]


def assert_department_live_integrity(db: Session, *, department_code: str) -> None:
    if not live_routing_enabled(db):
        return
    readiness = department_readiness(db, department_code=department_code)
    if not readiness["live_ready"]:
        raise ValueError(
            f"{readiness['department_label']} cannot lose PM/Sample/Handover/Completion coverage while Phase 7 production routing is active"
        )

    # Do not allow Admin to remove PM eligibility from a person who still owns
    # an unfinished production workstream merely because another PM exists in
    # the same department. Existing production ownership must remain executable.
    active_rows = list(db.scalars(select(ProjectWorkstream).where(
        ProjectWorkstream.department_code == department_code,
        ProjectWorkstream.is_active.is_(True),
        ProjectWorkstream.status != "completed",
    )).all())
    for workstream in active_rows:
        if not is_real_department_member(
            db, department_code=department_code, user_id=workstream.project_manager_user_id, purpose="pm"
        ):
            raise ValueError(
                f"{readiness['department_label']} member cannot be removed from PM eligibility while assigned to active Project Workstream #{workstream.id}"
            )


def _open_cutover_blockers(db: Session) -> dict:
    open_samples = int(db.scalar(select(func.count(TechnicalSampleRequest.id)).where(
        TechnicalSampleRequest.status != "client_approved"
    )) or 0)
    open_workstreams = int(db.scalar(select(func.count(ProjectWorkstream.id)).where(
        ProjectWorkstream.is_active.is_(True),
        ProjectWorkstream.status != "completed",
    )) or 0)
    unresolved_handovers = int(db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.is_active.is_(True),
        ProjectDataHandover.status != "accepted",
    )) or 0)
    return {
        "open_sample_requests": open_samples,
        "open_technical_workstreams": open_workstreams,
        "unresolved_handovers": unresolved_handovers,
    }


def routing_status_payload(db: Session) -> dict:
    row = _control(db)
    live = live_routing_enabled(db)
    readiness = all_departments_readiness(db)
    blockers = _open_cutover_blockers(db)
    all_ready = all(item["live_ready"] for item in readiness)
    blocker_total = sum(blockers.values())
    activated_by = db.get(User, row.activated_by_id) if row and row.activated_by_id else None
    if live:
        message = "Phase 7 production routing is ACTIVE. Real Technical Team Directory users now own technical PM, sample, handover, progress and completion workflows."
    elif not all_ready:
        message = "Prepare all six technical departments with PM, Sample, Handover and Completion coverage before production activation."
    elif blocker_total:
        message = "Finish the listed UAT/demo technical work before cutover. Phase 7 uses a clean-boundary activation and will not mix active demo and live workflows."
    else:
        message = f"All production prerequisites are satisfied. Admin may activate real technical routing by entering: {ACTIVATION_CONFIRMATION}"
    return {
        "routing_mode": ROUTING_MODE_LIVE if live else ROUTING_MODE_DEMO,
        "live_technical_routing_enabled": live,
        "activation_confirmation": ACTIVATION_CONFIRMATION,
        "all_departments_ready": all_ready,
        "can_activate": bool(not live and all_ready and blocker_total == 0),
        "blockers": blockers,
        "department_readiness": readiness,
        "activated_at": row.activated_at.isoformat() if row and row.activated_at else None,
        "activated_by_name": activated_by.full_name if activated_by else None,
        "activation_note": row.activation_note if row else None,
        "message": message,
    }


def activate_live_routing(
    db: Session,
    *,
    actor: User,
    confirmation: str,
    note: str | None,
) -> TechnicalRoutingControl:
    if normalize_role(actor.role) != "admin":
        raise PermissionError("Only Admin can activate Phase 7 production technical routing")
    if confirmation.strip() != ACTIVATION_CONFIRMATION:
        raise ValueError(f"Type exactly: {ACTIVATION_CONFIRMATION}")
    existing = _control(db)
    if existing and existing.live_enabled:
        return existing
    status = routing_status_payload(db)
    if not status["all_departments_ready"]:
        missing = ", ".join(
            item["department_label"] for item in status["department_readiness"] if not item["live_ready"]
        )
        raise ValueError(f"All six technical directories must be live-ready before cutover. Not ready: {missing}")
    if any(status["blockers"].values()):
        b = status["blockers"]
        raise ValueError(
            "Clean-boundary cutover is blocked: "
            f"open samples={b['open_sample_requests']}, "
            f"open workstreams={b['open_technical_workstreams']}, "
            f"unresolved handovers={b['unresolved_handovers']}"
        )
    row = existing or TechnicalRoutingControl(id=1)
    row.routing_mode = ROUTING_MODE_LIVE
    row.live_enabled = True
    row.activated_by_id = actor.id
    row.activated_at = utc_now()
    row.activation_note = (note or "").strip() or None
    row.updated_at = utc_now()
    if existing is None:
        db.add(row)
    db.flush()
    return row
