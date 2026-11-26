"""Client advance payment tracking (Finance V8 Phase 1).

SCOPE AND SAFETY BOUNDARY
-------------------------
This module tracks money received from the CLIENT before billing. It is deliberately
separate from the existing employee expense-advance ledger (``ExpenseClaim.claim_type``
values ``advance`` / ``additional_advance``), which is money paid TO staff for field work.
The two concepts never share tables, and every object here is prefixed ``client_advance_``.

HARD RULES (Phase 1 frozen contract)
------------------------------------
1. Nothing in this module contributes to the Sales figure.
2. Nothing in this module contributes to the Revenue figure.
3. Invoice commercial value is never modified here.
4. An advance is only ever ADJUSTED during billing/payment settlement.
5. The Finance Command Center KPI reconciliation must stay unchanged.

Consequently the columns added to ``project_commercial_estimate_revisions`` are stored as
INPUT ONLY. They are intentionally NOT projected into the existing KPI payload keys
(``sales_inr`` / ``gross_inr`` / ``open_sales_inr`` / outstanding / payment-pending /
partial-payment). They are surfaced later under a separate ``advance`` block.

Currency
--------
Each receipt records its original currency, receipt-date FX rate, and INR equivalent.
Those values belong only to the isolated client-advance ledger; they never alter the
commercial revision, invoice value, Sales, Revenue, or Outstanding calculations.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now

MONEY = Numeric(18, 2)
PERCENT = Numeric(6, 2)

# ---------------------------------------------------------------------------
# Enumerations (kept as plain strings to match the existing schema style)
# ---------------------------------------------------------------------------

# Structured payment arrangement agreed with the client. Stored beside the free-text
# ``payment_terms`` narrative so Finance can filter without losing BD's wording.
ADVANCE_PAYMENT_TYPES = {
    "full_advance": "Full Advance",
    "percentage_advance": "Percentage Advance",
    "fixed_advance": "Fixed Advance",
    "milestone_advance": "Milestone Payment",
    "no_advance": "No Advance",
}

# Derived, never stored. Precedence is evaluated top-down; first match wins.
ADVANCE_STATUSES = (
    "not_required",
    "requested",
    "pending",
    "partial_received",
    "received",
    "overdue",
    "adjusted",
    "closed",
)

ADVANCE_STATUS_LABELS = {
    "not_required": "Not Required",
    "requested": "Requested",
    "pending": "Pending",
    "partial_received": "Partial Received",
    "received": "Received",
    "overdue": "Overdue",
    "adjusted": "Adjusted",
    "closed": "Closed",
}

# How the money physically arrived.
ADVANCE_PAYMENT_MODES = (
    "bank_transfer",
    "neft",
    "rtgs",
    "imps",
    "cheque",
    "demand_draft",
    "upi",
    "other",
)

# Follow-up communication channel.
ADVANCE_FOLLOWUP_CHANNELS = (
    "email",
    "phone",
    "meeting",
    "whatsapp",
    "letter",
    "portal",
    "other",
)

__all__ = [
    "ADVANCE_PAYMENT_TYPES",
    "ADVANCE_STATUSES",
    "ADVANCE_STATUS_LABELS",
    "ADVANCE_PAYMENT_MODES",
    "ADVANCE_FOLLOWUP_CHANNELS",
    "ClientAdvanceTransaction",
    "ClientAdvanceFollowUp",
    "ClientAdvanceStatusHistory",
]


class ClientAdvanceTransaction(Base):
    """One actual advance receipt from the client.

    A project may receive several advance instalments, so the received total is always
    the sum of these rows and is never stored as a mutable running balance.
    """

    __tablename__ = "client_advance_transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_clients.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    # The commercial revision whose terms this receipt satisfies. Nullable so a receipt
    # that arrives before the revision exists is never lost.
    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_estimate_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Optional milestone linkage; reuses the existing approved milestone schedule.
    milestone_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_milestones.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    sequence: Mapped[int] = mapped_column(Integer, default=1)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(String(3), index=True)
    amount_inr: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    payment_date: Mapped[date] = mapped_column(Date, index=True)
    payment_mode: Mapped[str] = mapped_column(String(30), default="bank_transfer", index=True)
    reference_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    bank_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    instrument_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    attachment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Settlement metadata is deliberately isolated from ProjectInvoicePayment. A later
    # billing/settlement phase may populate it without changing invoice calculations.
    adjusted_amount_inr: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    # Plain integer by design: lifecycle invoice tables may load after Finance models,
    # matching the existing commercial-to-invoice compatibility pattern.
    adjusted_invoice_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    adjusted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Recorded by Finance. ``verified_*`` is the optional second-person confirmation.
    recorded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_reversed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    reversal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "sequence", name="uq_client_advance_transaction_sequence"
        ),
    )


class ClientAdvanceFollowUp(Base):
    """A documented chase for an expected advance that has not arrived yet."""

    __tablename__ = "client_advance_followups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True
    )
    client_id: Mapped[int | None] = mapped_column(
        ForeignKey("finance_clients.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_estimate_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    contact_person: Mapped[str | None] = mapped_column(String(255), nullable=True)
    communication_type: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_date: Mapped[date] = mapped_column(Date, index=True)
    next_followup_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    contact_person_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    contact_person_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Finance's promise-to-pay date. Feeds the Overdue rule at read time.
    promised_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    escalated_to_management: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    __table_args__ = (Index("ix_client_advance_followups_project_date", "project_id", "followup_date"),)


class ClientAdvanceStatusHistory(Base):
    """Append-only record of advance status transitions (audit trail).

    Written explicitly when a status transition is observed. Status itself remains
    derived, so this table is evidence of movement, never the source of truth.
    """

    __tablename__ = "client_advance_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True
    )
    revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_commercial_estimate_revisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    old_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    new_status: Mapped[str] = mapped_column(String(30), index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_source: Mapped[str] = mapped_column(String(40), default="manual", index=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
