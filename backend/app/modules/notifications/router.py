from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.notification_access import (
    CAPABILITY_MANAGE_NOTIFICATION_SETTINGS,
    can_manage_notification_settings,
    require_notification_settings_permission,
)
from app.core.database import get_db
from app.modules.notifications.schemas import (
    GlobalNotificationResponse,
    NotificationPopupItem,
    NotificationPendingCountResponse,
    NotificationReadAllResponse,
    NotificationRefreshResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    NotificationUnreadCountResponse,
)
from app.modules.notifications.service import (
    get_notification_for_user,
    list_notifications_for_user,
    list_popup_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    pending_count_for_user,
    unread_count_for_user,
)
from app.modules.notifications.settings_service import (
    notification_settings_payload,
    set_overdue_reminder_minutes,
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


@router.get("/popup-queue", response_model=list[NotificationPopupItem])
def notification_popup_queue(
    limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[dict]:
    """Unresolved notifications for the CENTER POPUP queue.

    Read-only: it never resolves, approves or rejects anything, so rendering or
    dismissing a popup cannot change business state.
    """

    return list_popup_notifications(
        db,
        user_id=auth.user.id,
        effective_role=auth.effective_role,
        limit=limit,
        excluded_event_prefixes=_excluded_prefixes(auth),
    )


@router.get("/pending-count", response_model=NotificationPendingCountResponse)
def notification_pending_count(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> NotificationPendingCountResponse:
    """Notifications still awaiting a business decision (resolved != read)."""

    return NotificationPendingCountResponse(
        pending_count=pending_count_for_user(
            db,
            user_id=auth.user.id,
            excluded_event_prefixes=_excluded_prefixes(auth),
        )
    )


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
# ---------------------------------------------------------------------------
# Notification settings (overdue popup reminder interval)
#
# Kept on the SAME router so it mounts under /api/notifications/global.
# READ is open to any signed-in user (the client needs the current interval to
# schedule its single reminder timer). UPDATE is gated on the
# manage_notification_settings capability enforced on the BACKEND.
# ---------------------------------------------------------------------------


@router.get("/settings/notification-settings", response_model=NotificationSettingsResponse)
def read_notification_settings(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    payload = notification_settings_payload(db)
    payload["can_manage"] = can_manage_notification_settings(auth.user, auth.effective_role)
    payload["capability"] = CAPABILITY_MANAGE_NOTIFICATION_SETTINGS
    return payload


@router.put("/settings/notification-settings", response_model=NotificationSettingsResponse)
def update_notification_settings(
    payload: NotificationSettingsUpdateRequest,
    db: Session = Depends(get_db),
    user=Depends(require_notification_settings_permission),
) -> dict:
    result = set_overdue_reminder_minutes(
        db, minutes=payload.overdue_popup_reminder_minutes, actor_id=user.id
    )
    db.commit()
    result["can_manage"] = True
    result["capability"] = CAPABILITY_MANAGE_NOTIFICATION_SETTINGS
    return result
