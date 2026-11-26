"""Inform the BD Manager of milestones on BD Employee-origin projects.

Uses existing per-user global notifications and caller transactions. This module
never changes a project's stage, invoice, approvals, ownership, or finance data.
"""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.bd_employee.handoff_models import BdEmployeeProjectLink
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.notifications.service import create_global_notification

logger = logging.getLogger(__name__)

# Do not notify managers about every production/QC/QA step; only requested
# milestones. These are informational bell notifications, NOT approval popups.
MANAGER_EVENTS = {
    "project_created": (
        "BD Employee Project Created",
        "{employee} created Project {code}.",
        "/bd/projects?project={id}",
    ),
    "project_delivered": (
        "BD Employee Project Delivered",
        "Project {code} linked to {employee} has completed operational delivery. Client feedback is the next step.",
        "/bd/feedback?project={id}",
    ),
    "client_feedback_updated": (
        "BD Employee Client Feedback Received",
        "Client feedback was recorded for {employee}'s Project {code}. Review the feedback and billing status.",
        "/bd/feedback?project={id}",
    ),
    "project_closed": (
        "BD Employee Project Financially Closed",
        "Finance has finalized closure for {employee}'s Project {code}.",
        "/bd/projects?project={id}",
    ),
}


def _manager_recipients(db: Session, project: FinanceProject) -> tuple[list[int], User | None]:
    """Resolve recipients from persisted BD origin; never from request data.

    An explicit employee handoff has a specific manager. Directly created
    BD Employee projects have no manager link: active BD Managers have
    team-level visibility and receive that team's project milestones.
    """
    if project.project_source_team != "bd_team":
        return [], None
    client = db.get(FinanceClient, project.client_id)
    if client is None or client.source_team != "bd_team":
        return [], None

    link = db.get(BdEmployeeProjectLink, project.id)
    creator = db.get(User, project.created_by_id) if project.created_by_id else None
    if link is not None:
        employee = db.get(User, link.employee_user_id)
        if employee is None or employee.role != "bd_employee":
            return [], None
        manager = db.get(User, link.manager_user_id)
        if (manager is None or manager.role != "bd" or not manager.is_active
                or manager.account_status != "active"):
            return [], None
        return [manager.id], employee

    if creator is None or creator.role != "bd_employee":
        return [], None
    manager_ids = list(db.scalars(select(User.id).where(
        User.role == "bd",
        User.is_active.is_(True),
        User.account_status == "active",
    )).all())
    return sorted(set(manager_ids)), creator


def notify_manager_project_event(
    db: Session, *, project_id: int, milestone: str, event_id: int | None = None,
) -> None:
    """Insert once per manager/event. Caller owns the surrounding transaction."""
    if milestone not in MANAGER_EVENTS:
        raise ValueError(f"Unsupported BD Manager milestone: {milestone}")
    project = db.get(FinanceProject, project_id)
    if project is None:
        return
    recipients, employee = _manager_recipients(db, project)
    if not recipients or employee is None:
        return
    title, message, url = MANAGER_EVENTS[milestone]
    identifier = f":{event_id}" if event_id is not None else ""
    create_global_notification(
        db,
        event_type=f"bd_manager.employee_project.{milestone}",
        title=f"{title}: {project.project_code}",
        message=message.format(employee=employee.full_name, code=project.project_code),
        category="system",
        target_url=url.format(id=project.id),
        recipient_user_ids=recipients,
        dedupe_key=f"bd-manager-employee-project:{project.id}:{milestone}{identifier}",
        requires_action=False,
    )


def safe_notify_manager_project_event(
    db: Session, *, project_id: int, milestone: str, event_id: int | None = None,
) -> None:
    """Isolate notification failures from legitimate workflow transactions."""
    try:
        with db.begin_nested():
            notify_manager_project_event(db, project_id=project_id, milestone=milestone, event_id=event_id)
    except Exception:
        logger.exception(
            "BD Manager notification failed for project=%s milestone=%s event=%s",
            project_id, milestone, event_id,
        )
