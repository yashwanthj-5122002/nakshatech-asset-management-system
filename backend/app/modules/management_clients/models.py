from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ManagementClientIntake(Base):
    """Isolated client register; not a FinanceProject or a BD-owned client."""

    __tablename__ = "management_client_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(255), index=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India")
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_person_name: Mapped[str] = mapped_column(String(255))
    contact_person_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_person_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    work_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_person_name: Mapped[str] = mapped_column(String(255), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
