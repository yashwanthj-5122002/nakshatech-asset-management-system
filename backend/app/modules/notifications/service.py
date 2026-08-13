from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.roles import VALID_ROLES
from app.models.entities import User, utc_now
from app.modules.notifications.models import GlobalNotification

VALID_NOTIFICATION_CATEGORIES = {"approval", "ticket", "system"}


def _clean_text(value: str, *, field: str, max_length: int) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        raise ValueError(f"{field} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field} must be {max_length} characters or fewer")
    return cleaned


def normalize_target_url(value: str | None) -> str | None:
    """Allow only internal application deep links.

    Frontend consumers may navigate directly to this value, so external URLs,
    protocol-relative URLs and control characters are intentionally rejected.
    """

    if value is None:
        return None
    target = str(value).strip()
    if not target:
        return None
    if len(target) > 512:
        raise ValueError("target_url must be 512 characters or fewer")
    if not target.startswith("/") or target.startswith("//"):
        raise ValueError("target_url must be an internal application path")
    if "\r" in target or "\n" in target or "\x00" in target:
        raise ValueError("target_url contains invalid characters")
    return target


def _normalize_roles(recipient_roles: Iterable[str] | None) -> set[str]:
    roles = {str(role).strip().lower() for role in (recipient_roles or []) if str(role).strip()}
    invalid = roles.difference(VALID_ROLES)
    if invalid:
        raise ValueError(f"Unknown notification recipient role(s): {', '.join(sorted(invalid))}")
    return roles


def resolve_recipient_users(
    db: Session,
    *,
    recipient_user_ids: Iterable[int] | None = None,
    recipient_roles: Iterable[str] | None = None,
) -> list[User]:
    """Resolve explicit users and role recipients into active concrete users."""

    ids = {int(user_id) for user_id in (recipient_user_ids or [])}
    roles = _normalize_roles(recipient_roles)
    if not ids and not roles:
        raise ValueError("At least one recipient user or role is required")

    conditions = []
    if ids:
        conditions.append(User.id.in_(ids))
    if roles:
        conditions.append(User.role.in_(roles))

    from sqlalchemy import or_

    users = list(
        db.scalars(
            select(User)
            .where(
                or_(*conditions),
                User.is_active.is_(True),
                User.account_status == "active",
            )
            .order_by(User.id.asc())
        ).all()
    )
    return users


def create_global_notification(
    db: Session,
    *,
    event_type: str,
    title: str,
    message: str,
    category: str = "system",
    target_url: str | None = None,
    recipient_user_ids: Iterable[int] | None = None,
    recipient_roles: Iterable[str] | None = None,
    dedupe_key: str | None = None,
) -> list[GlobalNotification]:
    """Create persistent per-user notifications without committing the caller's transaction.

    A role target is expanded to active users at creation time. When ``dedupe_key``
    is supplied, each recipient can receive that logical event at most once.
    The database unique constraint is the final concurrency guard.
    """

    clean_event_type = _clean_text(event_type, field="event_type", max_length=80)
    clean_title = _clean_text(title, field="title", max_length=255)
    clean_message = _clean_text(message, field="message", max_length=10_000)
    clean_category = str(category or "system").strip().lower()
    if clean_category not in VALID_NOTIFICATION_CATEGORIES:
        raise ValueError(f"Unsupported notification category: {clean_category}")
    clean_target_url = normalize_target_url(target_url)
    clean_dedupe_key = str(dedupe_key or "").strip() or None
    if clean_dedupe_key and len(clean_dedupe_key) > 255:
        raise ValueError("dedupe_key must be 255 characters or fewer")

    requested_roles = _normalize_roles(recipient_roles)
    users = resolve_recipient_users(
        db,
        recipient_user_ids=recipient_user_ids,
        recipient_roles=requested_roles,
    )

    created: list[GlobalNotification] = []
    for user in users:
        if clean_dedupe_key:
            existing = db.scalar(
                select(GlobalNotification.id).where(
                    GlobalNotification.recipient_user_id == user.id,
                    GlobalNotification.dedupe_key == clean_dedupe_key,
                )
            )
            if existing is not None:
                continue

        matched_role = user.role if user.role in requested_roles else None
        notification = GlobalNotification(
            recipient_user_id=user.id,
            recipient_role=matched_role,
            event_type=clean_event_type,
            category=clean_category,
            title=clean_title,
            message=clean_message,
            target_url=clean_target_url,
            dedupe_key=clean_dedupe_key,
        )
        try:
            with db.begin_nested():
                db.add(notification)
                db.flush()
        except IntegrityError:
            # A concurrent request may have inserted the same logical event.
            # The savepoint rollback keeps the caller's outer transaction intact.
            continue
        created.append(notification)

    return created


def _exclude_event_prefixes(query, prefixes: Iterable[str] | None):
    for prefix in prefixes or ():
        clean_prefix = str(prefix or "").strip()
        if clean_prefix:
            query = query.where(~GlobalNotification.event_type.startswith(clean_prefix))
    return query


def list_notifications_for_user(
    db: Session,
    *,
    user_id: int,
    unread_only: bool = False,
    category: str | None = None,
    limit: int = 100,
    offset: int = 0,
    excluded_event_prefixes: Iterable[str] | None = None,
) -> list[GlobalNotification]:
    query = select(GlobalNotification).where(GlobalNotification.recipient_user_id == user_id)
    query = _exclude_event_prefixes(query, excluded_event_prefixes)
    if unread_only:
        query = query.where(GlobalNotification.is_read.is_(False))
    if category:
        normalized = category.strip().lower()
        if normalized not in VALID_NOTIFICATION_CATEGORIES:
            raise HTTPException(status_code=422, detail="Invalid notification category")
        query = query.where(GlobalNotification.category == normalized)
    query = query.order_by(GlobalNotification.created_at.desc(), GlobalNotification.id.desc())
    return list(db.scalars(query.offset(offset).limit(limit)).all())


def get_notification_for_user(db: Session, *, user_id: int, notification_id: int) -> GlobalNotification:
    notification = db.scalar(
        select(GlobalNotification).where(
            GlobalNotification.id == notification_id,
            GlobalNotification.recipient_user_id == user_id,
        )
    )
    if notification is None:
        # Return 404 instead of 403 so notification IDs cannot be enumerated across users.
        raise HTTPException(status_code=404, detail="Notification not found")
    return notification


def unread_count_for_user(
    db: Session,
    *,
    user_id: int,
    excluded_event_prefixes: Iterable[str] | None = None,
) -> int:
    query = select(func.count(GlobalNotification.id)).where(
        GlobalNotification.recipient_user_id == user_id,
        GlobalNotification.is_read.is_(False),
    )
    query = _exclude_event_prefixes(query, excluded_event_prefixes)
    return int(db.scalar(query) or 0)


def mark_notification_read(
    db: Session,
    *,
    user_id: int,
    notification_id: int,
    now: datetime | None = None,
) -> GlobalNotification:
    notification = get_notification_for_user(db, user_id=user_id, notification_id=notification_id)
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = now or utc_now()
        db.flush()
    return notification


def mark_all_notifications_read(
    db: Session,
    *,
    user_id: int,
    category: str | None = None,
    now: datetime | None = None,
) -> int:
    conditions = [
        GlobalNotification.recipient_user_id == user_id,
        GlobalNotification.is_read.is_(False),
    ]
    if category:
        normalized = category.strip().lower()
        if normalized not in VALID_NOTIFICATION_CATEGORIES:
            raise HTTPException(status_code=422, detail="Invalid notification category")
        conditions.append(GlobalNotification.category == normalized)

    result = db.execute(
        update(GlobalNotification)
        .where(*conditions)
        .values(is_read=True, read_at=now or utc_now())
    )
    db.flush()
    return int(result.rowcount or 0)
