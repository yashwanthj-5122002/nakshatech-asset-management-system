from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceProject
from app.modules.finance.visibility import filter_visible_project_ids
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.handover_service import DEMO_DEPARTMENT_EMAILS, DEMO_EMPLOYEE_IDS
from app.modules.operations.models import BDOpportunity, ProjectWorkstream
from app.modules.operations.monitoring_models import ProjectHandoverSchedule, ProjectWorkstreamProgress
from app.modules.operations.monitoring_schemas import ProjectHandoverScheduleUpdate, ProjectWorkstreamProgressUpdate
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_DEPARTMENT_ROLE_MAP,
    TECHNICAL_ROLE_DEPARTMENT_MAP,
    normalize_role,
    project_lifecycle_status,
)
from app.modules.operations.technical_routing_service import (
    current_routing_mode,
    is_real_department_member,
    live_routing_enabled,
)


TECHNICAL_ROLES = set(TECHNICAL_ROLE_DEPARTMENT_MAP)
STATUS_PROGRESS_ESTIMATE = {
    "planned": 0,
    "ready": 10,
    "in_progress": 50,
    "blocked": 50,
    "completed": 100,
}


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _project_opportunity(db: Session, project_id: int) -> BDOpportunity | None:
    return db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project_id))


def _ensure_bd_owner(db: Session, *, project_id: int, actor: User) -> BDOpportunity:
    opportunity = _project_opportunity(db, project_id)
    if opportunity is None or opportunity.owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can manage this project's monitoring schedule")
    if opportunity.stage in {"delivered", "closed"}:
        raise ValueError("Project monitoring schedule cannot be changed after delivery / closure")
    return opportunity


def _is_reserved_demo_manager(actor: User, row: ProjectWorkstream, effective_role: str) -> bool:
    department_code = row.department_code
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(department_code)
    return bool(
        actor.id == row.project_manager_user_id
        and normalize_role(effective_role) == expected_role
        and normalize_role(actor.role) == expected_role
        and actor.email.strip().lower() == DEMO_DEPARTMENT_EMAILS.get(department_code, "").lower()
        and actor.employee_id == DEMO_EMPLOYEE_IDS.get(department_code)
        and actor.is_active
        and actor.account_status == "active"
    )


def _is_authorized_manager(db: Session, actor: User, row: ProjectWorkstream, effective_role: str) -> bool:
    if not live_routing_enabled(db):
        return _is_reserved_demo_manager(actor, row, effective_role)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(row.department_code)
    return bool(
        actor.id == row.project_manager_user_id
        and normalize_role(effective_role) == expected_role
        and normalize_role(actor.role) == expected_role
        and actor.is_active
        and actor.account_status == "active"
        and is_real_department_member(
            db, department_code=row.department_code, user_id=actor.id, purpose="pm"
        )
    )


def update_workstream_progress(
    db: Session,
    *,
    workstream: ProjectWorkstream,
    actor: User,
    effective_role: str,
    payload: ProjectWorkstreamProgressUpdate,
) -> ProjectWorkstreamProgress:
    if not workstream.is_active:
        raise ValueError("This project workstream is inactive")
    if normalize_role(effective_role) not in TECHNICAL_ROLES:
        raise PermissionError("Only the assigned technical department Project Manager can report progress")
    if not _is_authorized_manager(db, actor, workstream, effective_role):
        if live_routing_enabled(db):
            raise PermissionError(
                "Progress updates are restricted to the assigned live production Project Manager for this department"
            )
        raise PermissionError(
            "Phase 4 UAT progress updates are restricted to the reserved demo Project Manager for this department"
        )
    if workstream.status == "completed" and payload.progress_percent != 100:
        raise ValueError("A completed workstream must report 100% progress")

    row = db.scalar(select(ProjectWorkstreamProgress).where(
        ProjectWorkstreamProgress.workstream_id == workstream.id
    ))
    note = (payload.note or "").strip() or None
    if row is None:
        row = ProjectWorkstreamProgress(
            workstream_id=workstream.id,
            progress_percent=payload.progress_percent,
            update_note=note,
            reported_by_id=actor.id,
        )
        db.add(row)
    else:
        row.progress_percent = payload.progress_percent
        row.update_note = note
        row.reported_by_id = actor.id
        row.updated_at = utc_now()
    db.flush()
    return row


def update_handover_schedule(
    db: Session,
    *,
    handover: ProjectDataHandover,
    actor: User,
    payload: ProjectHandoverScheduleUpdate,
) -> ProjectHandoverSchedule:
    if not handover.is_active:
        raise ValueError("This data handover connection is inactive")
    _ensure_bd_owner(db, project_id=handover.project_id, actor=actor)
    due_at = _naive_utc(payload.due_at)
    note = (payload.note or "").strip() or None
    row = db.scalar(select(ProjectHandoverSchedule).where(
        ProjectHandoverSchedule.handover_id == handover.id
    ))
    if row is None:
        row = ProjectHandoverSchedule(
            handover_id=handover.id,
            due_at=due_at,
            coordination_note=note,
            updated_by_id=actor.id,
        )
        db.add(row)
    else:
        row.due_at = due_at
        row.coordination_note = note
        row.updated_by_id = actor.id
        row.updated_at = utc_now()
    db.flush()
    return row


def _visible_project_ids(db: Session, *, actor: User, effective_role: str) -> tuple[str, list[int]]:
    role = normalize_role(effective_role)
    if role == "bd":
        ids = list(db.scalars(select(BDOpportunity.linked_project_id).where(
            BDOpportunity.owner_user_id == actor.id,
            BDOpportunity.linked_project_id.is_not(None),
        ).order_by(BDOpportunity.updated_at.desc())).all())
        return "bd_monitor", filter_visible_project_ids(db, [int(item) for item in ids if item is not None])
    if role in TECHNICAL_ROLES:
        department_code = TECHNICAL_ROLE_DEPARTMENT_MAP[role]
        ids = list(db.scalars(select(ProjectWorkstream.project_id).where(
            ProjectWorkstream.department_code == department_code,
            ProjectWorkstream.project_manager_user_id == actor.id,
            ProjectWorkstream.is_active.is_(True),
        ).distinct()).all())
        return "department", filter_visible_project_ids(db, [int(item) for item in ids])
    if role in {"management", "admin"}:
        ids = list(db.scalars(select(ProjectWorkstream.project_id).where(
            ProjectWorkstream.is_active.is_(True)
        ).distinct()).all())
        return "read_only", filter_visible_project_ids(db, [int(item) for item in ids])
    raise PermissionError("Master Project Monitoring is not available for this role")


def _reported_progress_map(db: Session, workstream_ids: list[int]) -> dict[int, ProjectWorkstreamProgress]:
    if not workstream_ids:
        return {}
    rows = list(db.scalars(select(ProjectWorkstreamProgress).where(
        ProjectWorkstreamProgress.workstream_id.in_(workstream_ids)
    )).all())
    return {row.workstream_id: row for row in rows}


def _schedule_map(db: Session, handover_ids: list[int]) -> dict[int, ProjectHandoverSchedule]:
    if not handover_ids:
        return {}
    rows = list(db.scalars(select(ProjectHandoverSchedule).where(
        ProjectHandoverSchedule.handover_id.in_(handover_ids)
    )).all())
    return {row.handover_id: row for row in rows}


def _workstream_monitor_payload(
    db: Session,
    row: ProjectWorkstream,
    *,
    progress: ProjectWorkstreamProgress | None,
    actor: User,
    effective_role: str,
    incoming: list[ProjectDataHandover],
    outgoing: list[ProjectDataHandover],
) -> dict:
    manager = db.get(User, row.project_manager_user_id)
    completed = row.status == "completed"
    if completed:
        effective_progress = 100
        progress_source = "workflow_completed"
    elif progress is not None:
        effective_progress = max(0, min(100, int(progress.progress_percent)))
        progress_source = "pm_reported"
    else:
        effective_progress = STATUS_PROGRESS_ESTIMATE.get(row.status, 0)
        progress_source = "status_estimate"

    unresolved = [item for item in incoming if item.status != "accepted"]
    blocked_by = []
    for item in unresolved:
        source = db.get(ProjectWorkstream, item.from_workstream_id)
        if source is not None:
            blocked_by.append({
                "handover_id": item.id,
                "handover_code": item.handover_code,
                "department_code": source.department_code,
                "department_label": TECHNICAL_DEPARTMENT_LABELS.get(source.department_code, source.department_code),
                "handover_status": item.status,
            })

    return {
        "id": row.id,
        "project_id": row.project_id,
        "department_code": row.department_code,
        "department_label": TECHNICAL_DEPARTMENT_LABELS.get(row.department_code, row.department_code),
        "project_manager_user_id": row.project_manager_user_id,
        "project_manager_name": manager.full_name if manager else None,
        "project_manager_email": manager.email if manager else None,
        "sequence_order": row.sequence_order,
        "status": row.status,
        "progress_percent": effective_progress,
        "reported_progress_percent": progress.progress_percent if progress is not None else None,
        "progress_source": progress_source,
        "progress_note": progress.update_note if progress is not None else None,
        "progress_updated_at": progress.updated_at.isoformat() if progress is not None else None,
        "incoming_dependencies": len(incoming),
        "unresolved_incoming_dependencies": len(unresolved),
        "outgoing_connections": len(outgoing),
        "blocked_by": blocked_by,
        "can_update_progress": _is_authorized_manager(db, actor, row, effective_role),
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _handover_monitor_payload(
    db: Session,
    row: ProjectDataHandover,
    *,
    schedule: ProjectHandoverSchedule | None,
    now: datetime,
    viewer_mode: str,
) -> dict:
    source = db.get(ProjectWorkstream, row.from_workstream_id)
    target = db.get(ProjectWorkstream, row.to_workstream_id)
    source_label = TECHNICAL_DEPARTMENT_LABELS.get(source.department_code, source.department_code) if source else "Source"
    target_label = TECHNICAL_DEPARTMENT_LABELS.get(target.department_code, target.department_code) if target else "Receiver"

    bottleneck_code = None
    bottleneck_label = None
    action_required = "Complete"
    if row.status == "waiting_for_source":
        bottleneck_code = source.department_code if source else None
        bottleneck_label = source_label
        action_required = f"{source_label} to submit data"
    elif row.status == "pending_receipt":
        bottleneck_code = target.department_code if target else None
        bottleneck_label = target_label
        action_required = f"{target_label} to review / accept"
    elif row.status == "revision_requested":
        bottleneck_code = source.department_code if source else None
        bottleneck_label = source_label
        action_required = f"{source_label} to correct and resubmit"

    due_at = schedule.due_at if schedule is not None else None
    overdue = bool(due_at and row.status != "accepted" and due_at < now)
    updated_at = row.updated_at or row.created_at
    age_hours = max(0.0, (now - updated_at).total_seconds() / 3600.0)

    return {
        "id": row.id,
        "handover_code": row.handover_code,
        "project_id": row.project_id,
        "from_workstream_id": row.from_workstream_id,
        "from_department_code": source.department_code if source else None,
        "from_department_label": source_label,
        "to_workstream_id": row.to_workstream_id,
        "to_department_code": target.department_code if target else None,
        "to_department_label": target_label,
        "title": row.title,
        "expected_output": row.expected_output,
        "status": row.status,
        "current_attempt_no": row.current_attempt_no,
        "revision_feedback": row.revision_feedback,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "due_at": due_at.isoformat() if due_at else None,
        "coordination_note": schedule.coordination_note if schedule is not None else None,
        "overdue": overdue,
        "age_hours": round(age_hours, 1),
        "bottleneck_department_code": bottleneck_code,
        "bottleneck_department_label": bottleneck_label,
        "action_required": action_required,
        "can_schedule": viewer_mode == "bd_monitor",
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def monitoring_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    viewer_mode, project_ids = _visible_project_ids(db, actor=actor, effective_role=effective_role)
    role = normalize_role(effective_role)
    now = utc_now()
    projects: list[dict] = []

    for project_id in project_ids:
        project = db.get(FinanceProject, project_id)
        if project is None:
            continue
        workstreams = list(db.scalars(select(ProjectWorkstream).where(
            ProjectWorkstream.project_id == project_id,
            ProjectWorkstream.is_active.is_(True),
        ).order_by(ProjectWorkstream.sequence_order.asc(), ProjectWorkstream.id.asc())).all())
        if not workstreams:
            continue
        handovers = list(db.scalars(select(ProjectDataHandover).where(
            ProjectDataHandover.project_id == project_id,
            ProjectDataHandover.is_active.is_(True),
        ).order_by(ProjectDataHandover.id.asc())).all())
        progress_map = _reported_progress_map(db, [row.id for row in workstreams])
        schedule_map = _schedule_map(db, [row.id for row in handovers])

        incoming_map: dict[int, list[ProjectDataHandover]] = defaultdict(list)
        outgoing_map: dict[int, list[ProjectDataHandover]] = defaultdict(list)
        for handover in handovers:
            incoming_map[handover.to_workstream_id].append(handover)
            outgoing_map[handover.from_workstream_id].append(handover)

        workstream_payloads = [
            _workstream_monitor_payload(
                db,
                row,
                progress=progress_map.get(row.id),
                actor=actor,
                effective_role=role,
                incoming=incoming_map.get(row.id, []),
                outgoing=outgoing_map.get(row.id, []),
            )
            for row in workstreams
        ]
        handover_payloads = [
            _handover_monitor_payload(
                db,
                row,
                schedule=schedule_map.get(row.id),
                now=now,
                viewer_mode=viewer_mode,
            )
            for row in handovers
        ]

        overall = round(sum(item["progress_percent"] for item in workstream_payloads) / len(workstream_payloads), 1)
        completed_count = sum(1 for item in workstream_payloads if item["status"] == "completed")
        blocked_count = sum(1 for item in workstream_payloads if item["status"] == "blocked")
        unresolved = [item for item in handover_payloads if item["status"] != "accepted"]
        overdue = [item for item in handover_payloads if item["overdue"]]
        revisions = [item for item in handover_payloads if item["status"] == "revision_requested"]
        pending_receipt = [item for item in handover_payloads if item["status"] == "pending_receipt"]
        bottleneck_labels = sorted({
            item["bottleneck_department_label"]
            for item in unresolved
            if item["bottleneck_department_label"]
        })

        if completed_count == len(workstream_payloads):
            health = "completed"
        elif overdue:
            health = "delayed"
        elif blocked_count or revisions:
            health = "blocked"
        elif unresolved:
            health = "attention"
        else:
            health = "on_track"

        opportunity = _project_opportunity(db, project_id)
        projects.append({
            "project_id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "client_name": project.client.client_name if project.client else project.client_name,
            "project_status": project_lifecycle_status(project),
            "opportunity_id": opportunity.id if opportunity else None,
            "opportunity_code": opportunity.opportunity_code if opportunity else None,
            "summary": {
                "overall_progress_percent": overall,
                "total_workstreams": len(workstream_payloads),
                "completed_workstreams": completed_count,
                "blocked_workstreams": blocked_count,
                "reported_workstreams": sum(1 for item in workstream_payloads if item["progress_source"] == "pm_reported"),
                "total_handovers": len(handover_payloads),
                "unresolved_handovers": len(unresolved),
                "pending_receipt_handovers": len(pending_receipt),
                "revision_handovers": len(revisions),
                "overdue_handovers": len(overdue),
                "health": health,
                "bottleneck_departments": bottleneck_labels,
            },
            "workstreams": workstream_payloads,
            "handovers": handover_payloads,
        })

    total_projects = len(projects)
    average_progress = round(
        sum(item["summary"]["overall_progress_percent"] for item in projects) / total_projects, 1
    ) if total_projects else 0.0
    return {
        "viewer_mode": viewer_mode,
        "current_role": role,
        "current_department_code": TECHNICAL_ROLE_DEPARTMENT_MAP.get(role),
        "routing_mode": current_routing_mode(db),
        "live_technical_routing_enabled": live_routing_enabled(db),
        "demo_mode": not live_routing_enabled(db),
        "summary": {
            "total_projects": total_projects,
            "average_progress_percent": average_progress,
            "delayed_projects": sum(1 for item in projects if item["summary"]["health"] == "delayed"),
            "blocked_projects": sum(1 for item in projects if item["summary"]["health"] == "blocked"),
            "unresolved_handovers": sum(item["summary"]["unresolved_handovers"] for item in projects),
            "overdue_handovers": sum(item["summary"]["overdue_handovers"] for item in projects),
        },
        "progress_method": {
            "description": "PM-reported percentage is used when available; otherwise Phase 4 uses a transparent workflow-status estimate.",
            "status_estimates": STATUS_PROGRESS_ESTIMATE,
        },
        "projects": projects,
    }
