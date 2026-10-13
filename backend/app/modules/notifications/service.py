from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.roles import VALID_ROLES
from app.models.entities import User, utc_now
from app.modules.notifications.models import GlobalNotification

logger = logging.getLogger(__name__)

VALID_NOTIFICATION_CATEGORIES = {"approval", "ticket", "system"}

# These exact events belonged exclusively to the rejected V7 Sample Request
# workflow. Keep the list narrow so no current workflow notification is
# suppressed by a prefix or a broad category rule.
OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES = frozenset({
    "technical.sample.requested",
    "bd.sample.submitted",
    "technical.sample.revision_requested",
    "finance.bd_opportunity.client_approved",
})
OBSOLETE_SAMPLE_NOTIFICATION_RESOLUTION = "Obsolete Sample Request workflow retired"


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
    # --- additive, optional popup metadata (existing call sites are unaffected) ---
    severity: str | None = None,
    requires_action: bool | None = None,
    metadata: dict | None = None,
    is_reminder: bool | None = None,
) -> list[GlobalNotification]:
    """Create persistent per-user notifications without committing the caller's transaction.

    A role target is expanded to active users at creation time. When ``dedupe_key``
    is supplied, each recipient can receive that logical event at most once.
    The database unique constraint is the final concurrency guard.
    """

    clean_event_type = _clean_text(event_type, field="event_type", max_length=80)
    if clean_event_type in OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES:
        logger.info("obsolete Sample Request notification suppressed event_type=%s", clean_event_type)
        return []
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
    if metadata is not None:
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a mapping")
        cleaned_metadata = json.dumps(metadata, default=str)[:8000]
    else:
        cleaned_metadata = None

    users = resolve_recipient_users(
        db,
        recipient_user_ids=recipient_user_ids,
        recipient_roles=requested_roles,
    )
    logger.info(
        "notification created event_type=%s recipients=%s",
        clean_event_type,
        [user.id for user in users],
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
                logger.info(
                    "notification dedupe skipped event_type=%s recipient=%s key=%s",
                    clean_event_type,
                    user.id,
                    clean_dedupe_key,
                )
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
            severity=(str(severity).strip().lower() or "info") if severity else "info",
            requires_action=bool(requires_action),
            metadata_json=cleaned_metadata,
            is_reminder=bool(is_reminder),
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


def retire_obsolete_sample_notifications(db: Session) -> int:
    """Resolve only persisted notifications from the retired Sample Request flow.

    Rows remain available as notification history. The update is idempotent and
    deliberately uses an exact event allow-list so unrelated current events are
    never changed.
    """

    rows = list(db.scalars(select(GlobalNotification).where(
        GlobalNotification.event_type.in_(OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES)
    )).all())
    changed = 0
    stamp = utc_now()
    for row in rows:
        if (
            row.is_read
            and row.read_at is not None
            and not row.requires_action
            and row.resolved_at is not None
            and row.resolution_note == OBSOLETE_SAMPLE_NOTIFICATION_RESOLUTION
            and row.target_url is None
        ):
            continue
        row.is_read = True
        row.read_at = row.read_at or stamp
        row.requires_action = False
        row.resolved_at = row.resolved_at or stamp
        row.resolution_note = OBSOLETE_SAMPLE_NOTIFICATION_RESOLUTION
        row.target_url = None
        changed += 1
    if changed:
        logger.info("retired obsolete Sample Request notifications count=%s", changed)
    return changed


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
# ---------------------------------------------------------------------------
# Notification popup experience (additive helpers)
# ---------------------------------------------------------------------------

# Roles allowed to see monetary values inside notification metadata. Everyone
# else receives the notification WITH the money fields stripped server-side, so
# hiding them in the UI is never the only protection.
MONEY_VISIBLE_ROLES = frozenset({"finance", "management", "admin", "software_team", "bd"})

_MONEY_METADATA_KEYS = (
    "amount",
    "amount_due",
    "pending_amount",
    "commercial_value",
    "project_value",
    "invoice_total",
)


def _decode_metadata(notification: GlobalNotification) -> dict:
    if not notification.metadata_json:
        return {}
    try:
        parsed = json.loads(notification.metadata_json)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def redact_notification_metadata(metadata: dict, *, effective_role: str) -> dict:
    """Strip monetary fields for roles that may not see financial amounts."""

    if (effective_role or "").strip().lower() in MONEY_VISIBLE_ROLES:
        return dict(metadata)
    return {
        key: value
        for key, value in metadata.items()
        if key not in _MONEY_METADATA_KEYS and not key.startswith("amount")
    }


def notification_payload(
    notification: GlobalNotification,
    *,
    effective_role: str,
) -> dict:
    """Serialize one notification for the bell and the center popup.

    READ and RESOLVED stay independent so the UI can show
    "read but still pending action" without conflating the two.
    """

    return {
        "id": notification.id,
        "recipient_role": notification.recipient_role,
        "event_type": notification.event_type,
        "category": notification.category,
        "title": notification.title,
        "message": notification.message,
        "target_url": notification.target_url,
        "is_read": bool(notification.is_read),
        "read_at": notification.read_at,
        "created_at": notification.created_at,
        "severity": notification.severity or "info",
        "requires_action": bool(notification.requires_action),
        "is_resolved": notification.resolved_at is not None,
        "resolved_at": notification.resolved_at,
        "is_reminder": bool(notification.is_reminder),
        "metadata": redact_notification_metadata(
            _decode_metadata(notification), effective_role=effective_role
        ),
    }


def list_popup_notifications(
    db: Session,
    *,
    user_id: int,
    effective_role: str,
    limit: int = 5,
    excluded_event_prefixes: Iterable[str] | None = None,
) -> list[dict]:
    """Unresolved notifications eligible for the center popup, oldest first.

    This is a READ of existing rows: it never inserts, updates or resolves
    anything, so opening/closing a popup can have no backend side effect.
    """

    query = select(GlobalNotification).where(
        GlobalNotification.recipient_user_id == user_id,
        GlobalNotification.resolved_at.is_(None),
    )
    query = _exclude_event_prefixes(query, excluded_event_prefixes)
    query = query.order_by(
        GlobalNotification.created_at.asc(), GlobalNotification.id.asc()
    ).limit(max(1, min(int(limit), 20)))
    rows = list(db.scalars(query).all())
    return [notification_payload(row, effective_role=effective_role) for row in rows]


def pending_count_for_user(
    db: Session,
    *,
    user_id: int,
    excluded_event_prefixes: Iterable[str] | None = None,
) -> int:
    """Count of notifications that still require a business decision."""

    query = select(func.count(GlobalNotification.id)).where(
        GlobalNotification.recipient_user_id == user_id,
        GlobalNotification.resolved_at.is_(None),
        GlobalNotification.requires_action.is_(True),
    )
    query = _exclude_event_prefixes(query, excluded_event_prefixes)
    return int(db.scalar(query) or 0)


def resolve_notifications(
    db: Session,
    *,
    recipient_user_ids: Iterable[int],
    event_type: str | None = None,
    event_type_prefix: str | None = None,
    dedupe_key_prefix: str | None = None,
    resolved_by_id: int | None = None,
    resolution_note: str | None = None,
    now: datetime | None = None,
) -> int:
    """Resolve pending notifications AFTER a real workflow action succeeded.

    Called from the existing approval services - never from the popup UI - so a
    notification can only become resolved when the underlying business action
    actually completed.
    """

    ids = {int(user_id) for user_id in recipient_user_ids if user_id}
    if not ids:
        return 0
    conditions = [
        GlobalNotification.recipient_user_id.in_(ids),
        GlobalNotification.resolved_at.is_(None),
    ]
    if event_type:
        conditions.append(GlobalNotification.event_type == event_type)
    if event_type_prefix:
        conditions.append(GlobalNotification.event_type.startswith(event_type_prefix))
    if dedupe_key_prefix:
        conditions.append(GlobalNotification.dedupe_key.like(f"{dedupe_key_prefix}%"))

    rows = list(db.scalars(select(GlobalNotification).where(*conditions)).all())
    if not rows:
        return 0
    stamp = now or utc_now()
    note = (resolution_note or "").strip()[:255] or None
    for row in rows:
        row.resolved_at = stamp
        row.resolved_by_id = resolved_by_id
        row.resolution_note = note
    db.flush()
    logger.info(
        "notifications resolved event_type=%s prefix=%s count=%s",
        event_type,
        event_type_prefix,
        len(rows),
    )
    return len(rows)


def resolve_reminders(
    db: Session,
    *,
    dedupe_key_prefixes: Iterable[str],
    resolved_by_id: int | None = None,
    resolution_note: str | None = None,
) -> int:
    """Stop recurring overdue reminders once the underlying condition clears.

    Only clears the persisted reminder rows; it never inserts a new one, so the
    recurring popup cycle can never turn into notification spam.
    """

    candidates = list(
        db.scalars(
            select(GlobalNotification).where(GlobalNotification.resolved_at.is_(None))
        ).all()
    )
    total = 0
    for prefix in dedupe_key_prefixes:
        clean_prefix = str(prefix or "").strip()
        if not clean_prefix:
            continue
        matched = [
            row for row in candidates
            if (row.dedupe_key or "").startswith(clean_prefix)
            and row.resolved_at is None
        ]
        if not matched:
            continue
        stamp = utc_now()
        note = (resolution_note or "").strip()[:255] or None
        for row in matched:
            row.resolved_at = stamp
            row.resolved_by_id = resolved_by_id
            row.resolution_note = note
        db.flush()
        total += len(matched)
    if total:
        logger.info("overdue reminders resolved count=%s", total)
    return total
