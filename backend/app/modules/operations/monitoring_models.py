from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ProjectWorkstreamProgress(Base):
    """Latest reported progress for one technical project workstream.

    The V7.0.15 workstream table remains the source of truth for workflow status.
    This Phase 4 row adds a lightweight progress percentage and note without
    changing the earlier workstream schema.
    """

    __tablename__ = "ops_v718_project_workstream_progress"
    __table_args__ = (
        UniqueConstraint("workstream_id", name="uq_ops_v718_workstream_progress"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workstream_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v715_project_workstreams.id", ondelete="CASCADE"), index=True
    )
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    update_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectHandoverSchedule(Base):
    """BD coordination due date and note for one Phase 3 data handover."""

    __tablename__ = "ops_v718_project_handover_schedule"
    __table_args__ = (
        UniqueConstraint("handover_id", name="uq_ops_v718_handover_schedule"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handover_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v717_project_data_handovers.id", ondelete="CASCADE"), index=True
    )
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    coordination_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
