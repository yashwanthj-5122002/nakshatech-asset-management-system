from __future__ import annotations

import logging
import re
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import FinanceProject
from app.modules.notifications.service import create_global_notification
from app.modules.operations.handover_models import ProjectDataHandover, ProjectDataHandoverAttempt
from app.modules.operations.handover_schemas import (
    ProjectDataHandoverCreate,
    ProjectDataHandoverDecision,
    ProjectDataHandoverSubmit,
)
from app.modules.operations.models import BDOpportunity, ProjectWorkstream
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_DEPARTMENT_ROLE_MAP,
    TECHNICAL_ROLE_DEPARTMENT_MAP,
    normalize_role,
)
from app.modules.operations.technical_routing_service import (
    current_routing_mode,
    is_real_department_member,
    live_routing_enabled,
    real_department_users,
    validate_live_project_manager,
)

logger = logging.getLogger(__name__)

HANDOVER_STATUSES = {
    "waiting_for_source",
    "pending_receipt",
    "revision_requested",
    "accepted",
}

# Phase 3 remains UAT-only for technical email recipients. Real team addresses
# are not activated until the full multi-department workflow has been accepted.
DEMO_DEPARTMENT_EMAILS = {
    "ortho": "ortho.demo@nakshatech.com",
    "lidar": "lidar.demo@nakshatech.com",
    "civil": "civil.demo@nakshatech.com",
    "laser_scanning": "laser.scanning.demo@nakshatech.com",
    "bim": "bim.demo@nakshatech.com",
    "mobile_mapping": "mobile.mapping.demo@nakshatech.com",
}
DEMO_EMPLOYEE_IDS = {
    "ortho": "DEMO-V715-ORTHO-PM",
    "lidar": "DEMO-V715-LIDAR-PM",
    "civil": "DEMO-V715-CIVIL-PM",
    "laser_scanning": "DEMO-V715-LASER-PM",
    "bim": "DEMO-V715-BIM-PM",
    "mobile_mapping": "DEMO-V715-MOBILE-PM",
}


def _handover_code(db: Session) -> str:
    year = utc_now().year
    prefix = f"HDO-{year}-"
    codes = list(db.scalars(select(ProjectDataHandover.handover_code).where(
        ProjectDataHandover.handover_code.like(f"{prefix}%")
    )).all())
    highest = 0
    for code in codes:
        match = re.search(r"(\d+)$", code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}{highest + 1:04d}"


def _demo_user_for_department(db: Session, department_code: str) -> User:
    email = DEMO_DEPARTMENT_EMAILS.get(department_code)
    employee_id = DEMO_EMPLOYEE_IDS.get(department_code)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(department_code)
    if not email or not employee_id or not expected_role:
        raise ValueError(f"Unsupported technical department: {department_code}")
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if (
        user is None
        or user.employee_id != employee_id
        or normalize_role(user.role) != expected_role
        or not user.is_active
        or user.account_status != "active"
    ):
        raise ValueError(
            f"Phase 3 demo account for {TECHNICAL_DEPARTMENT_LABELS[department_code]} is missing or inactive: {email}"
        )
    return user


def _project_opportunity(db: Session, project_id: int) -> BDOpportunity | None:
    return db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project_id))


def _project_workstream(db: Session, workstream_id: int) -> ProjectWorkstream:
    row = db.get(ProjectWorkstream, workstream_id)
    if row is None or not row.is_active:
        raise ValueError("Selected technical project workstream was not found or is inactive")
    return row


def _validate_demo_workstream_manager(db: Session, row: ProjectWorkstream) -> User:
    expected = _demo_user_for_department(db, row.department_code)
    if row.project_manager_user_id != expected.id:
        raise ValueError(
            f"Phase 3 UAT requires the reserved demo {TECHNICAL_DEPARTMENT_LABELS[row.department_code]} PM on this workstream"
        )
    return expected


def _validate_routed_workstream_manager(db: Session, row: ProjectWorkstream) -> User:
    if live_routing_enabled(db):
        return validate_live_project_manager(db, department_code=row.department_code, user_id=row.project_manager_user_id)
    return _validate_demo_workstream_manager(db, row)


def _workstream_manager_is_routed(db: Session, row: ProjectWorkstream) -> bool:
    try:
        _validate_routed_workstream_manager(db, row)
        return True
    except (ValueError, PermissionError):
        return False


def _handover_recipients(db: Session, row: ProjectWorkstream) -> list[User]:
    if not live_routing_enabled(db):
        return [_validate_demo_workstream_manager(db, row)]

    recipients = list(real_department_users(db, department_code=row.department_code, purpose="handover"))
    manager = db.get(User, row.project_manager_user_id) if row.project_manager_user_id else None
    if manager and is_real_department_member(
        db, department_code=row.department_code, user_id=manager.id, purpose="pm"
    ) and all(user.id != manager.id for user in recipients):
        recipients.insert(0, manager)
    if not recipients:
        raise ValueError(
            f"No live handover recipient is configured for {TECHNICAL_DEPARTMENT_LABELS[row.department_code]}"
        )
    return recipients


def _ensure_bd_owner(db: Session, *, project_id: int, actor: User) -> BDOpportunity:
    opportunity = _project_opportunity(db, project_id)
    if opportunity is None or opportunity.owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can configure technical team connections for this project")
    if opportunity.stage in {"delivered", "closed"}:
        raise ValueError("Technical handovers cannot be configured after project delivery / closure")
    return opportunity


def _would_create_cycle(db: Session, *, project_id: int, source_id: int, target_id: int) -> bool:
    edges: dict[int, set[int]] = defaultdict(set)
    rows = list(db.scalars(select(ProjectDataHandover).where(
        ProjectDataHandover.project_id == project_id,
        ProjectDataHandover.is_active.is_(True),
    )).all())
    for row in rows:
        edges[row.from_workstream_id].add(row.to_workstream_id)
    edges[source_id].add(target_id)

    visiting: set[int] = set()
    visited: set[int] = set()

    def visit(node: int) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in edges.get(node, set()):
            if visit(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in list(edges))


def create_project_handover(
    db: Session,
    *,
    actor: User,
    payload: ProjectDataHandoverCreate,
) -> ProjectDataHandover:
    _ensure_bd_owner(db, project_id=payload.project_id, actor=actor)
    project = db.get(FinanceProject, payload.project_id)
    if project is None:
        raise ValueError("Finance Project ID not found")

    source = _project_workstream(db, payload.from_workstream_id)
    target = _project_workstream(db, payload.to_workstream_id)
    if source.project_id != project.id or target.project_id != project.id:
        raise ValueError("Both connected departments must belong to the same master Project ID")
    if source.id == target.id:
        raise ValueError("A technical department cannot hand over data to itself")
    if target.status in {"in_progress", "completed"}:
        raise ValueError("Create the dependency before the receiving department starts work")

    # UAT uses the reserved demo PMs. After the explicit Phase 7 cutover,
    # both ends must be assigned to Phase 6 live-ready PMs.
    _validate_routed_workstream_manager(db, source)
    _validate_routed_workstream_manager(db, target)

    existing = db.scalar(select(ProjectDataHandover).where(
        ProjectDataHandover.project_id == project.id,
        ProjectDataHandover.from_workstream_id == source.id,
        ProjectDataHandover.to_workstream_id == target.id,
    ))
    if existing is not None and existing.is_active:
        raise ValueError("This department-to-department connection already exists for the project")
    if _would_create_cycle(db, project_id=project.id, source_id=source.id, target_id=target.id):
        raise ValueError("This connection would create a circular department dependency")

    if existing is not None:
        # A connection removed before its first transfer can be safely reactivated
        # without violating the project/from/to uniqueness constraint.
        existing.title = payload.title.strip()
        existing.expected_output = payload.expected_output.strip()
        existing.status = "waiting_for_source"
        existing.current_attempt_no = 0
        existing.revision_feedback = None
        existing.accepted_by_id = None
        existing.accepted_at = None
        existing.created_by_id = actor.id
        existing.is_active = True
        existing.updated_at = utc_now()
        db.flush()
        return existing

    row = ProjectDataHandover(
        handover_code=_handover_code(db),
        project_id=project.id,
        from_workstream_id=source.id,
        to_workstream_id=target.id,
        title=payload.title.strip(),
        expected_output=payload.expected_output.strip(),
        status="waiting_for_source",
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def deactivate_project_handover(db: Session, *, actor: User, handover: ProjectDataHandover) -> ProjectDataHandover:
    _ensure_bd_owner(db, project_id=handover.project_id, actor=actor)
    if handover.current_attempt_no > 0 or handover.status != "waiting_for_source":
        raise ValueError("A handover connection can be removed only before the first data submission")
    target = _receiver_workstream(db, handover)
    handover.is_active = False
    handover.updated_at = utc_now()
    db.flush()
    unresolved = db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.to_workstream_id == target.id,
        ProjectDataHandover.is_active.is_(True),
        ProjectDataHandover.status != "accepted",
    )) or 0
    if unresolved == 0 and target.status == "planned":
        target.status = "ready"
        target.updated_by_id = actor.id
        target.updated_at = utc_now()
    db.flush()
    return handover


def _sender_workstream(db: Session, handover: ProjectDataHandover) -> ProjectWorkstream:
    return _project_workstream(db, handover.from_workstream_id)


def _receiver_workstream(db: Session, handover: ProjectDataHandover) -> ProjectWorkstream:
    return _project_workstream(db, handover.to_workstream_id)


def _assert_sender(db: Session, *, handover: ProjectDataHandover, actor: User, effective_role: str) -> ProjectWorkstream:
    source = _sender_workstream(db, handover)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(source.department_code)
    manager = _validate_routed_workstream_manager(db, source)
    if normalize_role(effective_role) != expected_role or actor.id != source.project_manager_user_id or actor.id != manager.id:
        mode = "live" if live_routing_enabled(db) else "demo"
        raise PermissionError(f"Only the assigned {mode} Project Manager of the sending department can submit this handover")
    return source


def _assert_receiver(db: Session, *, handover: ProjectDataHandover, actor: User, effective_role: str) -> ProjectWorkstream:
    target = _receiver_workstream(db, handover)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(target.department_code)
    manager = _validate_routed_workstream_manager(db, target)
    if normalize_role(effective_role) != expected_role or actor.id != target.project_manager_user_id or actor.id != manager.id:
        mode = "live" if live_routing_enabled(db) else "demo"
        raise PermissionError(f"Only the assigned {mode} Project Manager of the receiving department can decide this handover")
    return target


def submit_project_handover(
    db: Session,
    *,
    handover: ProjectDataHandover,
    actor: User,
    effective_role: str,
    payload: ProjectDataHandoverSubmit,
) -> ProjectDataHandoverAttempt:
    if not handover.is_active:
        raise ValueError("This data handover connection is inactive")
    source = _assert_sender(db, handover=handover, actor=actor, effective_role=effective_role)
    if source.status not in {"in_progress", "completed"}:
        raise ValueError("Start the sending department workstream before transferring project data")
    if handover.status not in {"waiting_for_source", "revision_requested"}:
        raise ValueError("This handover is not waiting for a sender submission")

    attempt_no = handover.current_attempt_no + 1
    attempt = ProjectDataHandoverAttempt(
        handover_id=handover.id,
        attempt_no=attempt_no,
        output_reference=payload.output_reference.strip(),
        notes=(payload.notes or "").strip() or None,
        submitted_by_id=actor.id,
    )
    db.add(attempt)
    handover.current_attempt_no = attempt_no
    handover.status = "pending_receipt"
    handover.revision_feedback = None
    handover.accepted_by_id = None
    handover.accepted_at = None
    handover.updated_at = utc_now()
    db.flush()
    return attempt


def decide_project_handover(
    db: Session,
    *,
    handover: ProjectDataHandover,
    actor: User,
    effective_role: str,
    payload: ProjectDataHandoverDecision,
) -> ProjectDataHandover:
    if not handover.is_active:
        raise ValueError("This data handover connection is inactive")
    target = _assert_receiver(db, handover=handover, actor=actor, effective_role=effective_role)
    if handover.status != "pending_receipt":
        raise ValueError("The receiving department can decide only a pending data handover")

    feedback = (payload.feedback or "").strip() or None
    if payload.decision == "revision_requested":
        if not feedback:
            raise ValueError("Enter correction / revision feedback for the sending department")
        handover.status = "revision_requested"
        handover.revision_feedback = feedback
        handover.accepted_by_id = None
        handover.accepted_at = None
    else:
        handover.status = "accepted"
        handover.revision_feedback = None
        handover.accepted_by_id = actor.id
        handover.accepted_at = utc_now()
        # The receiving workstream becomes READY only when every active upstream
        # connection into that workstream has been accepted.
        unresolved = db.scalar(select(func.count(ProjectDataHandover.id)).where(
            ProjectDataHandover.to_workstream_id == target.id,
            ProjectDataHandover.is_active.is_(True),
            ProjectDataHandover.id != handover.id,
            ProjectDataHandover.status != "accepted",
        )) or 0
        if unresolved == 0 and target.status == "planned":
            target.status = "ready"
            target.updated_by_id = actor.id
            target.updated_at = utc_now()
    handover.updated_at = utc_now()
    db.flush()
    return handover


def _project_name(project: FinanceProject | None) -> str:
    if project is None:
        return "Unknown project"
    return f"{project.project_code} - {project.project_name}"


def _latest_attempt(handover: ProjectDataHandover) -> ProjectDataHandoverAttempt | None:
    return handover.attempts[-1] if handover.attempts else None


def handover_payload(db: Session, row: ProjectDataHandover, *, actor: User | None = None, effective_role: str | None = None) -> dict:
    project = db.get(FinanceProject, row.project_id)
    source = db.get(ProjectWorkstream, row.from_workstream_id)
    target = db.get(ProjectWorkstream, row.to_workstream_id)
    source_manager = db.get(User, source.project_manager_user_id) if source else None
    target_manager = db.get(User, target.project_manager_user_id) if target else None
    latest = _latest_attempt(row)
    submitter = db.get(User, latest.submitted_by_id) if latest else None
    role = normalize_role(effective_role) if effective_role else None
    source_manager_valid = _workstream_manager_is_routed(db, source) if source else False
    target_manager_valid = _workstream_manager_is_routed(db, target) if target else False
    can_submit = bool(
        actor and source and source_manager_valid and actor.id == source.project_manager_user_id
        and role == TECHNICAL_DEPARTMENT_ROLE_MAP.get(source.department_code)
        and row.status in {"waiting_for_source", "revision_requested"}
    )
    can_decide = bool(
        actor and target and target_manager_valid and actor.id == target.project_manager_user_id
        and role == TECHNICAL_DEPARTMENT_ROLE_MAP.get(target.department_code)
        and row.status == "pending_receipt"
    )
    return {
        "id": row.id,
        "handover_code": row.handover_code,
        "project_id": row.project_id,
        "project_code": project.project_code if project else None,
        "project_name": project.project_name if project else None,
        "from_workstream_id": row.from_workstream_id,
        "from_department_code": source.department_code if source else None,
        "from_department_label": TECHNICAL_DEPARTMENT_LABELS.get(source.department_code, source.department_code) if source else None,
        "from_manager_name": source_manager.full_name if source_manager else None,
        "to_workstream_id": row.to_workstream_id,
        "to_department_code": target.department_code if target else None,
        "to_department_label": TECHNICAL_DEPARTMENT_LABELS.get(target.department_code, target.department_code) if target else None,
        "to_manager_name": target_manager.full_name if target_manager else None,
        "title": row.title,
        "expected_output": row.expected_output,
        "status": row.status,
        "current_attempt_no": row.current_attempt_no,
        "revision_feedback": row.revision_feedback,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "is_active": bool(row.is_active),
        "latest_attempt": None if latest is None else {
            "attempt_no": latest.attempt_no,
            "output_reference": latest.output_reference,
            "notes": latest.notes,
            "submitted_by_name": submitter.full_name if submitter else None,
            "submitted_at": latest.submitted_at.isoformat(),
        },
        "permissions": {"can_submit": can_submit, "can_decide": can_decide},
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _workstream_payload(db: Session, row: ProjectWorkstream) -> dict:
    manager = db.get(User, row.project_manager_user_id)
    incoming_unresolved = db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.to_workstream_id == row.id,
        ProjectDataHandover.is_active.is_(True),
        ProjectDataHandover.status != "accepted",
    )) or 0
    incoming_total = db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.to_workstream_id == row.id,
        ProjectDataHandover.is_active.is_(True),
    )) or 0
    outgoing_total = db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.from_workstream_id == row.id,
        ProjectDataHandover.is_active.is_(True),
    )) or 0
    return {
        "id": row.id,
        "department_code": row.department_code,
        "department_label": TECHNICAL_DEPARTMENT_LABELS.get(row.department_code, row.department_code),
        "project_manager_user_id": row.project_manager_user_id,
        "project_manager_name": manager.full_name if manager else None,
        "project_manager_email": manager.email if manager else None,
        "sequence_order": row.sequence_order,
        "status": row.status,
        "incoming_dependencies": int(incoming_total),
        "unresolved_incoming_dependencies": int(incoming_unresolved),
        "outgoing_connections": int(outgoing_total),
    }


def handover_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    role = normalize_role(effective_role)
    technical = role in TECHNICAL_ROLE_DEPARTMENT_MAP
    if role == "bd":
        opportunities = list(db.scalars(select(BDOpportunity).where(
            BDOpportunity.owner_user_id == actor.id,
            BDOpportunity.linked_project_id.is_not(None),
        ).order_by(BDOpportunity.updated_at.desc())).all())
        project_ids = [row.linked_project_id for row in opportunities if row.linked_project_id is not None]
        viewer_mode = "bd_editor"
    elif technical:
        own_workstreams = list(db.scalars(select(ProjectWorkstream).where(
            ProjectWorkstream.project_manager_user_id == actor.id,
            ProjectWorkstream.department_code == TECHNICAL_ROLE_DEPARTMENT_MAP[role],
            ProjectWorkstream.is_active.is_(True),
        )).all())
        project_ids = sorted({row.project_id for row in own_workstreams})
        viewer_mode = "department"
    elif role in {"management", "admin"}:
        project_ids = list(db.scalars(select(ProjectWorkstream.project_id).where(
            ProjectWorkstream.is_active.is_(True)
        ).distinct()).all())
        viewer_mode = "read_only"
    else:
        raise PermissionError("Project Data Handovers are not available for this role")

    projects: list[dict] = []
    for project_id in project_ids:
        project = db.get(FinanceProject, project_id)
        if project is None:
            continue
        workstreams = list(db.scalars(select(ProjectWorkstream).where(
            ProjectWorkstream.project_id == project_id,
            ProjectWorkstream.is_active.is_(True),
        ).order_by(ProjectWorkstream.sequence_order.asc(), ProjectWorkstream.id.asc())).all())
        rows = list(db.scalars(select(ProjectDataHandover).where(
            ProjectDataHandover.project_id == project_id,
            ProjectDataHandover.is_active.is_(True),
        ).order_by(ProjectDataHandover.id.asc())).all())
        if technical:
            own_ids = {
                row.id for row in workstreams
                if row.project_manager_user_id == actor.id
                and row.department_code == TECHNICAL_ROLE_DEPARTMENT_MAP[role]
            }
            rows = [row for row in rows if row.from_workstream_id in own_ids or row.to_workstream_id in own_ids]
            workstreams_for_payload = [row for row in workstreams if row.id in own_ids]
        else:
            workstreams_for_payload = workstreams
        projects.append({
            "project_id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "client_name": project.client.client_name if project.client else project.client_name,
            "workstreams": [_workstream_payload(db, row) for row in workstreams_for_payload],
            "all_workstreams": [_workstream_payload(db, row) for row in workstreams] if role == "bd" else [],
            "handovers": [handover_payload(db, row, actor=actor, effective_role=role) for row in rows],
        })

    return {
        "viewer_mode": viewer_mode,
        "current_role": role,
        "current_department_code": TECHNICAL_ROLE_DEPARTMENT_MAP.get(role),
        "routing_mode": current_routing_mode(db),
        "live_technical_routing_enabled": live_routing_enabled(db),
        "demo_mode": not live_routing_enabled(db),
        "projects": projects,
    }


def _handover_message(db: Session, handover: ProjectDataHandover) -> tuple[str, ProjectWorkstream, ProjectWorkstream]:
    source = _sender_workstream(db, handover)
    target = _receiver_workstream(db, handover)
    project = db.get(FinanceProject, handover.project_id)
    latest = _latest_attempt(handover)
    message = "\n".join([
        f"Project: {_project_name(project)}",
        f"Handover: {handover.handover_code} - {handover.title}",
        f"From: {TECHNICAL_DEPARTMENT_LABELS[source.department_code]}",
        f"To: {TECHNICAL_DEPARTMENT_LABELS[target.department_code]}",
        f"Expected Output: {handover.expected_output}",
        f"Attempt: {handover.current_attempt_no}",
        f"Output Reference: {latest.output_reference if latest else 'Not submitted'}",
        f"Notes: {(latest.notes if latest else None) or 'None'}",
    ])
    return message, source, target


def create_receiver_handover_notification(db: Session, *, handover_id: int) -> int:
    handover = db.get(ProjectDataHandover, handover_id)
    if handover is None:
        return 0
    message, _source, target = _handover_message(db, handover)
    recipients = _handover_recipients(db, target)
    rows = []
    for receiver in recipients:
        rows.extend(create_global_notification(
            db,
            event_type="project.handover.pending_receipt",
            title=f"Data handover ready: {handover.handover_code}",
            message=message + "\nAction: review and Accept or Request Correction.",
            category="system",
            target_url="/project-handovers",
            recipient_user_ids=[receiver.id],
            dedupe_key=f"project.handover.pending.{handover.id}.{handover.current_attempt_no}.{receiver.id}",
        ))
    return len(rows)


def deliver_receiver_handover_email(db: Session, *, handover_id: int) -> tuple[int, int]:
    handover = db.get(ProjectDataHandover, handover_id)
    if handover is None:
        return 0, 0
    message, _source, target = _handover_message(db, handover)
    recipients = _handover_recipients(db, target)
    sent = 0
    failed = 0
    for receiver in recipients:
        try:
            greeting = receiver.full_name or "Technical Team"
            send_email(
                recipient=receiver.email,
                subject=f"[{handover.handover_code}] Project data ready for {TECHNICAL_DEPARTMENT_LABELS[target.department_code]}",
                body=(
                    f"Hello {greeting},\n\n"
                    + message
                    + f"\n\nERP Data Handovers: {settings.app_public_url.rstrip('/')}/project-handovers\n\nNakshaTech ERP"
                ),
                from_name="NakshaTech Project Data Handover",
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Could not send handover email to user %s", receiver.id)
    return sent, failed


def create_sender_decision_notification(db: Session, *, handover_id: int) -> int:
    handover = db.get(ProjectDataHandover, handover_id)
    if handover is None:
        return 0
    message, source, target = _handover_message(db, handover)
    recipients = _handover_recipients(db, source)
    if handover.status == "accepted":
        title = f"Data handover accepted: {handover.handover_code}"
        action = f"{TECHNICAL_DEPARTMENT_LABELS[target.department_code]} accepted the handover."
        event = "project.handover.accepted"
    else:
        title = f"Data handover correction requested: {handover.handover_code}"
        action = f"Correction requested: {handover.revision_feedback or 'See ERP feedback'}"
        event = "project.handover.revision_requested"
    rows = []
    for sender in recipients:
        rows.extend(create_global_notification(
            db,
            event_type=event,
            title=title,
            message=message + "\n" + action,
            category="system",
            target_url="/project-handovers",
            recipient_user_ids=[sender.id],
            dedupe_key=f"{event}.{handover.id}.{handover.current_attempt_no}.{sender.id}",
        ))
    return len(rows)


def deliver_sender_decision_email(db: Session, *, handover_id: int) -> tuple[int, int]:
    handover = db.get(ProjectDataHandover, handover_id)
    if handover is None:
        return 0, 0
    message, source, target = _handover_message(db, handover)
    recipients = _handover_recipients(db, source)
    if handover.status == "accepted":
        subject = f"[{handover.handover_code}] Data accepted by {TECHNICAL_DEPARTMENT_LABELS[target.department_code]}"
        extra = "The receiving department accepted the handover."
    else:
        subject = f"[{handover.handover_code}] Data correction requested"
        extra = f"Feedback: {handover.revision_feedback or 'See ERP'}"
    sent = 0
    failed = 0
    for sender in recipients:
        try:
            greeting = sender.full_name or "Technical Team"
            send_email(
                recipient=sender.email,
                subject=subject,
                body=(
                    f"Hello {greeting},\n\n"
                    + message
                    + "\n"
                    + extra
                    + f"\n\nERP Data Handovers: {settings.app_public_url.rstrip('/')}/project-handovers\n\nNakshaTech ERP"
                ),
                from_name="NakshaTech Project Data Handover",
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Could not send handover decision email to user %s", sender.id)
    return sent, failed
