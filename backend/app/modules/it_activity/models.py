from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import Asset, utc_now


class ITHandoverRecord(Base):
    __tablename__ = "it_handover_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    asset_code_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    device_category: Mapped[str] = mapped_column(String(30), index=True)
    employee_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dc_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    work_mode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    internal_asset_no: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    accessories_provided: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(160), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), index=True)
    action_raw: Mapped[str | None] = mapped_column(String(255), nullable=True)
    activity_date: Mapped[date] = mapped_column(Date, index=True)
    activity_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    issued_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_updated_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    imported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    asset: Mapped[Asset | None] = relationship()


class ITPurchaseRecord(Base):
    __tablename__ = "it_purchase_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    purchase_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    linked_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    linked_asset_code_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    purchase_date: Mapped[date] = mapped_column(Date, index=True)
    po_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    asset_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    supplier_name: Mapped[str] = mapped_column(String(255), index=True)
    supplier_contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    item_description: Mapped[str] = mapped_column(Text)
    warranty_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    received_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    inspection_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_key: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    imported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    linked_asset: Mapped[Asset | None] = relationship()
