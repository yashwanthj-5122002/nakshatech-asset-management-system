from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.notifications.schemas import (
    GlobalNotificationResponse,
    NotificationReadAllResponse,
    NotificationRefreshResponse,
    NotificationUnreadCountResponse,
)
from app.modules.notifications.service import (
    get_notification_for_user,
    list_notifications_for_user,
    mark_all_notifications_read,
    mark_notification_read,
    unread_count_for_user,
)
from app.services.ticket_sla_service import ensure_critical_sla_breach_notifications

router = APIRouter(prefix="/notifications/global", tags=["notifications"])

# Final Batch 4 authority no longer asks Management to approve IT Work or Asset
# Replacement. Keep historical rows in the database for audit, but do not show
# those obsolete approval prompts in the current Management notification feed.
_MANAGEMENT_OBSOLETE_APPROVAL_PREFIXES = (
    "approval.it_work.",
    "approval.replacement.",
)


def _excluded_prefixes(auth: CurrentAuth) -> tuple[str, ...]:
    return _MANAGEMENT_OBSOLETE_APPROVAL_PREFIXES if auth.effective_role == "management" else ()


@router.get("", response_model=list[GlobalNotificationResponse])
def list_global_notifications(
    unread_only: bool = False,
    category: str | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[GlobalNotificationResponse]:
    return list_notifications_for_user(
        db,
        user_id=auth.user.id,
        unread_only=unread_only,
        category=category,
        limit=limit,
        offset=offset,
        excluded_event_prefixes=_excluded_prefixes(auth),
    )


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
def global_notification_unread_count(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> NotificationUnreadCountResponse:
    return NotificationUnreadCountResponse(
        unread_count=unread_count_for_user(
            db,
            user_id=auth.user.id,
            excluded_event_prefixes=_excluded_prefixes(auth),
        )
    )


@router.post("/refresh-ticket-sla", response_model=NotificationRefreshResponse)
def refresh_ticket_sla_notifications(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> NotificationRefreshResponse:
    # Employees do not scan operational queues. Staff/management bell polling
    # materializes time-based critical SLA breach events in a deduplicated way.
    if auth.effective_role not in {"admin", "it", "drone", "software_team", "management"}:
        return NotificationRefreshResponse(created=0)
    created = ensure_critical_sla_breach_notifications(db)
    if created:
        db.commit()
    return NotificationRefreshResponse(created=created)


@router.post("/read-all", response_model=NotificationReadAllResponse)
def mark_all_global_notifications_read(
    category: str | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> NotificationReadAllResponse:
    updated = mark_all_notifications_read(db, user_id=auth.user.id, category=category)
    db.commit()
    return NotificationReadAllResponse(updated=updated)


@router.get("/{notification_id}", response_model=GlobalNotificationResponse)
def get_global_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> GlobalNotificationResponse:
    return get_notification_for_user(db, user_id=auth.user.id, notification_id=notification_id)


@router.post("/{notification_id}/read", response_model=GlobalNotificationResponse)
def mark_global_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> GlobalNotificationResponse:
    notification = mark_notification_read(db, user_id=auth.user.id, notification_id=notification_id)
    db.commit()
    db.refresh(notification)
    return notification
