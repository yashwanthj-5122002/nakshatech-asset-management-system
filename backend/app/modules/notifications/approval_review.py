"""Read-only Finance/Management notification eligibility.

This is a DISPLAY policy, never an authorization check for approval actions.
The existing workflow endpoints remain authoritative for making decisions.
Only explicitly reviewed event types are admitted as pending approvals.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.management_clients.models import ManagementAdditionalProjectRequest, ManagementClientIntake
from app.modules.management_projects.models import ManagementProjectLink
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.lifecycle_models import (
    ProjectFeedbackRequest, ProjectInvoice, ProjectInvoiceBadDebt, ProjectInvoiceBadDebtApproval,
)
from app.modules.operations.models import ProjectWorkflow

FINANCE_APPROVAL_EVENTS = frozenset({
    "workflow.project.submitted_finance",
    "management.additional_project.requested",
})
MANAGEMENT_APPROVAL_EVENTS = frozenset({
    "lifecycle.management_approval_requested",
    "lifecycle.bad_debt.proposed",
    "lifecycle.no_feedback_authorization_required",
})


def approval_events_for_role(role: str) -> frozenset[str]:
    if role == "finance":
        return FINANCE_APPROVAL_EVENTS
    if role == "management":
        return MANAGEMENT_APPROVAL_EVENTS
    return frozenset()


def _positive_int(value: object) -> int | None:
    try:
        text = str(value or "").strip()
        if not text.isdecimal():
            return None
        result = int(text)
        return result if result > 0 else None
    except (TypeError, ValueError):
        return None


def _meta(row: GlobalNotification) -> dict:
    try:
        decoded = json.loads(row.metadata_json or "{}")
        return decoded if isinstance(decoded, dict) else {}
    except (TypeError, ValueError):
        return {}


def _query_id(row: GlobalNotification, name: str) -> int | None:
    values = parse_qs(urlsplit(row.target_url or "").query).get(name, [])
    return _positive_int(values[0]) if len(values) == 1 else None


def _dedupe_id(row: GlobalNotification, expression: str) -> int | None:
    found = re.fullmatch(expression, row.dedupe_key or "")
    return _positive_int(found.group(1)) if found else None


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _current_finance_submission(row: GlobalNotification, workflow: ProjectWorkflow) -> bool:
    if workflow.status != "pending_finance_approval":
        return False
    # Do not revive an approval notification from an earlier returned cycle.
    return not (workflow.submitted_at and row.created_at and
                _utc(row.created_at) < _utc(workflow.submitted_at))


def is_pending_approval_for_user(
    db: Session,
    row: GlobalNotification,
    viewer: User,
    role: str,
    cache: dict | None = None,
) -> bool:
    """True only if this recipient can still make the actual business decision.

    Uses current workflow records, not the often-incorrect historical notification
    category/requires_action/resolved_at; older legacy rows are never rewritten.
    """
    if row.recipient_user_id != viewer.id or row.event_type not in approval_events_for_role(role):
        return False
    # Cache repeated checks for the same row/recipient during one API request.
    cache_key = (row.id, viewer.id, role)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    result = _pending_uncached(db, row, viewer, role)
    if cache is not None:
        cache[cache_key] = result
    return result


def _pending_uncached(db: Session, row: GlobalNotification, viewer: User, role: str) -> bool:
    event = row.event_type
    if role == "finance" and event == "workflow.project.submitted_finance":
        project_id = _positive_int(_meta(row).get("project_id")) or _query_id(row, "project")
        workflow = (db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id).limit(1))
                    if project_id else None)
        return workflow is not None and _current_finance_submission(row, workflow)

    if role == "finance" and event == "management.additional_project.requested":
        request_id = _positive_int(_meta(row).get("request_id")) or _dedupe_id(
            row, r"mgmt_add_project_request_(\d+)")
        request = db.get(ManagementAdditionalProjectRequest, request_id) if request_id else None
        return bool(request and request.status == "PENDING" and request.created_project_id is None)

    if role == "management" and event == "lifecycle.management_approval_requested":
        project_id = _dedupe_id(row, r"lifecycle:management-approval:(\d+)")
        if not project_id:
            return False
        link = db.get(ManagementProjectLink, project_id)
        intake = db.get(ManagementClientIntake, link.management_client_id) if link else None
        workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id).limit(1))
        if not (intake and intake.created_by_id == viewer.id and workflow and
                workflow.operational_completed_at is not None):
            return False
        from app.modules.operations.lifecycle_service import (
            APPROVAL_PENDING, management_billing_status, management_source_approval_event,
        )
        if management_source_approval_event(db, project_id) is not None:
            return False
        if management_billing_status(db, workflow) != APPROVAL_PENDING:
            return False
        if db.scalar(select(ProjectInvoice.id).where(ProjectInvoice.project_id == project_id).limit(1)):
            return False
        # Match the same fully-delivered readiness rule used by the actual POST
        # /management/client-register/projects/{id}/approve endpoint.
        from app.modules.management_clients.router import (
            _approval_flags, _project_packages, _tracking_rollup, file_aggregates_for_packages,
        )
        packages = _project_packages(db, [project_id]).get(project_id, [])
        aggregates = file_aggregates_for_packages(db, [package.id for package in packages])
        summary = _tracking_rollup(packages, aggregates)
        return bool(_approval_flags(db, link=link, workflow_status=APPROVAL_PENDING,
                                    summary=summary, viewer_user_id=viewer.id)["can_approve"])

    if role == "management" and event == "lifecycle.bad_debt.proposed":
        invoice_id = _dedupe_id(row, r"lifecycle:bad-debt:proposal:(\d+):\d+")
        if not invoice_id:
            return False
        proposal = db.scalar(select(ProjectInvoiceBadDebt).where(
            ProjectInvoiceBadDebt.invoice_id == invoice_id))
        if not proposal or proposal.status != "PROPOSED":
            return False
        # Never resurrect an old notification from an earlier proposal cycle.
        if not (row.dedupe_key or "").endswith(f":{int(proposal.proposed_at.timestamp())}"):
            return False
        from app.modules.operations.lifecycle_service import BAD_DEBT_APPROVER_EMAILS
        email = (viewer.email or "").strip().lower()
        approver = next((key for key, address in BAD_DEBT_APPROVER_EMAILS.items()
                         if email == address), None)
        if approver is None:
            return False
        decision = db.scalar(select(ProjectInvoiceBadDebtApproval.id).where(
            ProjectInvoiceBadDebtApproval.bad_debt_id == proposal.id,
            ProjectInvoiceBadDebtApproval.decided_at >= proposal.proposed_at,
            ProjectInvoiceBadDebtApproval.approver_key == approver,
        ).limit(1))
        return decision is None

    if role == "management" and event == "lifecycle.no_feedback_authorization_required":
        request_id = _dedupe_id(row, r"lifecycle:no-feedback-recommendation:(\d+)")
        request = db.get(ProjectFeedbackRequest, request_id) if request_id else None
        return bool(request and request.status == "closure_recommended")

    return False
