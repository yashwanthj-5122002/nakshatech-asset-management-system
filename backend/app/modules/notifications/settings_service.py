"""Notification settings storage (overdue popup reminder interval).

Additive only: one key/value row per setting in ``notification_settings``. The
interval is a PRESENTATION preference. It never creates, resolves or mutates a
notification row on its own - the client resurfaces the existing overdue popup.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import utc_now
from app.modules.notifications.models import NotificationSetting

logger = logging.getLogger(__name__)

SETTING_OVERDUE_REMINDER_MINUTES = "overdue_popup_reminder_minutes"
DEFAULT_OVERDUE_REMINDER_MINUTES = 10
MIN_OVERDUE_REMINDER_MINUTES = 1
MAX_OVERDUE_REMINDER_MINUTES = 1440

# The curated options offered by the Management settings UI.
SUGGESTED_REMINDER_MINUTES = (5, 10, 15, 30, 60)


def _row(db: Session, key: str) -> NotificationSetting | None:
    return db.scalar(
        select(NotificationSetting).where(NotificationSetting.setting_key == key)
    )


def get_overdue_reminder_minutes(db: Session) -> int:
    """Current interval, falling back to the 10 minute default."""

    row = _row(db, SETTING_OVERDUE_REMINDER_MINUTES)
    if row is None:
        return DEFAULT_OVERDUE_REMINDER_MINUTES
    try:
        value = int(row.setting_value)
    except (TypeError, ValueError):
        return DEFAULT_OVERDUE_REMINDER_MINUTES
    return max(MIN_OVERDUE_REMINDER_MINUTES, min(value, MAX_OVERDUE_REMINDER_MINUTES))


def set_overdue_reminder_minutes(db: Session, *, minutes: int, actor_id: int | None) -> dict:
    """Persist a new interval. Caller must have already passed the capability check."""

    try:
        value = int(minutes)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid reminder interval") from exc
    if value < MIN_OVERDUE_REMINDER_MINUTES or value > MAX_OVERDUE_REMINDER_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Reminder interval must be between {MIN_OVERDUE_REMINDER_MINUTES} and {MAX_OVERDUE_REMINDER_MINUTES} minutes",
        )

    previous = get_overdue_reminder_minutes(db)
    row = _row(db, SETTING_OVERDUE_REMINDER_MINUTES)
    if row is None:
        row = NotificationSetting(setting_key=SETTING_OVERDUE_REMINDER_MINUTES, setting_value=str(value))
        db.add(row)
    else:
        row.setting_value = str(value)
    row.updated_at = utc_now()
    row.updated_by_id = actor_id
    db.flush()
    logger.info(
        "notification reminder interval changed old=%s new=%s by=%s",
        previous,
        value,
        actor_id,
    )
    return {
        "overdue_popup_reminder_minutes": value,
        "previous_overdue_popup_reminder_minutes": previous,
        "suggested_minutes": list(SUGGESTED_REMINDER_MINUTES),
        "default_minutes": DEFAULT_OVERDUE_REMINDER_MINUTES,
        "updated_at": row.updated_at,
    }


def notification_settings_payload(db: Session) -> dict:
    minutes = get_overdue_reminder_minutes(db)
    return {
        "overdue_popup_reminder_minutes": minutes,
        "suggested_minutes": list(SUGGESTED_REMINDER_MINUTES),
        "default_minutes": DEFAULT_OVERDUE_REMINDER_MINUTES,
    }