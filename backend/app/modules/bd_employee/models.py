"""Personal BD prospect + communication records. No Finance client/project mutation."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class BdEmployeeProspect(Base):
    __tablename__ = "bd_employee_prospects"
    __table_args__ = (
        Index("ix_bd_employee_prospects_owner_status", "owner_user_id", "status"),
        Index("ix_bd_employee_prospects_owner_followup", "owner_user_id", "next_followup_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    service_interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="new")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_followup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class BdEmployeeContactActivity(Base):
    __tablename__ = "bd_employee_contact_activities"
    __table_args__ = (Index("ix_bd_employee_activity_owner_prospect", "owner_user_id", "prospect_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prospect_id: Mapped[int] = mapped_column(ForeignKey("bd_employee_prospects.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    outcome: Mapped[str] = mapped_column(String(30), nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    contacted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utc_now)
