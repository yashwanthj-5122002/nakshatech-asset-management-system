from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.notifications.service import create_global_notification

_WORKFLOW_LABELS = {
    "it_work": "IT Work",
    "replacement": "Asset Replacement",
    "purchase_request": "Purchase Request",
}

_WORKFLOW_PATHS = {
    "it_work": "/work",
    "replacement": "/replacements",
    "purchase_request": "/it/purchase-requests",
}

_DECISION_LABELS = {
    "approved": "approved",
    "rejected": "rejected",
    "returned": "returned by Management",
    "sent_back": "sent back by Management",
}


def _event_token(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    text = str(value or "").strip()
    return text or "event"


def _target_url(workflow: str, reporting_month: str | None) -> str:
    base = _WORKFLOW_PATHS[workflow]
    month = str(reporting_month or "").strip()
    return f"{base}?month={month}" if month else base


def notify_management_approval_required(
    db: Session,
    *,
    workflow: str,
    record_id: int,
    record_code: str,
    reporting_month: str | None,
    submitted_by_name: str | None,
    event_token: datetime | str | None,
    resubmitted: bool = False,
) -> None:
    """Notify active Management users that an approval item needs review.

    Notification rows are added to the caller's current transaction and are not
    committed here, keeping the approval state and its notification atomic.
    """

    label = _WORKFLOW_LABELS[workflow]
    action = "resubmitted" if resubmitted else "submitted"
    actor = str(submitted_by_name or "IT Department").strip() or "IT Department"
    title = f"{label} {'resubmitted' if resubmitted else 'awaiting approval'}"
    message = (
        f"{record_code} was {'resubmitted' if resubmitted else 'submitted'} by {actor} "
        "and requires Management review."
    )
    create_global_notification(
        db,
        event_type=f"approval.{workflow}.{action}",
        category="approval",
        title=title,
        message=message,
        target_url=_target_url(workflow, reporting_month),
        recipient_roles=["management"],
        dedupe_key=f"approval:{workflow}:{record_id}:{action}:{_event_token(event_token)}",
    )


def notify_approval_decision(
    db: Session,
    *,
    workflow: str,
    record_id: int,
    record_code: str,
    reporting_month: str | None,
    outcome: str,
    decided_by_name: str | None,
    remarks: str | None,
    event_token: datetime | str | None,
    recipient_user_id: int | None,
    fallback_role: str = "it",
) -> None:
    """Notify the responsible IT role and, when available, the original requester.

    Including the concrete requester preserves ownership while role fan-out keeps
    the IT team aware of Management decisions. The notification service de-dupes
    overlapping recipients automatically.
    """

    label = _WORKFLOW_LABELS[workflow]
    outcome_label = _DECISION_LABELS[outcome]
    actor = str(decided_by_name or "Management").strip() or "Management"
    message = f"{record_code} was {outcome_label} by {actor}."
    clean_remarks = str(remarks or "").strip()
    if clean_remarks:
        message = f"{message} Management remarks: {clean_remarks}"

    recipient_user_ids = [recipient_user_id] if recipient_user_id is not None else None

    create_global_notification(
        db,
        event_type=f"approval.{workflow}.{outcome}",
        category="approval",
        title=f"{label} {outcome_label}",
        message=message,
        target_url=_target_url(workflow, reporting_month),
        recipient_user_ids=recipient_user_ids,
        recipient_roles=[fallback_role],
        dedupe_key=f"approval:{workflow}:{record_id}:{outcome}:{_event_token(event_token)}",
    )
