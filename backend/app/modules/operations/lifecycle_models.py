from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
    # Null when BD records an offline/manual client outcome that never arrived
    # through a portal feedback request (V8.1 BD Feedback Action Center).
    feedback_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_feedback_requests.id", ondelete="CASCADE"), index=True
    )
    response_type: Mapped[str] = mapped_column(String(40), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    correction_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    # 'client_portal' (client submitted via the secure link) or 'bd_manual'
    # (BD recorded an offline client response: call, email or letter).
    source: Mapped[str | None] = mapped_column(String(20), default="client_portal")
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

    # Commercial / FX snapshot (additive). ``amount`` stays the revenue-before-tax value in the invoice
    # currency; the *_inr columns are the accounting values at the invoice date's own FX rate. Legacy rows
    # keep NULLs, which readers treat as "FX not recorded" (INR invoices resolve at rate 1).
    tax_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    fx_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fx_rate_to_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fx_rate_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fx_rate_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    base_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    tax_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    fx_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    po_wo_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    # Traceability to the approved commercial basis and PM billing basis this invoice was prepared from
    # (additive, nullable; plain integers so lifecycle tables never depend on the commercial tables' load order).
    estimate_revision_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    billing_basis_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    billed_quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    billed_milestone_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # --- Invoice Generation V2 (additive) ------------------------------------------------
    # GST breakdown. ``tax_amount`` above stays the single authoritative tax figure every
    # existing Sales/Revenue/Outstanding/settlement reader already sums into the invoice
    # total; these three pairs are a presentation breakdown of that same figure and must
    # always reconcile to it (cgst_amount + sgst_amount + igst_amount == tax_amount).
    # NULL on every legacy invoice, which keeps rendering the old single combined tax line.
    cgst_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    cgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    sgst_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    sgst_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    igst_percent: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    igst_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)

    # Work order / dispatch / place-of-supply fields used by the A4 tax invoice header.
    work_order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dispatch_details: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dispatch_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(160), nullable=True)

    # 'auto_fill' | 'manual' | NULL (legacy, predates Invoice Generation V2).
    entry_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Point-in-time billing/company/bank snapshot captured when the invoice is created, so a
    # later Client Master or company-configuration edit never silently changes an already
    # issued document. Shape: {"billing": {...}, "company": {...}, "bank": {...}}. NULL on
    # legacy invoices, which fall back to the live Client Master / app configuration exactly
    # as they do today.
    document_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # --- V8.7 invoice presentation theme + authorised signature (ADDITIVE) ---------------
    # ``theme`` selects ONE of the three A4 designs rendered from the SAME normalized
    # invoice payload: 'blue_classic' | 'blue_topographic' | 'green_gold_premium'.
    # NULL on legacy invoices, which render as 'blue_classic' (the historical design).
    theme: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    # Visual/approval signature (authorised signatory + company stamp). This is NOT a
    # statutory cryptographic DSC signature.
    signed: Mapped[bool] = mapped_column(Boolean, default=False)
    signed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    # Set when a material edit invalidates a previous signature (the sign-off no longer
    # represents the new content). The old signed_at/signed_by stay for audit.
    signature_invalidated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ProjectInvoiceLineItem(Base):
    """Invoice Generation V2 line items (additive; ``ProjectInvoice.amount`` stays authoritative).

    A legacy invoice (raised before this table existed) has zero rows here; the document
    renderer falls back to one synthetic line built from ``ProjectInvoice.amount``, exactly
    as it always has. Only once Finance enters 1..N real line items here does the rendered
    document switch to showing them individually. ``sum(amount for each row) == invoice.amount``
    is enforced by the service layer before the invoice is ever created.
    """

    __tablename__ = "project_invoice_line_items"
    __table_args__ = (
        UniqueConstraint("invoice_id", "sequence", name="uq_project_invoice_line_item_sequence"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("project_invoices.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text)
    hsn_sac: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit: Mapped[str] = mapped_column(String(30), default="Nos")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


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

    # Realization FX (additive). ``amount`` is applied against the invoice in the invoice currency; these
    # columns record what that payment realised in INR at the payment's OWN rate, never the invoice rate.
    payment_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    fx_snapshot_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fx_rate_to_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    fx_rate_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fx_rate_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    fx_rate_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    inr_equivalent: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    invoice_inr_equivalent: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    fx_gain_loss_inr: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)


class ProjectInvoiceBadDebt(Base):
    """Auditable disposition for an unpaid invoice balance.

    Payments remain actual cash/settlement rows in ``project_invoice_payments``.
    A bad-debt approval never manufactures a payment and never turns the
    written-off amount into realized Revenue. One current disposition row per
    invoice is sufficient; a rejected proposal can be resubmitted by updating
    the same audit record while preserving proposal/review timestamps.
    """

    __tablename__ = "project_invoice_bad_debts"
    __table_args__ = (
        UniqueConstraint("invoice_id", name="uq_project_invoice_bad_debt_invoice"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("project_invoices.id", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="PROPOSED", index=True)
    proposed_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    approved_amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    recovered_amount: Mapped[Decimal] = mapped_column(Numeric(16, 2), default=Decimal("0.00"))
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    reason: Mapped[str] = mapped_column(Text)
    collection_attempts: Mapped[str] = mapped_column(Text)
    last_followup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    finance_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    proposed_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectInvoiceBadDebtApproval(Base):
    """Append-only management decision for one Bad Debt case (DUAL approval).

    NakshaTech requires BOTH management approvers (Vinod Sir and Chethan) to
    approve a write-off before it becomes financially effective. Each decision is
    its own immutable row, so approval history is never overwritten, a repeated or
    concurrent click cannot duplicate the effect, and a re-proposal starts a fresh
    approval cycle (approvals are scoped by ``decided_at >= proposed_at``).
    """

    __tablename__ = "project_invoice_bad_debt_approvals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bad_debt_id: Mapped[int] = mapped_column(
        ForeignKey("project_invoice_bad_debts.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("project_invoices.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    # 'vinod' | 'chethan' — resolved from the authorized management account email.
    approver_key: Mapped[str] = mapped_column(String(20), index=True)
    approver_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    approver_email: Mapped[str] = mapped_column(String(255))
    decision: Mapped[str] = mapped_column(String(20))  # approved | rejected
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


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
