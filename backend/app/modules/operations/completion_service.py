from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import FinanceProject
from app.modules.notifications.service import create_global_notification, resolve_recipient_users
from app.modules.operations.completion_models import MasterProjectCompletion
from app.modules.operations.completion_schemas import (
    DepartmentCompletionRequest,
    FinanceClosureUpdate,
    MasterProjectDeliveryRequest,
)
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.handover_service import DEMO_DEPARTMENT_EMAILS, DEMO_EMPLOYEE_IDS
from app.modules.operations.models import BDOpportunity, BDOpportunityEvent, ProjectWorkstream
from app.modules.operations.monitoring_models import ProjectWorkstreamProgress
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
    real_department_users,
)

logger = logging.getLogger(__name__)

TECHNICAL_ROLES = set(TECHNICAL_ROLE_DEPARTMENT_MAP)
FINANCE_STATUSES = {"pending_billing", "billing_in_progress", "financially_closed"}


def _project_opportunity(db: Session, project_id: int) -> BDOpportunity | None:
    return db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project_id))


def _active_workstreams(db: Session, project_id: int) -> list[ProjectWorkstream]:
    return list(db.scalars(select(ProjectWorkstream).where(
        ProjectWorkstream.project_id == project_id,
        ProjectWorkstream.is_active.is_(True),
    ).order_by(ProjectWorkstream.sequence_order.asc(), ProjectWorkstream.id.asc())).all())


def _active_handovers(db: Session, project_id: int) -> list[ProjectDataHandover]:
    return list(db.scalars(select(ProjectDataHandover).where(
        ProjectDataHandover.project_id == project_id,
        ProjectDataHandover.is_active.is_(True),
    ).order_by(ProjectDataHandover.id.asc())).all())


def _is_reserved_demo_manager(actor: User, row: ProjectWorkstream, effective_role: str) -> bool:
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(row.department_code)
    return bool(
        expected_role
        and row.project_manager_user_id == actor.id
        and normalize_role(effective_role) == expected_role
        and normalize_role(actor.role) == expected_role
        and actor.email.strip().lower() == DEMO_DEPARTMENT_EMAILS.get(row.department_code, "").lower()
        and actor.employee_id == DEMO_EMPLOYEE_IDS.get(row.department_code)
        and actor.is_active
        and actor.account_status == "active"
    )


def _is_authorized_manager(db: Session, actor: User, row: ProjectWorkstream, effective_role: str) -> bool:
    if not live_routing_enabled(db):
        return _is_reserved_demo_manager(actor, row, effective_role)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(row.department_code)
    return bool(
        expected_role
        and row.project_manager_user_id == actor.id
        and normalize_role(effective_role) == expected_role
        and normalize_role(actor.role) == expected_role
        and actor.is_active
        and actor.account_status == "active"
        and is_real_department_member(
            db, department_code=row.department_code, user_id=actor.id, purpose="pm"
        )
    )


def _ensure_bd_owner(db: Session, *, project_id: int, actor: User) -> BDOpportunity:
    opportunity = _project_opportunity(db, project_id)
    if opportunity is None or opportunity.owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can record Master Project final delivery")
    if opportunity.stage in {"closed"}:
        raise ValueError("This project is already closed")
    return opportunity


def assert_legacy_ortho_final_delivery_allowed(db: Session, *, project_id: int) -> None:
    """Keep legacy Ortho-only delivery intact but block premature multi-team delivery.

    V7.0.14 added a Finance notification to the legacy Ortho final-delivery route.
    For a Phase 1+ multi-department Master Project that route would be too early,
    because Ortho may finish while another peer department is still working.
    """

    workstreams = _active_workstreams(db, project_id)
    if len(workstreams) > 1:
        raise ValueError(
            "This is a multi-department Master Project. Use Project Completion after every selected department completes and every data handover is accepted."
        )


def _unresolved_incoming(db: Session, workstream_id: int) -> int:
    return int(db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.to_workstream_id == workstream_id,
        ProjectDataHandover.is_active.is_(True),
        ProjectDataHandover.status != "accepted",
    )) or 0)


def _unresolved_outgoing(db: Session, workstream_id: int) -> int:
    return int(db.scalar(select(func.count(ProjectDataHandover.id)).where(
        ProjectDataHandover.from_workstream_id == workstream_id,
        ProjectDataHandover.is_active.is_(True),
        ProjectDataHandover.status != "accepted",
    )) or 0)


def complete_department_workstream(
    db: Session,
    *,
    workstream: ProjectWorkstream,
    actor: User,
    effective_role: str,
    payload: DepartmentCompletionRequest,
) -> ProjectWorkstream:
    if not workstream.is_active:
        raise ValueError("This project workstream is inactive")
    if not _is_authorized_manager(db, actor, workstream, effective_role):
        if live_routing_enabled(db):
            raise PermissionError(
                "Department completion is restricted to the assigned live production Project Manager"
            )
        raise PermissionError(
            "Phase 5 UAT completion is restricted to the reserved demo Project Manager assigned to this department"
        )
    if workstream.status == "completed":
        return workstream
    if workstream.status != "in_progress":
        raise ValueError("Set this department workstream to In Progress before completing it")
    if _unresolved_incoming(db, workstream.id):
        raise ValueError("All incoming data handovers must be accepted before this department can complete work")
    if _unresolved_outgoing(db, workstream.id):
        raise ValueError("All outgoing data handovers must be accepted by downstream departments before this department can complete work")

    workstream.status = "completed"
    if payload.note is not None:
        workstream.notes = payload.note.strip() or None
    workstream.completed_at = utc_now()
    workstream.updated_by_id = actor.id
    workstream.updated_at = utc_now()

    progress = db.scalar(select(ProjectWorkstreamProgress).where(
        ProjectWorkstreamProgress.workstream_id == workstream.id
    ))
    if progress is None:
        progress = ProjectWorkstreamProgress(
            workstream_id=workstream.id,
            progress_percent=100,
            update_note=(payload.note or "").strip() or "Department work completed",
            reported_by_id=actor.id,
        )
        db.add(progress)
    else:
        progress.progress_percent = 100
        if payload.note is not None:
            progress.update_note = payload.note.strip() or progress.update_note
        progress.reported_by_id = actor.id
        progress.updated_at = utc_now()
    db.flush()
    return workstream


def project_completion_readiness(db: Session, *, project_id: int) -> dict:
    workstreams = _active_workstreams(db, project_id)
    handovers = _active_handovers(db, project_id)
    incomplete = [row for row in workstreams if row.status != "completed"]
    unresolved = [row for row in handovers if row.status != "accepted"]
    return {
        "ready": bool(workstreams) and not incomplete and not unresolved,
        "total_workstreams": len(workstreams),
        "completed_workstreams": len(workstreams) - len(incomplete),
        "incomplete_department_codes": [row.department_code for row in incomplete],
        "total_handovers": len(handovers),
        "accepted_handovers": len(handovers) - len(unresolved),
        "unresolved_handover_codes": [row.handover_code for row in unresolved],
    }


def record_master_project_delivery(
    db: Session,
    *,
    project_id: int,
    actor: User,
    payload: MasterProjectDeliveryRequest,
) -> MasterProjectCompletion:
    opportunity = _ensure_bd_owner(db, project_id=project_id, actor=actor)
    project = db.get(FinanceProject, project_id)
    if project is None:
        raise ValueError("Finance Project ID not found")
    readiness = project_completion_readiness(db, project_id=project_id)
    if not readiness["ready"]:
        incomplete = ", ".join(
            TECHNICAL_DEPARTMENT_LABELS.get(code, code)
            for code in readiness["incomplete_department_codes"]
        ) or "none"
        unresolved = ", ".join(readiness["unresolved_handover_codes"]) or "none"
        raise ValueError(
            f"Master Project is not ready for final delivery. Incomplete departments: {incomplete}. Unresolved handovers: {unresolved}."
        )

    existing = db.scalar(select(MasterProjectCompletion).where(
        MasterProjectCompletion.project_id == project_id
    ))
    if existing is not None:
        raise ValueError("Master Project final delivery is already recorded")

    row = MasterProjectCompletion(
        project_id=project_id,
        final_output_reference=payload.final_output_reference.strip(),
        delivery_remarks=(payload.remarks or "").strip() or None,
        delivered_by_id=actor.id,
        delivered_at=utc_now(),
        finance_status="pending_billing",
    )
    db.add(row)

    previous_stage = opportunity.stage
    opportunity.stage = "delivered"
    opportunity.updated_at = utc_now()
    db.add(BDOpportunityEvent(
        opportunity_id=opportunity.id,
        action="master_project_final_delivery",
        from_stage=previous_stage,
        to_stage="delivered",
        comments=(payload.remarks or "").strip() or "All selected technical workstreams completed; Master Project final delivery recorded.",
        actor_user_id=actor.id,
    ))
    db.flush()
    return row


def create_department_completion_notifications(db: Session, *, workstream_id: int) -> int:
    if not live_routing_enabled(db):
        return 0
    workstream = db.get(ProjectWorkstream, workstream_id)
    if workstream is None:
        return 0
    project = db.get(FinanceProject, workstream.project_id)
    recipients = real_department_users(db, department_code=workstream.department_code, purpose="completion")
    rows = []
    for recipient in recipients:
        rows.extend(create_global_notification(
            db,
            event_type="project.workstream.completed",
            title=f"{TECHNICAL_DEPARTMENT_LABELS[workstream.department_code]} workstream completed",
            message=(
                f"Project: {project.project_code if project else workstream.project_id} - "
                f"{project.project_name if project else 'Project'}\n"
                f"Department: {TECHNICAL_DEPARTMENT_LABELS[workstream.department_code]}\n"
                "Status: COMPLETED"
            ),
            category="system",
            target_url="/project-completion",
            recipient_user_ids=[recipient.id],
            dedupe_key=f"project.workstream.completed.{workstream.id}.{recipient.id}",
        ))
    return len(rows)


def deliver_department_completion_emails(db: Session, *, workstream_id: int) -> tuple[int, int]:
    if not live_routing_enabled(db):
        return 0, 0
    workstream = db.get(ProjectWorkstream, workstream_id)
    if workstream is None:
        return 0, 0
    project = db.get(FinanceProject, workstream.project_id)
    recipients = real_department_users(db, department_code=workstream.department_code, purpose="completion")
    sent = 0
    failed = 0
    for recipient in recipients:
        try:
            send_email(
                recipient=recipient.email,
                subject=f"[{project.project_code if project else workstream.project_id}] {TECHNICAL_DEPARTMENT_LABELS[workstream.department_code]} workstream completed",
                body=(
                    f"Hello {recipient.full_name or 'Technical Team'},\n\n"
                    f"Project: {project.project_code if project else workstream.project_id} - {project.project_name if project else 'Project'}\n"
                    f"Department: {TECHNICAL_DEPARTMENT_LABELS[workstream.department_code]}\n"
                    "Status: COMPLETED\n\n"
                    f"ERP Project Completion: {settings.app_public_url.rstrip('/')}/project-completion\n\n"
                    "NakshaTech ERP"
                ),
                from_name="NakshaTech Project Completion",
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Could not send department completion email to user %s", recipient.id)
    return sent, failed


def create_bd_project_ready_notification(db: Session, *, project_id: int) -> list:
    readiness = project_completion_readiness(db, project_id=project_id)
    if not readiness["ready"]:
        return []
    opportunity = _project_opportunity(db, project_id)
    project = db.get(FinanceProject, project_id)
    if opportunity is None or project is None:
        return []
    return create_global_notification(
        db,
        event_type="bd.project.ready_for_final_delivery",
        title=f"Master Project ready for final delivery: {project.project_code}",
        message=(
            f"Every selected technical department for {project.project_code} - {project.project_name} is complete "
            "and every active inter-team data handover is accepted. BD can now record Master Final Delivery."
        ),
        category="system",
        target_url="/project-completion",
        recipient_user_ids=[opportunity.owner_user_id],
        dedupe_key=f"bd.project.ready_for_final_delivery.{project.id}",
    )


def _finance_completion_message(db: Session, *, completion: MasterProjectCompletion) -> tuple[str, FinanceProject | None]:
    project = db.get(FinanceProject, completion.project_id)
    if project is None:
        return "Master Project completion recorded.", None
    client_name = project.client.client_name if project.client else project.client_name
    workstreams = _active_workstreams(db, project.id)
    departments = ", ".join(
        TECHNICAL_DEPARTMENT_LABELS.get(row.department_code, row.department_code)
        for row in workstreams
    ) or "Not recorded"
    lines = [
        f"Project: {project.project_code} - {project.project_name}",
        f"Client: {client_name or 'Not specified'}",
        f"Completed Departments: {departments}",
        f"Master Final Output: {completion.final_output_reference}",
        f"Final Delivery Date: {completion.delivered_at.date().isoformat()}",
    ]
    if completion.delivery_remarks:
        lines.append(f"Delivery Remarks: {completion.delivery_remarks}")
    lines.append("Finance action: proceed with billing, invoice/payment follow-up, settlement and financial closure as applicable.")
    return "\n".join(lines), project


def create_finance_master_completion_notifications(db: Session, *, completion_id: int) -> list:
    completion = db.get(MasterProjectCompletion, completion_id)
    if completion is None:
        return []
    message, project = _finance_completion_message(db, completion=completion)
    if project is None:
        return []
    # Reuse the established V7.0.14 event type/dedupe key so the existing Finance
    # Action Notifications panel shows the Master Project completion and duplicate
    # legacy Ortho completion notifications cannot be created for the same project.
    return create_global_notification(
        db,
        event_type="finance.project_completed",
        title=f"Master Project delivered - Finance action required: {project.project_code}",
        message=message,
        category="system",
        target_url="/project-completion",
        recipient_roles=["finance"],
        dedupe_key=f"finance.project_completed.{project.id}",
    )


def deliver_finance_master_completion_emails(db: Session, *, completion_id: int) -> tuple[int, int]:
    completion = db.get(MasterProjectCompletion, completion_id)
    if completion is None:
        return 0, 0
    message, project = _finance_completion_message(db, completion=completion)
    if project is None:
        return 0, 0
    recipients = resolve_recipient_users(db, recipient_roles=["finance"])
    body = (
        "Hello Finance Team,\n\n"
        "Business Development has recorded Master Project Final Delivery after all selected technical departments completed their work and all inter-team handovers were accepted.\n\n"
        + message
        + f"\n\nERP Project Completion: {settings.app_public_url.rstrip('/')}/project-completion\n\nNakshaTech ERP"
    )
    sent = 0
    failed = 0
    for recipient in recipients:
        try:
            send_email(
                recipient=recipient.email,
                subject=f"[{project.project_code}] Master Project delivered - Finance action required",
                body=body,
                from_name="NakshaTech BD -> Finance",
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Could not send Master Project completion email to Finance user %s", recipient.id)
    return sent, failed


def update_finance_closure(
    db: Session,
    *,
    completion: MasterProjectCompletion,
    actor: User,
    effective_role: str,
    payload: FinanceClosureUpdate,
) -> MasterProjectCompletion:
    if normalize_role(effective_role) != "finance" or normalize_role(actor.role) != "finance":
        raise PermissionError("Only Finance can update billing / financial closure status")
    if completion.finance_status == "financially_closed":
        if payload.status != "financially_closed":
            raise ValueError("Financially closed projects cannot be reopened from this workflow")
        return completion
    if payload.status == "financially_closed" and completion.finance_status == "pending_billing":
        raise ValueError("Start billing / financial closure before marking the project financially closed")

    completion.finance_status = payload.status
    completion.finance_note = (payload.note or "").strip() or None
    if payload.status == "billing_in_progress":
        completion.finance_acknowledged_by_id = actor.id
        completion.finance_acknowledged_at = completion.finance_acknowledged_at or utc_now()
    else:
        completion.finance_acknowledged_by_id = completion.finance_acknowledged_by_id or actor.id
        completion.finance_acknowledged_at = completion.finance_acknowledged_at or utc_now()
        completion.financially_closed_by_id = actor.id
        completion.financially_closed_at = utc_now()
        opportunity = _project_opportunity(db, completion.project_id)
        if opportunity is not None and opportunity.stage != "closed":
            previous_stage = opportunity.stage
            opportunity.stage = "closed"
            opportunity.updated_at = utc_now()
            db.add(BDOpportunityEvent(
                opportunity_id=opportunity.id,
                action="financial_closure_completed",
                from_stage=previous_stage,
                to_stage="closed",
                comments=(payload.note or "").strip() or "Finance marked project financially closed.",
                actor_user_id=actor.id,
            ))
    completion.updated_at = utc_now()
    db.flush()
    return completion


def create_bd_financial_closure_notification(db: Session, *, completion_id: int) -> list:
    completion = db.get(MasterProjectCompletion, completion_id)
    if completion is None or completion.finance_status != "financially_closed":
        return []
    opportunity = _project_opportunity(db, completion.project_id)
    project = db.get(FinanceProject, completion.project_id)
    if opportunity is None or project is None:
        return []
    return create_global_notification(
        db,
        event_type="bd.project.financially_closed",
        title=f"Financial closure completed: {project.project_code}",
        message=(
            f"Finance has marked {project.project_code} - {project.project_name} as financially closed. "
            "The technical Master Project was already delivered; financial follow-up is now complete."
        ),
        category="system",
        target_url="/project-completion",
        recipient_user_ids=[opportunity.owner_user_id],
        dedupe_key=f"bd.project.financially_closed.{project.id}",
    )


def _completion_payload(db: Session, row: MasterProjectCompletion | None) -> dict | None:
    if row is None:
        return None
    delivered_by = db.get(User, row.delivered_by_id)
    finance_user = db.get(User, row.finance_acknowledged_by_id) if row.finance_acknowledged_by_id else None
    closed_by = db.get(User, row.financially_closed_by_id) if row.financially_closed_by_id else None
    return {
        "id": row.id,
        "project_id": row.project_id,
        "final_output_reference": row.final_output_reference,
        "delivery_remarks": row.delivery_remarks,
        "delivered_by_name": delivered_by.full_name if delivered_by else None,
        "delivered_at": row.delivered_at.isoformat(),
        "finance_status": row.finance_status,
        "finance_note": row.finance_note,
        "finance_acknowledged_by_name": finance_user.full_name if finance_user else None,
        "finance_acknowledged_at": row.finance_acknowledged_at.isoformat() if row.finance_acknowledged_at else None,
        "financially_closed_by_name": closed_by.full_name if closed_by else None,
        "financially_closed_at": row.financially_closed_at.isoformat() if row.financially_closed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _visible_project_ids(db: Session, *, actor: User, effective_role: str) -> tuple[str, list[int]]:
    role = normalize_role(effective_role)
    if role == "bd":
        ids = list(db.scalars(select(BDOpportunity.linked_project_id).where(
            BDOpportunity.owner_user_id == actor.id,
            BDOpportunity.linked_project_id.is_not(None),
        ).order_by(BDOpportunity.updated_at.desc())).all())
        return "bd_delivery", [int(item) for item in ids if item is not None]
    if role in TECHNICAL_ROLES:
        department_code = TECHNICAL_ROLE_DEPARTMENT_MAP[role]
        ids = list(db.scalars(select(ProjectWorkstream.project_id).where(
            ProjectWorkstream.department_code == department_code,
            ProjectWorkstream.project_manager_user_id == actor.id,
            ProjectWorkstream.is_active.is_(True),
        ).distinct()).all())
        return "department", [int(item) for item in ids]
    if role == "finance":
        ids = list(db.scalars(select(MasterProjectCompletion.project_id).order_by(
            MasterProjectCompletion.delivered_at.desc()
        )).all())
        return "finance_closure", [int(item) for item in ids]
    if role in {"management", "admin"}:
        ids = list(db.scalars(select(ProjectWorkstream.project_id).where(
            ProjectWorkstream.is_active.is_(True)
        ).distinct()).all())
        return "read_only", [int(item) for item in ids]
    raise PermissionError("Project Completion is not available for this role")


def completion_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    viewer_mode, project_ids = _visible_project_ids(db, actor=actor, effective_role=effective_role)
    role = normalize_role(effective_role)
    projects: list[dict] = []

    for project_id in project_ids:
        project = db.get(FinanceProject, project_id)
        if project is None:
            continue
        workstreams = _active_workstreams(db, project_id)
        if not workstreams and role != "finance":
            continue
        handovers = _active_handovers(db, project_id)
        completion = db.scalar(select(MasterProjectCompletion).where(
            MasterProjectCompletion.project_id == project_id
        ))
        readiness = project_completion_readiness(db, project_id=project_id)
        opportunity = _project_opportunity(db, project_id)
        manager_ids = [row.project_manager_user_id for row in workstreams]
        managers = {
            user.id: user for user in db.scalars(select(User).where(User.id.in_(manager_ids))).all()
        } if manager_ids else {}
        incoming: dict[int, list[ProjectDataHandover]] = defaultdict(list)
        outgoing: dict[int, list[ProjectDataHandover]] = defaultdict(list)
        for handover in handovers:
            incoming[handover.to_workstream_id].append(handover)
            outgoing[handover.from_workstream_id].append(handover)

        workstream_payloads = []
        for row in workstreams:
            manager = managers.get(row.project_manager_user_id)
            unresolved_in = sum(1 for item in incoming.get(row.id, []) if item.status != "accepted")
            unresolved_out = sum(1 for item in outgoing.get(row.id, []) if item.status != "accepted")
            can_complete = bool(
                completion is None
                and row.status == "in_progress"
                and unresolved_in == 0
                and unresolved_out == 0
                and _is_authorized_manager(db, actor, row, role)
            )
            workstream_payloads.append({
                "id": row.id,
                "department_code": row.department_code,
                "department_label": TECHNICAL_DEPARTMENT_LABELS.get(row.department_code, row.department_code),
                "project_manager_user_id": row.project_manager_user_id,
                "project_manager_name": manager.full_name if manager else None,
                "status": row.status,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "incoming_handovers": len(incoming.get(row.id, [])),
                "unresolved_incoming": unresolved_in,
                "outgoing_handovers": len(outgoing.get(row.id, [])),
                "unresolved_outgoing": unresolved_out,
                "can_complete": can_complete,
            })

        client_name = project.client.client_name if project.client else project.client_name
        projects.append({
            "project_id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "client_name": client_name,
            "project_status": project_lifecycle_status(project),
            "opportunity_id": opportunity.id if opportunity else None,
            "opportunity_code": opportunity.opportunity_code if opportunity else None,
            "readiness": readiness,
            "workstreams": workstream_payloads,
            "completion": _completion_payload(db, completion),
            "permissions": {
                "can_deliver": bool(viewer_mode == "bd_delivery" and completion is None and readiness["ready"]),
                "can_update_finance": bool(viewer_mode == "finance_closure" and completion is not None),
            },
        })

    return {
        "viewer_mode": viewer_mode,
        "current_role": role,
        "routing_mode": current_routing_mode(db),
        "live_technical_routing_enabled": live_routing_enabled(db),
        "demo_mode": not live_routing_enabled(db),
        "summary": {
            "visible_projects": len(projects),
            "ready_for_delivery": sum(1 for item in projects if item["readiness"]["ready"] and item["completion"] is None),
            "delivered_projects": sum(1 for item in projects if item["completion"] is not None),
            "pending_finance": sum(1 for item in projects if item["completion"] and item["completion"]["finance_status"] != "financially_closed"),
            "financially_closed": sum(1 for item in projects if item["completion"] and item["completion"]["finance_status"] == "financially_closed"),
        },
        "projects": projects,
    }
