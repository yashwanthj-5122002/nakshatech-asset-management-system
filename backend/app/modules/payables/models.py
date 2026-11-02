"""Additive tables only; independent from existing finance/expense tables."""
from __future__ import annotations

from datetime import date, datetime
from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import utc_now


class Payable(Base):
    __tablename__ = 'payables'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    origin: Mapped[str] = mapped_column(String(16), index=True)  # admin | finance
    raised_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    bill_name: Mapped[str] = mapped_column(String(220))
    bill_number: Mapped[str] = mapped_column(String(120))
    bill_category: Mapped[str] = mapped_column(String(100))
    vendor_name: Mapped[str] = mapped_column(String(220))
    vendor_gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    bill_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    billing_period: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cost_center: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_paise: Mapped[int] = mapped_column(BigInteger)
    gst_rate_bps: Mapped[int] = mapped_column(Integer)  # percentage*100; 18% -> 1800
    gst_paise: Mapped[int] = mapped_column(BigInteger)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    paid_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    priority: Mapped[str] = mapped_column(String(16), default='normal')
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default='draft', index=True)
    approval_version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('origin', 'vendor_name', 'bill_number', name='uq_payables_vendor_bill'),)


class PayableApproval(Base):
    __tablename__ = 'payable_approvals'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey('payables.id', ondelete='CASCADE'), index=True)
    approval_version: Mapped[int] = mapped_column(Integer)
    manager_email: Mapped[str] = mapped_column(String(255))
    manager_user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    decision: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint('payable_id', 'approval_version', 'manager_email', name='uq_payable_manager_version'),)


class PayablePayment(Base):
    __tablename__ = 'payable_payments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey('payables.id', ondelete='CASCADE'), index=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    payment_date: Mapped[date] = mapped_column(Date)
    payment_method: Mapped[str] = mapped_column(String(40))
    reference: Mapped[str] = mapped_column(String(120))
    recorded_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    __table_args__ = (UniqueConstraint('payable_id', 'reference', name='uq_payable_payment_reference'),)


class PayableDocument(Base):
    __tablename__ = 'payable_documents'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey('payables.id', ondelete='CASCADE'), index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey('payable_payments.id', ondelete='CASCADE'), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))  # bill | challan
    filename: Mapped[str] = mapped_column(String(180))
    media_type: Mapped[str] = mapped_column(String(80))
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class PayableAudit(Base):
    __tablename__ = 'payable_audit'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    payable_id: Mapped[int] = mapped_column(ForeignKey('payables.id', ondelete='CASCADE'), index=True)
    action: Mapped[str] = mapped_column(String(60))
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    details: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
