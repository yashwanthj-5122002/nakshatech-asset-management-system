from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class MasterProjectCompletion(Base):
    """Master-project final delivery and Finance closure handoff.

    Phase 5 keeps technical workstream execution in the earlier Phase 1-4 tables.
    This row is created only when BD records final delivery after every active
    technical workstream is complete and every active data handover is accepted.
    """

    __tablename__ = "ops_v719_master_project_completion"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_ops_v719_master_project_completion_project"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True
    )
    final_output_reference: Mapped[str] = mapped_column(String(1500))
    delivery_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    finance_status: Mapped[str] = mapped_column(String(40), default="pending_billing", index=True)
    finance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    finance_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    financially_closed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    financially_closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
