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


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationRefreshResponse(BaseModel):
    created: int


class NotificationReadAllResponse(BaseModel):
    updated: int
