from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ProjectFeedbackRequest(Base):
    __tablename__ = "project_feedback_requests"
    __table_args__ = (
        UniqueConstraint("project_id", "cycle_number", name="uq_project_feedback_request_cycle"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    request_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, index=True)
    recipient_email: Mapped[str] = mapped_column(String(255), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    message_thread_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="sent", index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    reminder_count: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectFeedbackResponse(Base):
    __tablename__ = "project_feedback_responses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    feedback_request_id: Mapped[int] = mapped_column(
        ForeignKey("project_feedback_requests.id", ondelete="CASCADE"), index=True
    )
    response_type: Mapped[str] = mapped_column(String(40), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    classification_status: Mapped[str] = mapped_column(String(40), default="pending_bd", index=True)
    classified_as: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    classified_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    classified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    responded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectFeedbackAttachment(Base):
    __tablename__ = "project_feedback_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    feedback_response_id: Mapped[int] = mapped_column(
        ForeignKey("project_feedback_responses.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    mime_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectReworkCycle(Base):
    __tablename__ = "project_rework_cycles"
    __table_args__ = (
        UniqueConstraint("project_id", "cycle_number", name="uq_project_rework_cycle_number"),
        UniqueConstraint("source_feedback_response_id", name="uq_project_rework_source_response"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    cycle_number: Mapped[int] = mapped_column(Integer, index=True)
    source_feedback_response_id: Mapped[int] = mapped_column(
        ForeignKey("project_feedback_responses.id", ondelete="RESTRICT"), index=True
    )
    # Distinguishes execution driven by a client CORRECTION_REWORK from execution
    # driven by an APPROVED_CHANGE_REQUEST (paid additional scope), so dashboards
    # and history never conflate the two even though both reuse the same
    # Production -> QC -> QA -> Delivery -> resubmission pipeline.
    cycle_type: Mapped[str] = mapped_column(String(30), default="CORRECTION_REWORK", index=True)
    source_change_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_change_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(40), default="REWORK_OPEN", index=True)
    correction_scope: Mapped[str] = mapped_column(Text)
    project_manager_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    team_leader_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    opened_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # How the PM confirmed the rework team: 'reuse' (carry the original work context forward) or 'adjust' (manual).
    team_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    resubmitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectDeliveryVersion(Base):
    __tablename__ = "project_delivery_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version_number", name="uq_project_delivery_version_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    rework_cycle_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_rework_cycles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, index=True)
    delivery_reference: Mapped[str] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectChangeRequest(Base):
    __tablename__ = "project_change_requests"
    __table_args__ = (
        UniqueConstraint("source_feedback_response_id", name="uq_project_change_request_source_response"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    request_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    source_feedback_response_id: Mapped[int] = mapped_column(
        ForeignKey("project_feedback_responses.id", ondelete="RESTRICT"), index=True
    )
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    commercial_impact: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decided_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decision_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectInvoice(Base):
    __tablename__ = "project_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="INVOICE_DRAFT", index=True)
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    raised_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    raised_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectInvoicePayment(Base):
    __tablename__ = "project_invoice_payments"
    __table_args__ = (
        UniqueConstraint("invoice_id", "payment_reference", name="uq_project_invoice_payment_reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("project_invoices.id", ondelete="CASCADE"), index=True)
    payment_reference: Mapped[str] = mapped_column(String(180), index=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    payment_mode: Mapped[str] = mapped_column(String(40), default="bank_transfer", index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectMessage(Base):
    __tablename__ = "project_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    recipient_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectTimelineEvent(Base):
    __tablename__ = "project_timeline_events"
    __table_args__ = (
        UniqueConstraint("project_id", "event_key", name="uq_project_timeline_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(180))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
