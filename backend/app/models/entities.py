from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utc_now() -> datetime:
    """Return a naive UTC timestamp for database columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), index=True)
    branch: Mapped[str] = mapped_column(String(120), default="Head Office")
    employee_id: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    designation: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    account_status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_logout_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    source_sheet: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    used_by: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    workstation_no: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    cpu_asset_tag: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    monitor_asset_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    mouse_asset_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    keyboard_asset_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    system_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    brand: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    connection_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capacity: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ownership: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    current_holder: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    device_type: Mapped[str] = mapped_column(String(80), index=True)
    processor: Mapped[str | None] = mapped_column(String(180), nullable=True)
    memory_gb: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ssd: Mapped[str | None] = mapped_column(String(120), nullable=True)
    hdd: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    mac_address: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    graphics_card: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operating_system: Mapped[str | None] = mapped_column(String(120), nullable=True)
    antivirus: Mapped[str | None] = mapped_column(String(80), nullable=True)
    network_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    asset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_asset_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    work_mode: Mapped[str] = mapped_column(String(50), default="office", index=True)
    status: Mapped[str] = mapped_column(String(50), default="available", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    work_records: Mapped[list[WorkRecord]] = relationship(back_populates="asset")
    outgoing_replacements: Mapped[list[ReplacementRecord]] = relationship(
        foreign_keys="ReplacementRecord.old_asset_id", back_populates="old_asset"
    )
    incoming_replacements: Mapped[list[ReplacementRecord]] = relationship(
        foreign_keys="ReplacementRecord.new_asset_id", back_populates="new_asset"
    )


class WorkRecord(Base):
    __tablename__ = "work_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    module: Mapped[str] = mapped_column(String(50), index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255))
    work_type: Mapped[str] = mapped_column(String(120), default="General")
    project: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    technician: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium")
    issue_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="open", index=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaced_component: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replacement_asset_tag: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="not_required")
    submitted_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    submitted_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submitted_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approved_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    approval_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    asset: Mapped[Asset | None] = relationship(back_populates="work_records")


class ComponentReplacement(Base):
    __tablename__ = "component_replacements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    replacement_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    work_record_id: Mapped[int | None] = mapped_column(ForeignKey("work_records.id"), nullable=True, index=True)
    cpu_asset_tag: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    workstation_no: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    component_type: Mapped[str] = mapped_column(String(120), index=True)
    change_type: Mapped[str] = mapped_column(String(40), default="replacement", index=True)
    batch_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    sequence_no: Mapped[int] = mapped_column(Integer, default=1)
    field_name: Mapped[str] = mapped_column(String(120))
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    old_condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    technician: Mapped[str | None] = mapped_column(String(255), nullable=True)
    replacement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    performed_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    asset: Mapped[Asset] = relationship()
    work_record: Mapped[WorkRecord | None] = relationship()


class MonthlySnapshotRun(Base):
    __tablename__ = "monthly_snapshot_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    month_start: Mapped[date] = mapped_column(Date, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), default="finalized", index=True)
    source: Mapped[str] = mapped_column(String(50), default="automatic")
    opening_count: Mapped[int] = mapped_column(Integer, default=0)
    closing_count: Mapped[int] = mapped_column(Integer, default=0)
    finalized_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    finalized_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    assets: Mapped[list[MonthlyAssetSnapshot]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class MonthlyAssetSnapshot(Base):
    __tablename__ = "monthly_asset_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("monthly_snapshot_runs.id"), index=True)
    asset_code: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped[MonthlySnapshotRun] = relationship(back_populates="assets")


class ReplacementRecord(Base):
    __tablename__ = "replacement_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    replacement_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    old_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    new_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True, index=True)
    reason: Mapped[str] = mapped_column(Text)
    damage_category: Mapped[str] = mapped_column(String(100), default="technical_failure")
    inspection_finding: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    final_action: Mapped[str] = mapped_column(String(80), default="replacement_pending")
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    requested_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    decision_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    old_asset: Mapped[Asset] = relationship(foreign_keys=[old_asset_id], back_populates="outgoing_replacements")
    new_asset: Mapped[Asset | None] = relationship(foreign_keys=[new_asset_id], back_populates="incoming_replacements")


class ApprovalDecisionHistory(Base):
    __tablename__ = "approval_decision_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workflow_type: Mapped[str] = mapped_column(String(50), index=True)
    record_id: Mapped[int] = mapped_column(Integer, index=True)
    record_code: Mapped[str] = mapped_column(String(80), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    from_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_status: Mapped[str] = mapped_column(String(50), index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    performed_by_name: Mapped[str] = mapped_column(String(255))
    performed_by_email: Mapped[str] = mapped_column(String(255), index=True)
    performed_by_role: Mapped[str] = mapped_column(String(30), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class AssetHistory(Base):
    __tablename__ = "asset_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    action: Mapped[str] = mapped_column(String(120))
    change_type: Mapped[str] = mapped_column(String(60), default="asset_activity", index=True)
    batch_code: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    changed_by_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    field_count: Mapped[int] = mapped_column(Integer, default=0)
    reporting_month: Mapped[str | None] = mapped_column(String(7), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class Drone(Base):
    __tablename__ = "drones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    model: Mapped[str] = mapped_column(String(255))
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pilot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="available")
    battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    survey_asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    locations: Mapped[list[DroneLocation]] = relationship(back_populates="drone", cascade="all, delete-orphan")


class DroneLocation(Base):
    __tablename__ = "drone_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    drone_id: Mapped[int] = mapped_column(ForeignKey("drones.id", ondelete="CASCADE"), index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    altitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    speed: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    drone: Mapped[Drone] = relationship(back_populates="locations")
