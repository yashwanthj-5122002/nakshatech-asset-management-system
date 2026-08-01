from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class DroneAssetCreate(BaseModel):
    asset_name: str = Field(min_length=2, max_length=255)
    category: str = "Other"
    subcategory: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    imported_equipment_id: str | None = None
    quantity: float = Field(default=1, ge=0)
    raw_quantity: str | None = None
    unit_of_measure: str | None = None
    tracking_type: str = "serialized_asset"
    current_status: str = "available"
    working_condition: str | None = None
    current_custodian: str | None = None
    associated_people: list[str] = []
    current_project_id: int | None = None
    current_location: str | None = None
    calibration_required: str | None = None
    maintenance_required: str | None = None
    technical_frequency: str | None = None
    responsible_function: str | None = None
    last_calibration_date: date | None = None
    next_calibration_date: date | None = None
    equipment_tolerance: str | None = None
    remarks: str | None = None
    is_telemetry_capable: bool = False


class DroneAssetUpdate(BaseModel):
    asset_name: str | None = None
    category: str | None = None
    subcategory: str | None = None
    manufacturer: str | None = None
    model_number: str | None = None
    serial_number: str | None = None
    imported_equipment_id: str | None = None
    quantity: float | None = Field(default=None, ge=0)
    unit_of_measure: str | None = None
    current_status: str | None = None
    working_condition: str | None = None
    current_custodian: str | None = None
    associated_people: list[str] | None = None
    current_project_id: int | None = None
    current_location: str | None = None
    calibration_required: str | None = None
    maintenance_required: str | None = None
    technical_frequency: str | None = None
    responsible_function: str | None = None
    last_calibration_date: date | None = None
    next_calibration_date: date | None = None
    equipment_tolerance: str | None = None
    remarks: str | None = None
    is_telemetry_capable: bool | None = None


class DroneProjectCreate(BaseModel):
    project_name: str = Field(min_length=2, max_length=255)
    project_code: str | None = None
    client: str | None = None
    project_manager: str | None = None
    start_date: date | None = None
    expected_end_date: date | None = None
    status: str = "planned"
    financial_year: str | None = None
    location: str | None = None
    project_area: str | None = None
    description: str | None = None
    remarks: str | None = None


class DroneKitCreate(BaseModel):
    kit_name: str = Field(min_length=2, max_length=255)
    kit_tag: str | None = None
    model: str | None = None
    unit_number: str | None = None
    uin: str | None = None
    current_status: str = "available"
    current_custodian: str | None = None
    current_project_id: int | None = None
    current_location: str | None = None
    remarks: str | None = None


class DroneImportCommitRequest(BaseModel):
    allow_warnings: bool = True
    selected_row_ids: list[int] | None = None


class DroneImportPreviewResponse(BaseModel):
    batch_id: int
    batch_code: str
    status: str
    summary: dict[str, Any]
    records: list[dict[str, Any]]
    exceptions: list[dict[str, Any]]


class DroneDashboardResponse(BaseModel):
    kpis: dict[str, int | float]
    category_distribution: list[dict[str, Any]]
    status_distribution: list[dict[str, Any]]
    project_distribution: list[dict[str, Any]]
    recent_assets: list[dict[str, Any]]
    import_quality: dict[str, int]
    telemetry: list[dict[str, Any]]


class DroneSearchResult(BaseModel):
    entity_type: str
    id: int
    primary: str
    secondary: str | None = None
    status: str | None = None
    context: dict[str, Any] = {}


class DroneOperationSelection(BaseModel):
    asset_id: int | None = None
    kit_id: int | None = None
    quantity: float = Field(default=1, gt=0)


class DroneDispatchCreate(BaseModel):
    project_id: int
    custodian: str = Field(min_length=2, max_length=255)
    destination: str = Field(min_length=2, max_length=255)
    dispatch_date: date
    expected_return_date: date | None = None
    purpose: str = Field(min_length=2)
    condition: str = "working"
    approved_by: str | None = None
    remarks: str | None = None
    allow_incomplete_kit: bool = False
    override_reason: str | None = None
    items: list[DroneOperationSelection] = Field(min_length=1)


class DroneAssignmentCreate(BaseModel):
    custodian: str = Field(min_length=2, max_length=255)
    project_id: int | None = None
    location: str = Field(min_length=2, max_length=255)
    assignment_date: date
    expected_return_date: date | None = None
    purpose: str = Field(min_length=2)
    approved_by: str | None = None
    remarks: str | None = None
    items: list[DroneOperationSelection] = Field(min_length=1)


class DroneReturnItem(BaseModel):
    operation_item_id: int
    quantity: float = Field(gt=0)
    condition: str = "working"
    next_status: str = "available"
    remarks: str | None = None


class DroneReturnCreate(BaseModel):
    dispatch_operation_id: int
    return_date: date
    receiver: str | None = None
    return_location: str = Field(min_length=2, max_length=255)
    remarks: str | None = None
    items: list[DroneReturnItem] = Field(min_length=1)


class DroneTransferCreate(BaseModel):
    transfer_date: date
    to_project_id: int | None = None
    to_custodian: str | None = None
    destination: str = Field(min_length=2, max_length=255)
    reason: str = Field(min_length=2)
    approved_by: str | None = None
    remarks: str | None = None
    items: list[DroneOperationSelection] = Field(min_length=1)


class DroneWorkRecordCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    work_type: str = Field(min_length=2, max_length=80)
    project_id: int | None = None
    asset_id: int | None = None
    kit_id: int | None = None
    assigned_to: str | None = None
    technician: str | None = None
    priority: str = "medium"
    status: str = "open"
    approval_status: str = "pending"
    description: str | None = None
    initial_condition: str | None = None
    start_date: date | None = None
    expected_completion_date: date | None = None


class DroneWorkRecordUpdate(BaseModel):
    status: str | None = None
    approval_status: str | None = None
    assigned_to: str | None = None
    technician: str | None = None
    priority: str | None = None
    description: str | None = None
    initial_condition: str | None = None
    resolution: str | None = None
    expected_completion_date: date | None = None
    approved_by: str | None = None


class DroneProjectUpdate(BaseModel):
    project_name: str | None = None
    client: str | None = None
    project_manager: str | None = None
    start_date: date | None = None
    expected_end_date: date | None = None
    actual_completion_date: date | None = None
    closure_date: date | None = None
    status: str | None = None
    financial_year: str | None = None
    location: str | None = None
    project_area: str | None = None
    description: str | None = None
    remarks: str | None = None
