from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class NotificationSetting(Base):
    """Key/value application notification settings managed by authorized users.

    A deliberately tiny, additive table: one row per setting key. It stores no
    business data and is never joined by finance/commercial logic.
    """

    __tablename__ = "notification_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    setting_value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class GlobalNotification(Base):
    """One persistent notification receipt for one concrete user.

    Role-targeted notifications are fanned out to active users when the event is
    created. Keeping one row per user makes unread/read state private to that
    user and prevents one manager from clearing another manager's notification.
    """

    __tablename__ = "global_notifications"
    __table_args__ = (
        UniqueConstraint(
            "recipient_user_id",
            "dedupe_key",
            name="uq_global_notifications_recipient_dedupe",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipient_role: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    category: Mapped[str] = mapped_column(String(40), default="system", index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    target_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    # ---------------------------------------------------------------------
    # Additive columns (notification popup experience).
    #
    # Every column below is nullable/defaulted so existing rows and existing
    # call sites of create_global_notification keep working unchanged.
    #
    # READ vs RESOLVED are deliberately separate concepts:
    #   * is_read  -> the recipient has SEEN the notification (popup or bell)
    #   * resolved -> the required BUSINESS ACTION has actually completed
    # A notification can therefore be read=True and resolved_at=NULL, which is
    # exactly the "user clicked Later" state.
    # ---------------------------------------------------------------------
    severity: Mapped[str] = mapped_column(String(16), default="info", index=True)
    requires_action: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    resolved_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional structured payload for the center popup. Money fields are stripped
    # server-side for roles that may not see them; see notification_payload().
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # True for time-based recurring conditions (overdue payments/advances) so the
    # client can resurface the popup on an interval without inserting new rows.
    is_reminder: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None
