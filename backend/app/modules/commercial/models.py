"""Additive project commercial / cost tables.

Everything hangs off the EXISTING ``finance_projects`` row (Project ID / Client ID). All money columns
are NUMERIC. INR is the accounting base currency: every foreign-currency event stores its own
immutable FX snapshot and the INR equivalent at that event's date.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now

MONEY = Numeric(18, 2)
RATE = Numeric(18, 8)


class ProjectFxSnapshot(Base):
    """One historical FX snapshot per financial event (estimate, revision, invoice, payment, vendor invoice)."""

    __tablename__ = "project_fx_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(40), index=True)
    event_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    currency_code: Mapped[str] = mapped_column(String(3), index=True)
    original_amount: Mapped[Decimal] = mapped_column(MONEY)
    fx_rate_to_inr: Mapped[Decimal] = mapped_column(RATE)
    fx_rate_date: Mapped[date] = mapped_column(Date, index=True)
    fx_rate_timestamp: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fx_rate_source: Mapped[str] = mapped_column(String(120))
    fx_rate_mode: Mapped[str] = mapped_column(String(30), index=True)
    reference_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    inr_equivalent: Mapped[Decimal] = mapped_column(MONEY)
    fx_locked: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    entered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    verified_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProjectFxOverride(Base):
    """Append-only audit history of manual FX overrides (no silent overwrite)."""

    __tablename__ = "project_fx_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("project_fx_snapshots.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    old_rate: Mapped[Decimal | None] = mapped_column(RATE, nullable=True)
    new_rate: Mapped[Decimal] = mapped_column(RATE)
    old_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_mode: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    rate_date: Mapped[date] = mapped_column(Date)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectCommercialEstimateRevision(Base):
    """BD commercial estimate. Revision 1 is frozen as the baseline when Finance approves the project."""

    __tablename__ = "project_commercial_estimate_revisions"
    __table_args__ = (UniqueConstraint("project_id", "revision_no", name="uq_project_estimate_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    revision_no: Mapped[int] = mapped_column(Integer)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # DRAFT -> (Finance approves the project) APPROVED baseline; later revisions PENDING_APPROVAL -> APPROVED / REJECTED
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)

    quotation_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    po_wo_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scope_description: Mapped[str] = mapped_column(Text)
    billing_type: Mapped[str] = mapped_column(String(30))
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_billing_milestone: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # BD's expected client collection date. This is a forecast only; Finance invoice due dates and
    # actual payment dates remain authoritative once billing begins.
    projected_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    currency_code: Mapped[str] = mapped_column(String(3), index=True)
    estimated_amount: Mapped[Decimal] = mapped_column(MONEY)          # headline value, original currency
    taxable_base_amount: Mapped[Decimal] = mapped_column(MONEY)       # revenue-before-tax basis, original currency
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    expected_tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    expected_gross: Mapped[Decimal] = mapped_column(MONEY)
    estimated_direct_cost_inr: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)  # optional cost budget (INR)
    # Unit-rate / milestone billing basis (additive). ``unit_rate`` is in the revision's original currency.
    unit_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    estimated_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)

    fx_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("project_fx_snapshots.id", ondelete="SET NULL"), nullable=True)
    fx_rate_to_inr: Mapped[Decimal] = mapped_column(RATE)
    fx_rate_date: Mapped[date] = mapped_column(Date)
    fx_rate_source: Mapped[str] = mapped_column(String(120))
    fx_rate_mode: Mapped[str] = mapped_column(String(30))
    estimated_inr: Mapped[Decimal] = mapped_column(MONEY)
    base_inr: Mapped[Decimal] = mapped_column(MONEY)
    tax_inr: Mapped[Decimal] = mapped_column(MONEY)
    gross_inr: Mapped[Decimal] = mapped_column(MONEY)

    estimate_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    previous_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    previous_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    previous_base_inr: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    decision_comments: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProjectCommercialMilestone(Base):
    """Approved billing milestone schedule of one estimate revision (used only for milestone billing)."""

    __tablename__ = "project_commercial_milestones"
    __table_args__ = (UniqueConstraint("revision_id", "sequence", name="uq_project_commercial_milestone_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("project_commercial_estimate_revisions.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    milestone_name: Mapped[str] = mapped_column(String(255))
    percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)      # % of the taxable base
    amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)               # taxable amount, original currency


class ProjectBillingBasis(Base):
    """Project Manager's confirmation of what is actually billable (operational facts only, never rates)."""

    __tablename__ = "project_billing_basis_entries"
    __table_args__ = (UniqueConstraint("project_id", "entry_no", name="uq_project_billing_basis_entry"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    entry_no: Mapped[int] = mapped_column(Integer)
    estimate_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_estimate_revisions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    billing_type: Mapped[str] = mapped_column(String(30))
    cumulative_billable_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_milestones.id", ondelete="SET NULL"), nullable=True, index=True
    )
    milestone_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    delivery_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    acceptance_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pm_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    billing_readiness_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confirmed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectExpense(Base):
    """Employee project expense. INR ONLY: there is intentionally no currency / FX column."""

    __tablename__ = "project_expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_code: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    expense_date: Mapped[date] = mapped_column(Date, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    purpose: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(MONEY)                     # claimed, INR
    approved_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)   # INR, set by Finance
    payment_source: Mapped[str] = mapped_column(String(20), default="EMPLOYEE_PAID", index=True)
    status: Mapped[str] = mapped_column(String(30), default="DRAFT", index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    phase_key: Mapped[str] = mapped_column(String(30), default="ORIGINAL", index=True)
    linked_vendor_invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_vendor_invoices.id", ondelete="SET NULL"), nullable=True, index=True
    )
    finance_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    finance_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reimbursed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    reimbursement_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    __table_args__ = (Index("ix_project_expenses_project_status", "project_id", "status"),)


class ProjectExpenseEvent(Base):
    __tablename__ = "project_expense_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expense_id: Mapped[int] = mapped_column(ForeignKey("project_expenses.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    from_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    to_status: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    old_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    new_amount: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectExpenseDeclaration(Base):
    __tablename__ = "project_expense_declarations"
    __table_args__ = (UniqueConstraint("project_id", "employee_id", "phase_key", name="uq_project_expense_declaration"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    phase_key: Mapped[str] = mapped_column(String(30), default="ORIGINAL")
    declaration_status: Mapped[str] = mapped_column(String(30))     # NO_MORE_EXPENSES | HAS_EXPENSES
    declared_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProjectVendorInvoice(Base):
    """Vendor / subcontractor invoice = COST to Nakshatech (never a client invoice)."""

    __tablename__ = "project_vendor_invoices"
    __table_args__ = (UniqueConstraint("project_id", "vendor_name", "invoice_number", name="uq_project_vendor_invoice_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)
    vendor_gstin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(100), index=True)
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    po_wo_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    description: Mapped[str] = mapped_column(Text)
    hsn_sac: Mapped[str | None] = mapped_column(String(20), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    rate: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="INR")
    taxable_amount: Mapped[Decimal] = mapped_column(MONEY)
    cgst: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    sgst: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    igst: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    other_tax: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0.00"))
    gross_amount: Mapped[Decimal] = mapped_column(MONEY)
    fx_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("project_fx_snapshots.id", ondelete="SET NULL"), nullable=True)
    fx_rate_to_inr: Mapped[Decimal] = mapped_column(RATE, default=Decimal("1"))
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fx_rate_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fx_rate_mode: Mapped[str] = mapped_column(String(30), default="BASE_CURRENCY")
    taxable_inr: Mapped[Decimal] = mapped_column(MONEY)
    tax_inr: Mapped[Decimal] = mapped_column(MONEY)
    gross_inr: Mapped[Decimal] = mapped_column(MONEY)
    payment_status: Mapped[str] = mapped_column(String(20), default="UNPAID", index=True)
    payment_source: Mapped[str] = mapped_column(String(20), default="COMPANY_PAID", index=True)
    linked_employee_expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_expenses.id", ondelete="SET NULL", use_alter=True, name="fk_vendor_invoice_employee_expense"),
        nullable=True, index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)   # ACTIVE | CANCELLED
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ProjectVendorPayment(Base):
    __tablename__ = "project_vendor_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_invoice_id: Mapped[int] = mapped_column(ForeignKey("project_vendor_invoices.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY)                     # invoice currency
    amount_inr: Mapped[Decimal] = mapped_column(MONEY)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    payment_reference: Mapped[str | None] = mapped_column(String(180), nullable=True)
    payment_mode: Mapped[str] = mapped_column(String(40), default="bank_transfer")
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class ProjectCommercialAttachment(Base):
    """One secure-attachment table for estimate documents, expense receipts, vendor and client invoices."""

    __tablename__ = "project_commercial_attachments"
    __table_args__ = (Index("ix_project_commercial_attachments_owner", "owner_type", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    owner_type: Mapped[str] = mapped_column(String(30))     # ESTIMATE_REVISION | EXPENSE | VENDOR_INVOICE | CLIENT_INVOICE
    owner_id: Mapped[int] = mapped_column(Integer)
    doc_type: Mapped[str] = mapped_column(String(30), default="OTHER")   # QUOTATION | PO | WO | APPROVAL | RECEIPT | INVOICE | OTHER
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    mime_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(Integer)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
