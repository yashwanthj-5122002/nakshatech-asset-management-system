"""Advance Payment notifications and alerts (Finance V8 Phase 4).

SCOPE AND SAFETY BOUNDARY
-------------------------
Reuses the existing notification architecture only: every alert is materialised
through ``create_global_notification`` into the existing ``global_notifications``
table (per-user receipts with a unique ``(recipient_user_id, dedupe_key)`` guard).
No new notification framework, table, or background scheduler is introduced; the
refresh is an explicit API call (Finance Command Center load / operations tooling)
and is idempotent per project, per rule, per calendar day.

Notification rules (Phase 4 frozen contract)
--------------------------------------------
1. Advance Payment Due      -> today >= expected advance date AND status Requested/Pending
                               Recipient: Finance
2. Advance Payment Overdue  -> today > final advance date AND pending amount > 0
                               Recipient: Finance
3. Partial Advance Pending  -> received amount > 0 AND received amount < expected amount
                               Recipient: Finance
4. High Value Pending       -> pending advance > configurable threshold (default Rs.10,00,000)
                               Recipient: Management

Dedupe keys follow ``advance_<rule>_project_{project_id}_{YYYY-MM-DD}`` so a
second refresh on the same day creates nothing, exactly like the existing
``refresh-ticket-sla`` idempotency approach.

Nothing here touches Sales, Revenue, Outstanding, invoice value, or the Finance
Command Center KPI reconciliation: alerts read the isolated Client Advance
Payment snapshots and only ever write notification rows.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User
from app.modules.finance.advance_service import advance_alert_rows
from app.modules.notifications.service import create_global_notification

logger = logging.getLogger(__name__)

FINANCE_RECIPIENT_ROLES = ("finance",)
MANAGEMENT_RECIPIENT_ROLES = ("management",)

ALERT_DUE = "due"
ALERT_OVERDUE = "overdue"
ALERT_PARTIAL = "partial"
ALERT_HIGH_VALUE = "high_value"

ALERT_KINDS = (ALERT_DUE, ALERT_OVERDUE, ALERT_PARTIAL, ALERT_HIGH_VALUE)

# Derived statuses that mean the advance is already settled/terminal. Amount
# rules must never fire for these rows even when raw amounts still differ.
TERMINAL_STATUSES = {"not_required", "received", "adjusted", "closed"}

_EVENT_TYPES = {
    ALERT_DUE: "finance.advance_payment.due",
    ALERT_OVERDUE: "finance.advance_payment.overdue",
    ALERT_PARTIAL: "finance.advance_payment.partial_pending",
    ALERT_HIGH_VALUE: "finance.advance_payment.high_value_pending",
}

_TITLES = {
    ALERT_DUE: "Advance Payment Due",
    ALERT_OVERDUE: "Advance Payment Overdue",
    ALERT_PARTIAL: "Partial Advance Pending",
    ALERT_HIGH_VALUE: "High Value Pending Advance",
}

_DEDUPE_PREFIXES = {
    ALERT_DUE: "advance_due",
    ALERT_OVERDUE: "advance_overdue",
    ALERT_PARTIAL: "advance_partial",
    ALERT_HIGH_VALUE: "advance_high_value",
}

# Rules 1-3 chase the money with Finance; rule 4 escalates to Management only.
_RECIPIENT_ROLES = {
    ALERT_DUE: FINANCE_RECIPIENT_ROLES,
    ALERT_OVERDUE: FINANCE_RECIPIENT_ROLES,
    ALERT_PARTIAL: FINANCE_RECIPIENT_ROLES,
    ALERT_HIGH_VALUE: MANAGEMENT_RECIPIENT_ROLES,
}

_TARGET_URL = "/finance/command-center"
_CATEGORY = "system"


def _money(value: object | None) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _inr(value: object | None) -> str:
    """Format whole rupees with Indian digit grouping (for example 10,00,000)."""
    amount = int(_money(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    sign = "-" if amount < 0 else ""
    digits = str(abs(amount))
    if len(digits) > 3:
        last_three = digits[-3:]
        rest = digits[:-3]
        parts: list[str] = []
        while len(rest) > 2:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            parts.insert(0, rest)
        grouped = ",".join(parts) + "," + last_three
    else:
        grouped = digits
    return f"{sign}Rs.{grouped}"


def _due_label(value: str | None) -> str:
    if not value:
        return "not scheduled"
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%d-%m-%Y")



def evaluate_advance_alerts(
    rows: list[dict],
    *,
    as_of: date,
    threshold: Decimal,
) -> list[dict]:
    """Pure evaluation of the four Phase 4 rules against snapshot rows.

    Each matching rule produces one alert entry for the project. Terminal
    advance statuses (received/adjusted/closed/not required) never raise a
    money-pending alert.
    """
    today_iso = as_of.isoformat()
    alerts: list[dict] = []
    for row in rows:
        status = row.get("status")
        if status in TERMINAL_STATUSES:
            continue
        expected = _money(row.get("advance_amount"))
        received = _money(row.get("received_amount"))
        pending = _money(row.get("pending_amount"))
        expected_date = row.get("expected_date")
        final_date = row.get("final_date")
        kinds: list[str] = []

        if expected_date and today_iso >= expected_date and status in ("requested", "pending"):
            kinds.append(ALERT_DUE)
        if final_date and today_iso > final_date and pending > 0:
            kinds.append(ALERT_OVERDUE)
        if received > 0 and received < expected:
            kinds.append(ALERT_PARTIAL)
        if pending > threshold:
            kinds.append(ALERT_HIGH_VALUE)

        for kind in kinds:
            days_overdue = None
            if kind == ALERT_OVERDUE and final_date:
                days_overdue = (as_of - date.fromisoformat(final_date)).days
            alerts.append({
                "kind": kind,
                "project_id": row.get("project_id"),
                "project_name": row.get("project_name"),
                "client": row.get("client"),
                "status": status,
                "status_label": row.get("status_label"),
                "expected_amount": expected,
                "received_amount": received,
                "pending_amount": pending,
                "expected_date": expected_date,
                "final_date": final_date,
                "days_overdue": days_overdue,
            })
    return alerts


def high_value_threshold() -> Decimal:
    """Configurable escalation threshold; default Rs.10,00,000."""
    return _money(settings.advance_high_value_threshold_inr)


def _message_for(alert: dict, *, threshold: Decimal) -> str:
    project = alert.get("project_name") or f"Project #{alert.get('project_id')}"
    client = alert.get("client") or "Unassigned client"
    prefix = f"Project {project} - Client {client}."
    status_label = alert.get("status_label") or alert.get("status") or ""
    kind = alert["kind"]
    if kind == ALERT_DUE:
        return (
            f"{prefix} Expected advance {_inr(alert['expected_amount'])} due on "
            f"{_due_label(alert['expected_date'])}. Current status: {status_label}."
        )
    if kind == ALERT_OVERDUE:
        days = alert.get("days_overdue") or 0
        return (
            f"{prefix} Pending advance {_inr(alert['pending_amount'])} is overdue by "
            f"{days} day(s) (final advance date {_due_label(alert['final_date'])}). "
            f"Current status: {status_label}."
        )
    if kind == ALERT_PARTIAL:
        return (
            f"{prefix} Partial advance received {_inr(alert['received_amount'])} of "
            f"{_inr(alert['expected_amount'])} expected; {_inr(alert['pending_amount'])} "
            f"still pending. Current status: {status_label}."
        )
    return (
        f"{prefix} Pending advance {_inr(alert['pending_amount'])} exceeds the high-value "
        f"threshold of {_inr(threshold)}. Current status: {status_label}."
    )


def _dedupe_key_for(alert: dict, *, as_of: date) -> str:
    return f"{_DEDUPE_PREFIXES[alert['kind']]}_project_{alert['project_id']}_{as_of.isoformat()}"


def _create_safe(db: Session, **kwargs) -> list:
    try:
        return create_global_notification(db, **kwargs)
    except Exception:  # noqa: BLE001 - one bad alert must not abort the refresh
        logger.exception("Advance payment notification creation failed")
        return []


def refresh_advance_notifications(
    db: Session,
    *,
    user: User,
    effective_role: str,
    as_of: date | None = None,
) -> dict:
    """Calculate due/overdue/partial/high-value advances and materialise alerts.

    Access follows the Client Advance Payment permission matrix, enforced
    backend side by ``resolve_advance_access``: Finance/Admin/Software Team get
    every project, Management and BD are scoped by ``_load_context`` (BD only to
    own projects), Technical PMs only to assigned projects, and Production/QC/QA
    are denied with ``PermissionError`` before anything is evaluated. The HTTP
    response carries counts only, so a PM refresh never exposes amounts.
    """
    today = as_of or date.today()
    threshold = high_value_threshold()
    access, rows = advance_alert_rows(db, user=user, effective_role=effective_role, as_of=today)
    alerts = evaluate_advance_alerts(rows, as_of=today, threshold=threshold)

    matched = {kind: 0 for kind in ALERT_KINDS}
    created = 0
    for alert in alerts:
        matched[alert["kind"]] += 1
        created_rows = _create_safe(
            db,
            event_type=_EVENT_TYPES[alert["kind"]],
            title=_TITLES[alert["kind"]],
            message=_message_for(alert, threshold=threshold),
            category=_CATEGORY,
            target_url=_TARGET_URL,
            recipient_roles=list(_RECIPIENT_ROLES[alert["kind"]]),
            dedupe_key=_dedupe_key_for(alert, as_of=today),
            # Popup experience (additive): due/overdue alerts are time-based
            # conditions, so the centre popup may resurface the SAME persisted row on
            # the configured interval. is_reminder never creates a new row.
            severity="danger" if alert["kind"] == ALERT_OVERDUE else ("warning" if alert["kind"] == ALERT_DUE else "info"),
            requires_action=True,
            is_reminder=True,
            metadata={
                "project_id": alert.get("project_id"),
                "project_name": alert.get("project_code"),
                "client_name": alert.get("client_name"),
                "alert_kind": alert["kind"],
                "amount": alert.get("pending_amount"),
                "due_date": alert.get("due_date"),
                "days_overdue": alert.get("days_overdue"),
                "currency": alert.get("currency"),
            },
        )
        created += len(created_rows)

    return {
        "created": created,
        "matched": matched,
        "evaluated_projects": len(rows),
        "financial_amounts_visible": access.financial_amounts_visible,
        "high_value_threshold_inr": float(threshold),
        "as_of": today.isoformat(),
    }


