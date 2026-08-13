from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


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
