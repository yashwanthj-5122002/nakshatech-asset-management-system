"""Isolated Finance-only invoice documents with no project/accounting linkage."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class StandaloneInvoice(Base):
    __tablename__ = "standalone_invoices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    invoice_date: Mapped[date] = mapped_column(Date, index=True)
    terms: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    reference_work_order: Mapped[str | None] = mapped_column(String(160), nullable=True)
    place_of_supply: Mapped[str | None] = mapped_column(String(160), nullable=True)

    seller_snapshot: Mapped[dict] = mapped_column(JSON)
    bill_to_snapshot: Mapped[dict] = mapped_column(JSON)
    ship_to_snapshot: Mapped[dict] = mapped_column(JSON)
    bank_snapshot: Mapped[dict] = mapped_column(JSON)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    terms_conditions: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_mode: Mapped[str] = mapped_column(String(20), default="none")
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cgst_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    sgst_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    igst_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    total: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    balance_due: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    amount_in_words: Mapped[str] = mapped_column(String(500))
    authorized_signatory_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qr_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    line_items: Mapped[list["StandaloneInvoiceLineItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="StandaloneInvoiceLineItem.sequence"
    )


class StandaloneInvoiceLineItem(Base):
    __tablename__ = "standalone_invoice_line_items"
    __table_args__ = (UniqueConstraint("standalone_invoice_id", "sequence", name="uq_standalone_invoice_line_sequence"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    standalone_invoice_id: Mapped[int] = mapped_column(
        ForeignKey("standalone_invoices.id", ondelete="CASCADE"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(500))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    hsn_sac: Mapped[str | None] = mapped_column(String(30), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    unit: Mapped[str] = mapped_column(String(30))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    tax_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0.00"))
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    invoice: Mapped[StandaloneInvoice] = relationship(back_populates="line_items")
