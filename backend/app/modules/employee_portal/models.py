from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class UserBranchAccess(Base):
    __tablename__ = "user_branch_access"
    __table_args__ = (UniqueConstraint("user_id", "branch_id", name="uq_user_branch_access"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id", ondelete="CASCADE"), index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    branch: Mapped[Branch] = relationship()


class EmailOTPChallenge(Base):
    __tablename__ = "email_otp_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    purpose: Mapped[str] = mapped_column(String(40), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class AuthenticatorCredential(Base):
    __tablename__ = "authenticator_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    encrypted_secret: Mapped[str] = mapped_column(Text)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class EmployeeMaster(Base):
    """HR-owned employee identity used to authorize self-registration.

    Authorization intentionally remains on ``User.role``.  ``department_code`` is
    profile scope and must never be treated as a privileged role assignment.
    """

    __tablename__ = "employee_master"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Nullable: New Joiner onboarding rows are created by HR without an XLSX serial number.
    source_sl_no: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    access_card_no: Mapped[str] = mapped_column(String(120))
    access_card_no_normalized: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    employee_number: Mapped[str] = mapped_column(String(120))
    employee_number_normalized: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    employee_name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(80))
    phone_normalized: Mapped[str] = mapped_column(String(40))
    department_raw: Mapped[str] = mapped_column(String(160), index=True)
    department_code: Mapped[str] = mapped_column(String(80), index=True)
    designation_raw: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255))
    email_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    employment_status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    crm_account_status: Mapped[str] = mapped_column(String(40), default="not_registered", index=True)
    linked_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, unique=True, index=True
    )
    source_batch_id: Mapped[str] = mapped_column(String(80), index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class EmployeeOnboardingRequest(Base):
    """Future new-joiner onboarding: HR draft -> IT official email -> Management final approval.

    Additive workflow table. Final approval creates the Employee Master row that makes
    the new joiner eligible for the normal Create CRM Account self-registration flow.
    """

    __tablename__ = "employee_onboarding_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_name: Mapped[str] = mapped_column(String(255))
    personal_email: Mapped[str] = mapped_column(String(255), index=True)
    personal_email_normalized: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str] = mapped_column(String(80))
    employee_number: Mapped[str] = mapped_column(String(120))
    employee_number_normalized: Mapped[str] = mapped_column(String(120), index=True)
    access_card_no: Mapped[str] = mapped_column(String(120))
    access_card_no_normalized: Mapped[str] = mapped_column(String(120), index=True)
    department_code: Mapped[str] = mapped_column(String(80), index=True)
    designation: Mapped[str] = mapped_column(String(200))
    joining_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="hr_draft", index=True)
    official_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    official_email_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    submitted_to_it_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    it_approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    it_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    management_approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    rejected_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    employee_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("employee_master.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    selected_branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    branch: Mapped[Branch | None] = relationship()


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), index=True)
    department: Mapped[str] = mapped_column(String(40), index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    reporting_manager_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_number: Mapped[str | None] = mapped_column(String(120), nullable=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True)
    asset_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    component: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    component_asset_tag: Mapped[str | None] = mapped_column(String(160), nullable=True)
    problem_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    problem_label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    impact_assessment: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    sla_target_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    branch: Mapped[Branch] = relationship()


class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    message: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("ticket_messages.id", ondelete="CASCADE"), nullable=True, index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(80))
    file_size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class TicketNotification(Base):
    __tablename__ = "ticket_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    recipient_role: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    recipient_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    notification_type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    result: Mapped[str] = mapped_column(String(30), default="success", index=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True, index=True)
    module: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
