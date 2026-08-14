from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class AssetVendorReturn(Base):
    """Immutable audit record for an asset returned to a rental/vendor source.

    The source Asset row is intentionally preserved so historical work, custody,
    replacement and audit records never lose their foreign-key target. Active
    inventory views exclude assets whose live status is ``returned_to_vendor``.
    """

    __tablename__ = "asset_vendor_returns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    return_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), unique=True, index=True)
    asset_code_snapshot: Mapped[str] = mapped_column(String(100), index=True)
    cpu_asset_tag_snapshot: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    device_type_snapshot: Mapped[str] = mapped_column(String(80), index=True)
    return_mode: Mapped[str] = mapped_column(String(40), index=True)
    return_date: Mapped[date] = mapped_column(Date, index=True)
    vendor_name: Mapped[str] = mapped_column(String(255), index=True)
    return_reference: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    condition: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    previous_used_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    previous_department: Mapped[str | None] = mapped_column(String(160), nullable=True)
    previous_workstation_no: Mapped[str | None] = mapped_column(String(120), nullable=True)
    monitor_tags_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    retained_monitor_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_snapshot_json: Mapped[str] = mapped_column(Text)
    performed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    performed_by_name: Mapped[str] = mapped_column(String(255))
    performed_by_email: Mapped[str] = mapped_column(String(255), index=True)
    performed_by_role: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class SpareMonitor(Base):
    """Monitor retained by NakshaTech after a rental desktop is returned.

    This is a component pool, not a primary IT Asset. A retained monitor can be
    consumed later by the existing Component Changes workflow.
    """

    __tablename__ = "spare_monitors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    monitor_tag: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    source_return_id: Mapped[int] = mapped_column(ForeignKey("asset_vendor_returns.id"), index=True)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    source_asset_code: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), default="available", index=True)
    current_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    location: Mapped[str] = mapped_column(String(180), default="IT Store", index=True)
    retained_date: Mapped[date] = mapped_column(Date, index=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    assigned_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
