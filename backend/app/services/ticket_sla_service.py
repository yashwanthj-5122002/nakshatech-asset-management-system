from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.models.entities import utc_now
from app.modules.employee_portal.models import AuditEvent, SupportTicket
from app.modules.notifications.service import create_global_notification

# Existing ticket priority logic defines the initial-response targets. Batch 2F
# adds warning windows without changing those approved target values.
SLA_TARGET_MINUTES = {"low": 1440, "medium": 480, "high": 120, "critical": 30}
SLA_WARNING_MINUTES = {
    "critical": 10,
    "high": 30,
    "medium": 120,
    "low": 240,
}
SLA_TERMINAL_STATUSES = {"resolved", "closed"}
SLA_RESPONSE_AUDIT_EVENTS = {"TICKET_MESSAGE_ADDED", "TICKET_UPDATED"}
SLA_REFRESH_INTERVAL_SECONDS = 30.0

_scan_lock = threading.Lock()
_last_scan_monotonic = 0.0


def _response_time_map(db: Session, ticket_ids: list[int]) -> dict[int, datetime]:
    """Return the first non-requester handling action for each ticket.

    A department reply or department-side ticket update counts as the initial
    response. Requester replies/reopens are excluded by comparing the audit
    actor against the original requester.
    """

    clean_ids = sorted({int(ticket_id) for ticket_id in ticket_ids if int(ticket_id) > 0})
    if not clean_ids:
        return {}

    rows = db.execute(
        select(
            SupportTicket.id,
            func.min(AuditEvent.created_at).label("first_response_at"),
        )
        .join(
            AuditEvent,
            cast(SupportTicket.id, String) == AuditEvent.target_id,
        )
        .where(
            SupportTicket.id.in_(clean_ids),
            AuditEvent.module == "tickets",
            AuditEvent.target_type == "ticket",
            AuditEvent.event_type.in_(SLA_RESPONSE_AUDIT_EVENTS),
            AuditEvent.user_id.is_not(None),
            AuditEvent.user_id != SupportTicket.requester_id,
        )
        .group_by(SupportTicket.id)
    ).all()
    return {
        int(ticket_id): first_response_at
        for ticket_id, first_response_at in rows
        if first_response_at is not None
    }


def build_ticket_sla_snapshot(
    ticket: SupportTicket,
    *,
    first_response_at: datetime | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    target_minutes = int(ticket.sla_target_minutes or SLA_TARGET_MINUTES.get(ticket.priority, 0))
    if target_minutes <= 0 or ticket.created_at is None:
        return {
            "sla_target_minutes": None,
            "sla_status": "not_applicable",
            "sla_due_at": None,
            "sla_warning_at": None,
            "sla_first_response_at": first_response_at,
            "sla_remaining_seconds": None,
            "sla_warning": False,
            "sla_breached": False,
            "sla_escalation_level": "none",
        }

    current = now or utc_now()
    due_at = ticket.created_at + timedelta(minutes=target_minutes)
    warning_minutes = int(SLA_WARNING_MINUTES.get(ticket.priority, max(1, target_minutes // 4)))
    warning_at = due_at - timedelta(minutes=warning_minutes)
    reference_at = first_response_at or current
    remaining_seconds = int((due_at - reference_at).total_seconds())
    breached = remaining_seconds < 0

    if first_response_at is not None:
        status = "breached" if breached else "met"
        warning = False
    elif breached or remaining_seconds == 0:
        status = "breached"
        warning = False
        breached = True
    else:
        warning = current >= warning_at
        status = "warning" if warning else "on_track"

    if breached:
        escalation_level = "critical_breach" if ticket.priority == "critical" else "breach"
    elif warning:
        escalation_level = "warning"
    else:
        escalation_level = "none"

    return {
        "sla_target_minutes": target_minutes,
        "sla_status": status,
        "sla_due_at": due_at,
        "sla_warning_at": warning_at,
        "sla_first_response_at": first_response_at,
        "sla_remaining_seconds": remaining_seconds,
        "sla_warning": warning,
        "sla_breached": breached,
        "sla_escalation_level": escalation_level,
    }


def build_ticket_sla_snapshot_map(
    db: Session,
    tickets: list[SupportTicket],
    *,
    now: datetime | None = None,
) -> dict[int, dict[str, Any]]:
    response_times = _response_time_map(db, [ticket.id for ticket in tickets])
    current = now or utc_now()
    return {
        ticket.id: build_ticket_sla_snapshot(
            ticket,
            first_response_at=response_times.get(ticket.id),
            now=current,
        )
        for ticket in tickets
    }


def ensure_critical_sla_breach_notifications(
    db: Session,
    *,
    now: datetime | None = None,
    force: bool = False,
) -> int:
    """Create one deduplicated bell escalation for each actionable critical breach.

    The function intentionally does not commit. The caller owns the transaction.
    A small process-local throttle protects the 30-second bell polling path from
    repeatedly scanning the same tickets. Database deduplication remains the final
    guard across workers/processes.
    """

    global _last_scan_monotonic
    if not force:
        current_monotonic = time.monotonic()
        with _scan_lock:
            if current_monotonic - _last_scan_monotonic < SLA_REFRESH_INTERVAL_SECONDS:
                return 0
            _last_scan_monotonic = current_monotonic

    current = now or utc_now()
    candidates = list(
        db.scalars(
            select(SupportTicket)
            .where(
                SupportTicket.priority == "critical",
                SupportTicket.status.not_in(SLA_TERMINAL_STATUSES),
            )
            .order_by(SupportTicket.created_at.asc(), SupportTicket.id.asc())
            .limit(500)
        ).all()
    )
    if not candidates:
        return 0

    response_times = _response_time_map(db, [ticket.id for ticket in candidates])
    created_count = 0
    for ticket in candidates:
        # A response stops the actionable breach escalation. A late response still
        # remains visibly marked as breached in the queue/detail SLA state.
        if response_times.get(ticket.id) is not None:
            continue
        snapshot = build_ticket_sla_snapshot(ticket, first_response_at=None, now=current)
        if not snapshot["sla_breached"]:
            continue

        overdue_seconds = max(0, -int(snapshot["sla_remaining_seconds"] or 0))
        overdue_minutes = max(1, overdue_seconds // 60)
        target_minutes = int(ticket.sla_target_minutes or SLA_TARGET_MINUTES["critical"])
        recipients = [ticket.department, "management"]
        created = create_global_notification(
            db,
            event_type="ticket.sla.critical_breach",
            category="ticket",
            title=f"Critical SLA breached · {ticket.ticket_code}",
            message=(
                f"Initial response target of {target_minutes} minutes has been breached "
                f"by {overdue_minutes} minute{'s' if overdue_minutes != 1 else ''}. Immediate attention required."
            ),
            target_url=f"/tickets/{ticket.id}",
            recipient_roles=recipients,
            dedupe_key=f"ticket:{ticket.id}:sla:critical-breach:v1",
        )
        created_count += len(created)

    return created_count
