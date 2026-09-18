from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class TechnicalSampleRequest(Base):
    """One BD-controlled technical sample workflow before Finance Project creation."""

    __tablename__ = "ops_v716_technical_sample_requests"
    __table_args__ = (
        UniqueConstraint("opportunity_id", name="uq_ops_v716_sample_opportunity"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v701_bd_opportunities.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    instructions: Mapped[str] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="requested", index=True)
    client_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_review_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    client_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    departments: Mapped[list["TechnicalSampleDepartment"]] = relationship(
        back_populates="sample_request",
        cascade="all, delete-orphan",
        order_by="TechnicalSampleDepartment.id",
    )


class TechnicalSampleDepartment(Base):
    """One selected peer technical department participating in a sample request."""

    __tablename__ = "ops_v716_technical_sample_departments"
    __table_args__ = (
        UniqueConstraint("sample_request_id", "department_code", name="uq_ops_v716_sample_department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_request_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v716_technical_sample_requests.id", ondelete="CASCADE"), index=True
    )
    department_code: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), default="requested", index=True)
    revision_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_submitted_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    last_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    sample_request: Mapped[TechnicalSampleRequest] = relationship(back_populates="departments")
    submissions: Mapped[list["TechnicalSampleSubmission"]] = relationship(
        back_populates="department",
        cascade="all, delete-orphan",
        order_by="TechnicalSampleSubmission.attempt_no",
    )


class TechnicalSampleSubmission(Base):
    """Immutable submission history for one department's sample attempts."""

    __tablename__ = "ops_v716_technical_sample_submissions"
    __table_args__ = (
        UniqueConstraint("sample_department_id", "attempt_no", name="uq_ops_v716_sample_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sample_department_id: Mapped[int] = mapped_column(
        ForeignKey("ops_v716_technical_sample_departments.id", ondelete="CASCADE"), index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer)
    sample_reference: Mapped[str] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    department: Mapped[TechnicalSampleDepartment] = relationship(back_populates="submissions")
