"""Employee-origin BD client handoff with explicit manager approvals and project attribution.

Additive tables: existing clients, projects, workflows and employee prospects are unchanged.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class BdClientHandoff(Base):
    __tablename__ = "bd_employee_client_handoffs"
    __table_args__ = (
        Index("ix_bd_client_handoffs_employee_status", "employee_user_id", "status"),
        UniqueConstraint("registered_client_id", name="uq_bd_client_handoffs_client"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    prospect_id: Mapped[int | None] = mapped_column(ForeignKey("bd_employee_prospects.id", ondelete="RESTRICT"), nullable=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India", nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lead_source: Mapped[str] = mapped_column(String(40), default="other", nullable=False)
    service_interest: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    manager_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    registered_client_id: Mapped[int | None] = mapped_column(ForeignKey("finance_clients.id", ondelete="RESTRICT"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class BdClientHandoffEvent(Base):
    """Append-only audit history for handoff submission and review."""
    __tablename__ = "bd_employee_client_handoff_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("bd_employee_client_handoffs.id", ondelete="RESTRICT"), index=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)


class BdEmployeeProjectLink(Base):
    """Only a BD Manager can create official projects; provenance links them to the employee."""
    __tablename__ = "bd_employee_project_links"

    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("bd_employee_client_handoffs.id", ondelete="RESTRICT"), nullable=False)
    employee_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    manager_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
