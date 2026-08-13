from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.modules.notifications.service import create_global_notification


def _event_token(value: datetime | str | None) -> str:
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    text = str(value or "").strip()
    return text or "event"


def _ticket_path(ticket_id: int) -> str:
    return f"/tickets/{ticket_id}"


def notify_ticket_created(
    db: Session,
    *,
    ticket_id: int,
    ticket_code: str,
    department: str,
    priority: str,
    title: str,
    requester_name: str | None,
    event_token: datetime | str | None,
) -> None:
    """Send one global bell notification to the responsible department.

    Critical tickets use a stronger title rather than generating a second duplicate
    notification. Rows remain in the caller's transaction and are not committed here.
    """

    clean_department = str(department or "").strip().lower()
    clean_priority = str(priority or "medium").strip().lower()
    requester = str(requester_name or "Employee").strip() or "Employee"
    if clean_priority == "critical":
        event_type = "ticket.created.critical"
        notification_title = f"Critical support ticket {ticket_code}"
        message = f"{requester} raised a critical ticket: {title}"
    else:
        event_type = "ticket.created"
        notification_title = f"New support ticket {ticket_code}"
        message = f"{requester} raised: {title}"

    create_global_notification(
        db,
        event_type=event_type,
        category="ticket",
        title=notification_title,
        message=message,
        target_url=_ticket_path(ticket_id),
        recipient_roles=[clean_department],
        dedupe_key=f"ticket:{ticket_id}:created:{_event_token(event_token)}",
    )


def notify_ticket_requester_reply(
    db: Session,
    *,
    ticket_id: int,
    ticket_code: str,
    department: str,
    message_id: int,
    message_preview: str,
) -> None:
    """Notify the handling department when the employee/requester replies."""

    create_global_notification(
        db,
        event_type="ticket.requester_reply",
        category="ticket",
        title=f"Employee replied to {ticket_code}",
        message=str(message_preview or "").strip()[:500] or "The employee added a reply.",
        target_url=_ticket_path(ticket_id),
        recipient_roles=[str(department or "").strip().lower()],
        dedupe_key=f"ticket:{ticket_id}:message:{message_id}:requester_reply",
    )


def notify_ticket_department_reply(
    db: Session,
    *,
    ticket_id: int,
    ticket_code: str,
    requester_user_id: int,
    message_id: int,
    message_preview: str,
) -> None:
    """Notify the employee/requester when the handling department replies."""

    create_global_notification(
        db,
        event_type="ticket.department_reply",
        category="ticket",
        title=f"New reply on {ticket_code}",
        message=str(message_preview or "").strip()[:500] or "Your support ticket has a new reply.",
        target_url=_ticket_path(ticket_id),
        recipient_user_ids=[requester_user_id],
        dedupe_key=f"ticket:{ticket_id}:message:{message_id}:department_reply",
    )


def notify_ticket_reopened(
    db: Session,
    *,
    ticket_id: int,
    ticket_code: str,
    department: str,
    event_token: datetime | str | None,
) -> None:
    """Notify the handling department when a resolved ticket is reopened."""

    create_global_notification(
        db,
        event_type="ticket.reopened",
        category="ticket",
        title=f"Ticket {ticket_code} reopened",
        message="The employee reopened this ticket and it requires attention.",
        target_url=_ticket_path(ticket_id),
        recipient_roles=[str(department or "").strip().lower()],
        dedupe_key=f"ticket:{ticket_id}:reopened:{_event_token(event_token)}",
    )


def notify_ticket_status_to_requester(
    db: Session,
    *,
    ticket_id: int,
    ticket_code: str,
    requester_user_id: int,
    status: str,
    event_token: datetime | str | None,
    resolution: str | None = None,
) -> None:
    """Notify the requester about a department-side ticket status change."""

    normalized_status = str(status or "").strip().lower()
    status_label = normalized_status.replace("_", " ").title() or "Updated"
    if normalized_status in {"resolved", "closed"}:
        title = f"Ticket {ticket_code} {normalized_status}"
        message = f"Your support ticket has been {normalized_status}."
        clean_resolution = str(resolution or "").strip()
        if clean_resolution:
            message = f"{message} Resolution: {clean_resolution}"
        event_type = f"ticket.{normalized_status}"
    else:
        title = f"Ticket {ticket_code} updated"
        message = f"Status: {status_label}"
        event_type = "ticket.updated"

    create_global_notification(
        db,
        event_type=event_type,
        category="ticket",
        title=title,
        message=message,
        target_url=_ticket_path(ticket_id),
        recipient_user_ids=[requester_user_id],
        dedupe_key=f"ticket:{ticket_id}:status:{normalized_status}:{_event_token(event_token)}",
    )
