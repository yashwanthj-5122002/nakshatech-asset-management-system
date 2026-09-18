from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class TechnicalRoutingControl(Base):
    """Singleton production-cutover control for the six peer technical departments."""

    __tablename__ = "ops_v721_technical_routing_control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    routing_mode: Mapped[str] = mapped_column(String(40), default="uat_demo_locked", index=True)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    activated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    activation_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
