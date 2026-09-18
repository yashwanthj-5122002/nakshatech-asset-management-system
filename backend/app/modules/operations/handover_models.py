from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class ProjectDataHandover(Base):
    """One directed technical-team dependency under one Finance Project ID."""

    __tablename__ = "ops_v717_project_data_handovers"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "from_workstream_id",
            "to_workstream_id",
            name="uq_ops_v717_project_handover_pair",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handover_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True
    )
    from_workstream_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v715_project_workstreams.id", ondelete="CASCADE"), index=True
    )
    to_workstream_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v715_project_workstreams.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    expected_output: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="waiting_for_source", index=True)
    current_attempt_no: Mapped[int] = mapped_column(Integer, default=0)
    revision_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    accepted_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    is_active: Mapped[bool] = mapped_column(default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    attempts: Mapped[list["ProjectDataHandoverAttempt"]] = relationship(
        back_populates="handover",
        cascade="all, delete-orphan",
        order_by="ProjectDataHandoverAttempt.attempt_no",
    )


class ProjectDataHandoverAttempt(Base):
    """Immutable submit/resubmit history for one data handover."""

    __tablename__ = "ops_v717_project_data_handover_attempts"
    __table_args__ = (
        UniqueConstraint("handover_id", "attempt_no", name="uq_ops_v717_handover_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    handover_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v717_project_data_handovers.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    output_reference: Mapped[str] = mapped_column(String(1500))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    handover: Mapped[ProjectDataHandover] = relationship(back_populates="attempts")
