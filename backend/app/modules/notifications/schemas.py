from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class GlobalNotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_role: str | None
    event_type: str
    category: str
    title: str
    message: str
    target_url: str | None
    is_read: bool
    read_at: datetime | None
    created_at: datetime
    # Additive popup fields. Defaults keep older rows valid.
    severity: str = "info"
    requires_action: bool = False
    resolved_at: datetime | None = None
    is_reminder: bool = False


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationRefreshResponse(BaseModel):
    created: int


class NotificationReadAllResponse(BaseModel):
    updated: int


class NotificationPendingCountResponse(BaseModel):
    """Unresolved notifications awaiting a business decision."""

    pending_count: int


class NotificationPopupItem(BaseModel):
    """One center-popup candidate.

    ``is_read`` (the user saw it) and ``is_resolved`` (the required business
    action completed) stay independent: read=True + is_resolved=False is the
    normal "user clicked Later" state.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    recipient_role: str | None = None
    event_type: str
    category: str
    title: str
    message: str
    target_url: str | None = None
    is_read: bool = False
    read_at: datetime | None = None
    created_at: datetime
    severity: str = "info"
    requires_action: bool = False
    is_resolved: bool = False
    resolved_at: datetime | None = None
    is_reminder: bool = False
    metadata: dict = {}


class NotificationSettingsResponse(BaseModel):
    overdue_popup_reminder_minutes: int
    suggested_minutes: list[int] = []
    default_minutes: int
    can_manage: bool = False
    capability: str
    # Audit value returned by an update: the interval that was replaced.
    previous_overdue_popup_reminder_minutes: int | None = None
    updated_at: datetime | None = None


class NotificationSettingsUpdateRequest(BaseModel):
    overdue_popup_reminder_minutes: int
