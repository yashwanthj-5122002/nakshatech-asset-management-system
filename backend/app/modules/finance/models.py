from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class FinanceClient(Base):
    __tablename__ = "finance_clients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(255), index=True)
    primary_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contact_person_name: Mapped[str] = mapped_column(String(255), index=True)
    contact_person_phone: Mapped[str] = mapped_column(String(40))
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India", index=True)
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source_team: Mapped[str] = mapped_column(String(80), index=True)
    source_person_name: Mapped[str] = mapped_column(String(255), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    projects: Mapped[list["FinanceProject"]] = relationship(
        back_populates="client",
        order_by="FinanceProject.project_code, FinanceProject.id",
    )
    master_profile: Mapped["FinanceClientMasterProfile | None"] = relationship(
        back_populates="client", cascade="all, delete-orphan", uselist=False
    )


class FinanceProject(Base):
    __tablename__ = "finance_projects"
    __table_args__ = (
        UniqueConstraint("client_id", "project_number", name="uq_finance_project_client_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    # client_name is retained as a historical snapshot / legacy compatibility field.
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("finance_clients.id", ondelete="RESTRICT"), nullable=True, index=True)
    project_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_source_team: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    project_source_person_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    client_awarded_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_award_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    client: Mapped[FinanceClient | None] = relationship(back_populates="projects")
    master_profile: Mapped["FinanceProjectMasterProfile | None"] = relationship(
        back_populates="project", cascade="all, delete-orphan", uselist=False
    )
    assignments: Mapped[list["FinanceProjectAssignment"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="FinanceProjectAssignment.id"
    )


class FinanceClientMasterProfile(Base):
    """Additive Client Master fields aligned to the business client-code sheet."""

    __tablename__ = "finance_client_master_profiles"

    client_id: Mapped[int] = mapped_column(
        ForeignKey("finance_clients.id", ondelete="CASCADE"), primary_key=True
    )
    vendor_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    client_type: Mapped[str] = mapped_column(String(32), default="client", index=True)
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    bd_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    organization_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    contact_person_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    import_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    client: Mapped[FinanceClient] = relationship(back_populates="master_profile")


class FinanceProjectMasterProfile(Base):
    """Additive Project Master ownership/lifecycle fields without altering legacy project rows."""

    __tablename__ = "finance_project_master_profiles"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), primary_key=True
    )
    task: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    project_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reporting_manager_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    project: Mapped[FinanceProject] = relationship(back_populates="master_profile")
    project_manager: Mapped["User | None"] = relationship("User", foreign_keys=[project_manager_id])
    reporting_manager: Mapped["User | None"] = relationship("User", foreign_keys=[reporting_manager_id])


class FinanceProjectAssignment(Base):
    """Active Employee-to-Project assignment used by privacy-safe Travel/KM project selection."""

    __tablename__ = "finance_project_assignments"
    __table_args__ = (UniqueConstraint("project_id", "user_id", name="uq_finance_project_assignment_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assigned_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    project: Mapped[FinanceProject] = relationship(back_populates="assignments")
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])


class ExpenseClaim(Base):
    __tablename__ = "expense_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id"), index=True)
    claim_type: Mapped[str] = mapped_column(String(40), index=True)
    purpose_description: Mapped[str] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    previous_advance_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_already_used: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    # V3: the employee's requested work period is immutable history after submit.
    requested_work_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    requested_work_end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Admin/Finance-approved dates are separate so the original request is never overwritten.
    approved_work_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    approved_work_end_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    settlement_due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    # Additional advances must point to the original Advance Request.
    parent_advance_claim_id: Mapped[int | None] = mapped_column(
        ForeignKey("expense_claims.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # Separate from payment status: a paid advance remains open until its bills are settled.
    settlement_status: Mapped[str] = mapped_column(String(50), default="not_required", index=True)

    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)

    admin_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    admin_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    admin_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    finance_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    finance_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    payment_reference: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    project: Mapped[FinanceProject] = relationship()
    parent_advance: Mapped[ExpenseClaim | None] = relationship(
        "ExpenseClaim",
        remote_side="ExpenseClaim.id",
        foreign_keys=[parent_advance_claim_id],
        back_populates="linked_additional_advances",
    )
    linked_additional_advances: Mapped[list[ExpenseClaim]] = relationship(
        "ExpenseClaim",
        foreign_keys="ExpenseClaim.parent_advance_claim_id",
        back_populates="parent_advance",
        order_by="ExpenseClaim.id",
    )
    items: Mapped[list[ExpenseClaimItem]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpenseClaimItem.id",
    )
    attachments: Mapped[list[ExpenseClaimAttachment]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpenseClaimAttachment.id",
    )
    events: Mapped[list[ExpenseClaimEvent]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpenseClaimEvent.id",
    )
    payments: Mapped[list[ExpenseClaimPayment]] = relationship(
        back_populates="claim",
        cascade="all, delete-orphan",
        order_by="ExpenseClaimPayment.payment_date, ExpenseClaimPayment.id",
    )
    settlement: Mapped[ExpenseSettlement | None] = relationship(
        back_populates="root_claim",
        cascade="all, delete-orphan",
        uselist=False,
        foreign_keys="ExpenseSettlement.root_claim_id",
    )


class ExpenseClaimItem(Base):
    __tablename__ = "expense_claim_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    other_category: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_mode: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="items")


class ExpenseClaimAttachment(Base):
    __tablename__ = "expense_claim_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="attachments")


class ExpenseClaimEvent(Base):
    __tablename__ = "expense_claim_events"
    __table_args__ = (
        UniqueConstraint("claim_id", "event_key", name="uq_expense_claim_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="events")


class ExpenseClaimPayment(Base):
    __tablename__ = "expense_claim_payments"
    __table_args__ = (
        UniqueConstraint("claim_id", "payment_reference", name="uq_expense_claim_payment_reference"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True)
    payment_reference: Mapped[str] = mapped_column(String(180), index=True)
    payment_mode: Mapped[str] = mapped_column(String(40), default="bank_transfer", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    claim: Mapped[ExpenseClaim] = relationship(back_populates="payments")


class ExpenseSettlement(Base):
    __tablename__ = "expense_settlements"
    __table_args__ = (
        UniqueConstraint("root_claim_id", name="uq_expense_settlement_root_claim"),
        UniqueConstraint("settlement_code", name="uq_expense_settlement_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settlement_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    root_claim_id: Mapped[int] = mapped_column(ForeignKey("expense_claims.id", ondelete="CASCADE"), index=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    total_advance_received: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    total_expense_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    balance_to_return: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))
    shortage_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0.00"))

    admin_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    admin_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    admin_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_decision_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    finance_decision_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_comments: Mapped[str | None] = mapped_column(Text, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    root_claim: Mapped[ExpenseClaim] = relationship(back_populates="settlement", foreign_keys=[root_claim_id])
    items: Mapped[list[ExpenseSettlementItem]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", order_by="ExpenseSettlementItem.id"
    )
    attachments: Mapped[list[ExpenseSettlementAttachment]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", order_by="ExpenseSettlementAttachment.id"
    )
    events: Mapped[list[ExpenseSettlementEvent]] = relationship(
        back_populates="settlement", cascade="all, delete-orphan", order_by="ExpenseSettlementEvent.id"
    )


class ExpenseSettlementItem(Base):
    __tablename__ = "expense_settlement_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("expense_settlements.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(80), index=True)
    other_category: Mapped[str | None] = mapped_column(String(160), nullable=True)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_mode: Mapped[str] = mapped_column(String(40), default="upi", index=True)
    expense_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    settlement: Mapped[ExpenseSettlement] = relationship(back_populates="items")


class ExpenseSettlementAttachment(Base):
    __tablename__ = "expense_settlement_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("expense_settlements.id", ondelete="CASCADE"), index=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    settlement: Mapped[ExpenseSettlement] = relationship(back_populates="attachments")


class ExpenseSettlementEvent(Base):
    __tablename__ = "expense_settlement_events"
    __table_args__ = (
        UniqueConstraint("settlement_id", "event_key", name="uq_expense_settlement_event_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("expense_settlements.id", ondelete="CASCADE"), index=True)
    event_key: Mapped[str] = mapped_column(String(160))
    action: Mapped[str] = mapped_column(String(80), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(40), nullable=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    settlement: Mapped[ExpenseSettlement] = relationship(back_populates="events")
