
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class BDAISubmission(Base):
    __tablename__ = "bd_ai_submissions"

    __table_args__ = (
        UniqueConstraint(
            "employee_user_id",
            "initial_fingerprint",
            name="uq_bd_ai_initial_submission",
        ),
        CheckConstraint(
            "employee_user_id <> manager_user_id",
            name="ck_bd_ai_no_self_approval",
        ),
        CheckConstraint(
            "status IN ('pending_review', 'approved', "
            "'returned', 'rejected')",
            name="ck_bd_ai_submission_status",
        ),
        CheckConstraint(
            "current_revision >= 1",
            name="ck_bd_ai_current_revision",
        ),
        Index(
            "ix_bd_ai_employee_status",
            "employee_user_id",
            "status",
        ),
        Index(
            "ix_bd_ai_manager_status",
            "manager_user_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    employee_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    manager_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    employee_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    employee_code: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    initial_fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(24),
        default="pending_review",
        nullable=False,
    )

    current_revision: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class BDAISubmissionRevision(Base):
    __tablename__ = "bd_ai_submission_revisions"

    __table_args__ = (
        UniqueConstraint(
            "submission_id",
            "revision_number",
            name="uq_bd_ai_submission_revision",
        ),
        CheckConstraint(
            "revision_number >= 1",
            name="ck_bd_ai_revision_number",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    submission_id: Mapped[int] = mapped_column(
        ForeignKey(
            "bd_ai_submissions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    revision_number: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    snapshot: Mapped[dict] = mapped_column(
        JSON, nullable=False
    )

    fingerprint: Mapped[str] = mapped_column(
        String(64), nullable=False
    )

    submitted_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class BDAISubmissionEvent(Base):
    __tablename__ = "bd_ai_submission_events"

    __table_args__ = (
        UniqueConstraint(
            "revision_id",
            "action",
            name="uq_bd_ai_revision_event",
        ),
        CheckConstraint(
            "action IN ('submitted', 'resubmitted', "
            "'approved', 'returned', 'rejected')",
            name="ck_bd_ai_event_action",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )

    revision_id: Mapped[int] = mapped_column(
        ForeignKey(
            "bd_ai_submission_revisions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    actor_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    actor_name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    action: Mapped[str] = mapped_column(
        String(30), nullable=False
    )

    note: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )
