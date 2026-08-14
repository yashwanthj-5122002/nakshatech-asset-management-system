from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ITPurchaseApprovalChannel(Base):
    """One active email approval channel for a Purchase Request.

    The Purchase Request remains the source of truth for lifecycle status. This
    table only stores the selected email recipient, one-time token state and
    channel metadata so email and the web application cannot diverge.
    """

    __tablename__ = "it_purchase_approval_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("it_purchase_requests.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    approver_name: Mapped[str] = mapped_column(String(255))
    approver_email: Mapped[str] = mapped_column(String(255), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    token_consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    email_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    email_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_source: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ITPurchaseApprovalEmailLog(Base):
    """Immutable proof that an approval-related email send was attempted."""

    __tablename__ = "it_purchase_approval_email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(
        ForeignKey("it_purchase_requests.id", ondelete="CASCADE"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recipient_email: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    delivery_status: Mapped[str] = mapped_column(String(30), index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
