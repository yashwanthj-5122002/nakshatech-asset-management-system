"""BD Employee notifications linked to authoritative BD-owned projects.

Only existing, authorized client/project links may receive a milestone. Caller
must be operating inside the existing workflow transaction (no independent commit).
"""
from __future__ import annotations

from datetime import datetime
import logging
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.bd_employee.handoff_models import BdEmployeeProjectLink
from app.modules.bd_employee.models import BdEmployeeProspect, BdEmployeeContactActivity
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.notifications.service import create_global_notification
from app.modules.operations.models import OrthoWorkPackage, ProjectWorkflow

# No client creation, Finance review or PM assignment notifications.
logger = logging.getLogger(__name__)
PROJECT_EVENTS = {
    "production_started": ("Production Started", "Production has started for Project {code}."),
    "production_completed": ("Production Completed", "Production is complete for Project {code}. The project is proceeding to QC."),
    "qc_completed": ("QC Completed", "Quality Control is complete for Project {code}. The project is proceeding to QA."),
    "qa_completed": ("QA Completed", "Quality Assurance is complete for Project {code}. The project is ready for delivery."),
    "project_delivered": ("Project Delivered", "Project {code} has been delivered to the client."),
    "client_feedback_updated": ("Client Feedback Updated", "Client feedback has been recorded for Project {code}."),
    "project_closed": ("Project Closed", "Project {code} has been officially closed."),
}


def _eligible_recipients(db: Session, project_id: int) -> list[int]:
    project = db.get(FinanceProject, project_id)
    if not project or project.project_source_team != "bd_team":
        return []
    client = db.get(FinanceClient, project.client_id)
    if not client or client.source_team != "bd_team":
        return []
    workflow = db.get(ProjectWorkflow, project_id)
    candidates = {project.created_by_id, client.created_by_id}
    if workflow:
        candidates.add(workflow.bd_owner_user_id)
    candidates.update(db.scalars(select(BdEmployeeProjectLink.employee_user_id).where(
        BdEmployeeProjectLink.project_id == project_id,
    )).all())

    # Reuse exactly the ownership boundary from employee Project Management.
    # Import lazily because direct_router itself imports workflow_service.
    from app.modules.bd_employee.direct_router import _business_project_ids
    recipients = []
    for user_id in candidates:
        if not user_id:
            continue
        employee = db.get(User, user_id)
        if (employee is None or employee.role != "bd_employee" or not employee.is_active
                or employee.account_status != "active"):
            continue
        if project_id in _business_project_ids(db, employee):
            recipients.append(employee.id)
    return sorted(set(recipients))


def notify_project_milestone(
    db: Session, *, project_id: int, milestone: str, event_id: int | None = None,
) -> None:
    if milestone not in PROJECT_EVENTS:
        raise ValueError("Unknown BD employee project milestone")
    project = db.get(FinanceProject, project_id)
    if project is None:
        return
    recipients = _eligible_recipients(db, project_id)
    if not recipients:
        return
    title, message_template = PROJECT_EVENTS[milestone]
    identity = f"{project_id}:{milestone}"
    if event_id is not None:
        identity += f":{event_id}"
    create_global_notification(
        db, event_type=f"bd_employee.project.{milestone}",
        category="system", title=f"{title}: {project.project_code}",
        message=message_template.format(code=project.project_code),
        target_url="/bd-employee/tracking" if milestone != "client_feedback_updated" else "/bd-employee/notifications",
        recipient_user_ids=recipients,
        dedupe_key=f"bd-employee-project:{identity}",
    )


def notify_completed_stage(db: Session, *, project_id: int, stage: str) -> None:
    """Only whole-project stage completion; never one package's completion."""
    if stage not in {"production", "qc", "qa"}:
        raise ValueError("Invalid completion stage")
    packages = list(db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.project_id == project_id,
        OrthoWorkPackage.rework_cycle_id.is_(None),
    )).all())
    if not packages:
        return
    # These explicit package flags are authoritative for area-level (legacy)
    # packages. File-tracked projects may defer until their parent rollups are
    # synchronized, rather than issuing a premature whole-project alert.
    attr, value = {
        "production": ("production_state", "completed"),
        "qc": ("qc_state", "approved"),
        "qa": ("qa_state", "approved"),
    }[stage]
    if all(getattr(pkg, attr, None) == value for pkg in packages):
        notify_project_milestone(db, project_id=project_id, milestone=f"{stage}_completed")


def ensure_due_followup_reminders(db: Session, *, owner_user_id: int) -> int:
    """Materialize only reminders supported by structured BD prospect data.

    Prospect records have a follow-up DATE but no time, tender deadline or
    quotation send timestamp. Do not infer those missing facts from notes.
    """
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    leads = db.scalars(select(BdEmployeeProspect).where(
        BdEmployeeProspect.owner_user_id == owner_user_id,
        BdEmployeeProspect.next_followup_date.is_not(None),
        BdEmployeeProspect.next_followup_date <= today,
        BdEmployeeProspect.status.not_in(("won", "not_interested")),
    )).all()
    created = 0
    for lead in leads:
        history = db.scalar(select(BdEmployeeContactActivity).where(
            BdEmployeeContactActivity.owner_user_id == owner_user_id,
            BdEmployeeContactActivity.prospect_id == lead.id,
        ).order_by(BdEmployeeContactActivity.contacted_at.desc(), BdEmployeeContactActivity.id.desc()).limit(1))
        if lead.status == "no_response":
            kind, title = "pending_response", "Pending Client Response"
            message = f"No client response recorded for {lead.company_name}. Follow-up due {lead.next_followup_date.isoformat()}."
        elif history and history.channel == "phone" and history.outcome == "callback":
            kind, title = "call_reminder", "Client Call Reminder"
            message = f"Call {lead.company_name} for the scheduled follow-up on {lead.next_followup_date.isoformat()}."
        else:
            # Meeting schedule, tender/proposal deadlines, quotation submission
            # and pending scope have no authoritative structured dates here.
            continue
        rows = create_global_notification(
            db, event_type=f"bd_employee.reminder.{kind}",
            title=title, message=message, category="system",
            target_url="/bd-employee/lead-hub/followups",
            recipient_user_ids=[owner_user_id],
            dedupe_key=f"bd-employee-reminder:{kind}:{lead.id}:{lead.next_followup_date.isoformat()}",
            is_reminder=True,
        )
        created += len(rows)
    return created


def safe_notify_project_milestone(db: Session, *, project_id: int, milestone: str, event_id: int | None = None) -> None:
    """Notification failure must never cancel a legitimate project workflow."""
    try:
        with db.begin_nested():
            notify_project_milestone(db, project_id=project_id, milestone=milestone, event_id=event_id)
    except Exception:
        logger.exception("BD Employee notification failed: project=%s milestone=%s", project_id, milestone)
    if milestone in {"project_delivered", "client_feedback_updated", "project_closed"}:
        # Existing workflow call sites already fire these authoritative milestones.
        # Dispatch manager receipts separately so an employee-notification error
        # cannot prevent delivery of the manager notification (or vice versa).
        from app.modules.bd_employee.manager_notification_service import safe_notify_manager_project_event
        safe_notify_manager_project_event(db, project_id=project_id, milestone=milestone, event_id=event_id)


def safe_notify_completed_stage(db: Session, *, project_id: int, stage: str) -> None:
    """Use a savepoint so notification errors cannot break QC / QA transitions."""
    try:
        with db.begin_nested():
            notify_completed_stage(db, project_id=project_id, stage=stage)
    except Exception:
        logger.exception("BD Employee stage notification failed: project=%s stage=%s", project_id, stage)
