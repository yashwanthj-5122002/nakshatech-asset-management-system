from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class DroneAssetAttributeDefinition(Base):
    __tablename__ = "drone_asset_attribute_definitions"
    __table_args__ = (UniqueConstraint("source_sheet", "original_header", name="uq_drone_attribute_header"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_sheet: Mapped[str] = mapped_column(String(160), index=True)
    original_header: Mapped[str] = mapped_column(String(255))
    display_label: Mapped[str] = mapped_column(String(255))
    normalized_field: Mapped[str | None] = mapped_column(String(160), nullable=True)
    data_type: Mapped[str] = mapped_column(String(40), default="text")
    unit: Mapped[str | None] = mapped_column(String(80), nullable=True)
    searchable: Mapped[bool] = mapped_column(Boolean, default=True)
    filterable: Mapped[bool] = mapped_column(Boolean, default=True)
    sortable: Mapped[bool] = mapped_column(Boolean, default=True)
    visible_in_table: Mapped[bool] = mapped_column(Boolean, default=True)
    visible_in_detail: Mapped[bool] = mapped_column(Boolean, default=True)
    included_in_excel: Mapped[bool] = mapped_column(Boolean, default=True)
    dashboard_usage: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DroneProject(Base):
    __tablename__ = "drone_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    project_name: Mapped[str] = mapped_column(String(255), index=True)
    client: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_manager: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closure_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="planned", index=True)
    financial_year: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_area: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DroneAssetKit(Base):
    __tablename__ = "drone_asset_kits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kit_tag: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    kit_name: Mapped[str] = mapped_column(String(255), index=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    uin: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    current_status: Mapped[str] = mapped_column(String(50), default="available", index=True)
    current_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    current_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    current_location: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[DroneProject | None] = relationship()
    components: Mapped[list[DroneKitComponent]] = relationship(back_populates="kit", cascade="all, delete-orphan")


class DroneSurveyAsset(Base):
    __tablename__ = "drone_survey_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    imported_equipment_id: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    asset_name: Mapped[str] = mapped_column(String(255), index=True)
    category: Mapped[str] = mapped_column(String(120), default="Other", index=True)
    subcategory: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    model_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    raw_serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    raw_quantity: Mapped[str | None] = mapped_column(String(120), nullable=True)
    unit_of_measure: Mapped[str | None] = mapped_column(String(80), nullable=True)
    tracking_type: Mapped[str] = mapped_column(String(50), default="serialized_asset", index=True)
    date_of_initial_verification: Mapped[date | None] = mapped_column(Date, nullable=True)
    calibration_required: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    maintenance_required: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    technical_frequency: Mapped[str | None] = mapped_column(String(160), nullable=True)
    responsible_function: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    calibrated_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_calibration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_calibration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    location_of_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location_of_equipment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    equipment_tolerance: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_status: Mapped[str] = mapped_column(String(50), default="available", index=True)
    working_condition: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    current_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    associated_people: Mapped[list | None] = mapped_column(JSON, nullable=True)
    current_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    current_location: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    parent_kit_id: Mapped[int | None] = mapped_column(ForeignKey("drone_asset_kits.id"), nullable=True, index=True)
    is_serialized: Mapped[bool] = mapped_column(Boolean, default=True)
    is_telemetry_capable: Mapped[bool] = mapped_column(Boolean, default=False)
    source_workbook: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("drone_import_batches.id"), nullable=True, index=True)
    original_raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_header_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reconciliation_status: Mapped[str] = mapped_column(String(50), default="approved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[DroneProject | None] = relationship()
    parent_kit: Mapped[DroneAssetKit | None] = relationship()


class DroneKitComponent(Base):
    __tablename__ = "drone_kit_components"
    __table_args__ = (UniqueConstraint("kit_id", "asset_id", name="uq_drone_kit_asset"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kit_id: Mapped[int] = mapped_column(ForeignKey("drone_asset_kits.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("drone_survey_assets.id"), index=True)
    component_name: Mapped[str] = mapped_column(String(255))
    required_quantity: Mapped[float] = mapped_column(Float, default=1)
    is_essential: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    kit: Mapped[DroneAssetKit] = relationship(back_populates="components")
    asset: Mapped[DroneSurveyAsset] = relationship()


class DroneImportBatch(Base):
    __tablename__ = "drone_import_batches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    source_workbook: Mapped[str] = mapped_column(String(255))
    reporting_month: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="preview", index=True)
    summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    rows: Mapped[list[DroneImportRow]] = relationship(back_populates="batch", cascade="all, delete-orphan")
    exceptions: Mapped[list[DroneImportException]] = relationship(back_populates="batch", cascade="all, delete-orphan")


class DroneImportRow(Base):
    __tablename__ = "drone_import_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("drone_import_batches.id"), index=True)
    source_sheet: Mapped[str] = mapped_column(String(160), index=True)
    source_row: Mapped[int] = mapped_column(Integer)
    source_section: Mapped[str | None] = mapped_column(String(255), nullable=True)
    record_type: Mapped[str] = mapped_column(String(60), index=True)
    original_raw_payload: Mapped[dict] = mapped_column(JSON)
    original_header_map: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    normalized_payload: Mapped[dict] = mapped_column(JSON)
    issues: Mapped[list | None] = mapped_column(JSON, nullable=True)
    classification: Mapped[str] = mapped_column(String(50), default="new_record", index=True)
    reconciliation_status: Mapped[str] = mapped_column(String(50), default="pending", index=True)
    created_asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    batch: Mapped[DroneImportBatch] = relationship(back_populates="rows")


class DroneImportException(Base):
    __tablename__ = "drone_import_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("drone_import_batches.id"), index=True)
    row_id: Mapped[int | None] = mapped_column(ForeignKey("drone_import_rows.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(30), default="warning", index=True)
    exception_type: Mapped[str] = mapped_column(String(80), index=True)
    message: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    batch: Mapped[DroneImportBatch] = relationship(back_populates="exceptions")


class DroneUINRegistration(Base):
    __tablename__ = "drone_uin_registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_number: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    category: Mapped[str | None] = mapped_column(String(120), nullable=True)
    uin_status: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    uin: Mapped[str | None] = mapped_column(String(180), nullable=True, index=True)
    uav: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    uav_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    linked_asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    source_sheet: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("drone_import_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DroneHDDDelivery(Base):
    __tablename__ = "drone_hdd_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    ulbs: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    square_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    hdd_serial_number: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    storage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    courier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    courier_details: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(50), default="delivered", index=True)
    linked_asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    source_sheet: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("drone_import_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DroneTelecomConnection(Base):
    __tablename__ = "drone_telecom_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    connection_number: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    device_type: Mapped[str] = mapped_column(String(160), default="Airtel Modem")
    provider: Mapped[str] = mapped_column(String(120), default="Airtel")
    linked_asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True)
    assigned_employee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assigned_project: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_status: Mapped[str] = mapped_column(String(50), default="available")
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(160), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_raw_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(ForeignKey("drone_import_batches.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class DroneAuditLog(Base):
    __tablename__ = "drone_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    entity_type: Mapped[str] = mapped_column(String(80), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class DroneOperation(Base):
    __tablename__ = "drone_operations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operation_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    from_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    to_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    parent_operation_id: Mapped[int | None] = mapped_column(ForeignKey("drone_operations.id"), nullable=True, index=True)
    from_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    destination: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    operation_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    expected_return_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped[DroneProject | None] = relationship(foreign_keys=[project_id])
    from_project: Mapped[DroneProject | None] = relationship(foreign_keys=[from_project_id])
    to_project: Mapped[DroneProject | None] = relationship(foreign_keys=[to_project_id])
    parent_operation: Mapped[DroneOperation | None] = relationship(remote_side=[id])
    items: Mapped[list[DroneOperationItem]] = relationship(back_populates="operation", cascade="all, delete-orphan")


class DroneOperationItem(Base):
    __tablename__ = "drone_operation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("drone_operations.id"), index=True)
    parent_item_id: Mapped[int | None] = mapped_column(ForeignKey("drone_operation_items.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    kit_id: Mapped[int | None] = mapped_column(ForeignKey("drone_asset_kits.id"), nullable=True, index=True)
    source_operation_item_id: Mapped[int | None] = mapped_column(ForeignKey("drone_operation_items.id"), nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    returned_quantity: Mapped[float] = mapped_column(Float, default=0)
    item_status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    operation: Mapped[DroneOperation] = relationship(back_populates="items")
    asset: Mapped[DroneSurveyAsset | None] = relationship(foreign_keys=[asset_id])
    kit: Mapped[DroneAssetKit | None] = relationship(foreign_keys=[kit_id])
    parent_item: Mapped[DroneOperationItem | None] = relationship(
        foreign_keys=[parent_item_id], remote_side=[id], back_populates="child_items"
    )
    child_items: Mapped[list[DroneOperationItem]] = relationship(
        foreign_keys=[parent_item_id], back_populates="parent_item"
    )
    source_operation_item: Mapped[DroneOperationItem | None] = relationship(
        foreign_keys=[source_operation_item_id], remote_side=[id]
    )


class DroneAssetMovement(Base):
    __tablename__ = "drone_asset_movements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    movement_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("drone_operations.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    kit_id: Mapped[int | None] = mapped_column(ForeignKey("drone_asset_kits.id"), nullable=True, index=True)
    movement_type: Mapped[str] = mapped_column(String(40), index=True)
    quantity: Mapped[float] = mapped_column(Float, default=1)
    old_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    new_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    old_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True)
    new_project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True)
    old_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_custodian: Mapped[str | None] = mapped_column(String(255), nullable=True)
    old_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    condition: Mapped[str | None] = mapped_column(String(120), nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    operation: Mapped[DroneOperation | None] = relationship()
    asset: Mapped[DroneSurveyAsset | None] = relationship(foreign_keys=[asset_id])
    kit: Mapped[DroneAssetKit | None] = relationship(foreign_keys=[kit_id])
    old_project: Mapped[DroneProject | None] = relationship(foreign_keys=[old_project_id])
    new_project: Mapped[DroneProject | None] = relationship(foreign_keys=[new_project_id])


class DroneWorkRecord(Base):
    __tablename__ = "drone_work_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    work_type: Mapped[str] = mapped_column(String(80), index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("drone_projects.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("drone_survey_assets.id"), nullable=True, index=True)
    kit_id: Mapped[int | None] = mapped_column(ForeignKey("drone_asset_kits.id"), nullable=True, index=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("drone_operations.id"), nullable=True, index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    technician: Mapped[str | None] = mapped_column(String(255), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    approval_status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_condition: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    performed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    project: Mapped[DroneProject | None] = relationship()
    asset: Mapped[DroneSurveyAsset | None] = relationship()
    kit: Mapped[DroneAssetKit | None] = relationship()
    operation: Mapped[DroneOperation | None] = relationship()
