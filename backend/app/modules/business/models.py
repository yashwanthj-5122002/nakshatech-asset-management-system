from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class BusinessRecord(Base):
    """Monthly business done for one project, entered by Finance.

    One row per (project, reporting month). Client, Project Manager and department
    are snapshotted at entry time so the monthly figures and their history stay
    stable even if the project's PM is reassigned later.
    """

    __tablename__ = "business_records"
    __table_args__ = (
        UniqueConstraint("project_id", "reporting_month", name="uq_business_record_project_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reporting_month: Mapped[str] = mapped_column(String(7), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("finance_clients.id", ondelete="SET NULL"), nullable=True, index=True)
    project_manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    project_manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department_code: Mapped[str] = mapped_column(String(40), default="ortho", index=True)

    amount_total: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    amount_released: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    amount_pending: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default="submitted", index=True)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    entered_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    history: Mapped[list["BusinessRecordHistory"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="BusinessRecordHistory.id",
    )


class BusinessRecordHistory(Base):
    """Append-only audit trail for every monthly business figure change."""

    __tablename__ = "business_record_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_id: Mapped[int | None] = mapped_column(
        ForeignKey("business_records.id", ondelete="CASCADE"), nullable=True, index=True
    )
    reporting_month: Mapped[str] = mapped_column(String(7), index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    client_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_manager_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    changes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    record: Mapped[BusinessRecord | None] = relationship(back_populates="history")
