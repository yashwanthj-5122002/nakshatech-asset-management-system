from __future__ import annotations

from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HandoverCreate(BaseModel):
    reporting_month: str | None = None
    asset_id: int | None = None
    device_category: str
    employee_name: str | None = None
    dc_number: str | None = None
    department: str | None = None
    work_mode: str | None = None
    internal_asset_no: str | None = None
    specification: str | None = None
    serial_number: str | None = None
    accessories_provided: str | None = None
    condition: str | None = None
    action_type: str
    return_status: str = "available"
    activity_date: date
    issued_by: str | None = None
    remarks: str | None = None
    asset_updated_status: str | None = None
    apply_to_asset: bool = True

    @field_validator("device_category")
    @classmethod
    def validate_device_category(cls, value: str) -> str:
        value = value.strip().lower()
        if value not in {"laptop", "desktop"}:
            raise ValueError("Device category must be laptop or desktop")
        return value

    @field_validator("action_type")
    @classmethod
    def validate_action_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"handover", "transfer", "return"}:
            raise ValueError("Live custody action must be handover, transfer or return")
        return normalized

    @field_validator("return_status")
    @classmethod
    def validate_return_status(cls, value: str) -> str:
        normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
        if normalized != "available":
            raise ValueError("Live Return always uses Available after inspection")
        return "available"

    @field_validator("work_mode")
    @classmethod
    def validate_work_mode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"office", "wfh", "field"}:
            raise ValueError("Work mode must be office, wfh or field")
        return normalized


class HandoverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_code: str
    asset_id: int | None = None
    asset_code_snapshot: str | None = None
    device_category: str
    employee_name: str | None = None
    from_employee_name: str | None = None
    to_employee_name: str | None = None
    dc_number: str | None = None
    department: str | None = None
    work_mode: str | None = None
    internal_asset_no: str | None = None
    specification: str | None = None
    serial_number: str | None = None
    accessories_provided: str | None = None
    condition: str | None = None
    action_type: str
    action_raw: str | None = None
    activity_date: date
    activity_time: time | None = None
    issued_by: str | None = None
    remarks: str | None = None
    asset_updated_status: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    imported: bool
    performed_by: str | None = None
    performed_by_email: str | None = None
    performed_by_role: str | None = None
    reporting_month: str | None = None
    created_at: datetime


class PurchaseRequestCreate(BaseModel):
    reporting_month: str | None = None
    requesting_department: str = Field(min_length=1)
    requested_employee: str = Field(min_length=1)
    item_type: str
    item_name: str = Field(min_length=1)
    item_description: str | None = None
    quantity: float = Field(default=1, gt=0)
    estimated_unit_price: float | None = Field(default=None, ge=0)
    estimated_total_amount: float | None = Field(default=None, ge=0)
    business_reason: str = Field(min_length=1)
    required_by_date: date | None = None
    priority: str = "medium"
    it_remarks: str | None = None

    @field_validator("item_type")
    @classmethod
    def validate_item_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"hardware", "software", "other"}:
            raise ValueError("Item type must be hardware, software or other")
        return normalized

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"low", "medium", "high", "critical"}:
            raise ValueError("Priority must be low, medium, high or critical")
        return normalized


class PurchaseRequestResubmit(PurchaseRequestCreate):
    pass


class PurchaseRequestDecision(BaseModel):
    action: str
    approved_amount: float | None = Field(default=None, ge=0)
    management_remarks: str | None = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"approve", "reject", "send_back"}:
            raise ValueError("Decision must be approve, reject or send_back")
        return normalized


class PurchaseRequestHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    from_status: str | None = None
    to_status: str
    remarks: str | None = None
    performed_by_name: str
    performed_by_email: str
    performed_by_role: str
    created_at: datetime


class PurchaseRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_code: str
    reporting_month: str | None = None
    requesting_department: str
    requested_employee: str
    item_type: str
    item_name: str
    item_description: str | None = None
    quantity: float
    estimated_unit_price: float | None = None
    estimated_total_amount: float | None = None
    business_reason: str
    required_by_date: date | None = None
    priority: str
    it_remarks: str | None = None
    status: str
    branch: str | None = None
    requested_by_name: str
    requested_by_email: str
    requested_by_role: str
    requested_at: datetime
    approved_amount: float | None = None
    management_remarks: str | None = None
    decided_by_name: str | None = None
    decided_by_email: str | None = None
    decided_by_role: str | None = None
    decided_at: datetime | None = None
    purchase_completed_at: datetime | None = None
    updated_at: datetime
    purchase_record_id: int | None = None
    purchase_code: str | None = None
    actual_purchase_amount: float | None = None
    purchase_date: date | None = None
    histories: list[PurchaseRequestHistoryResponse] = Field(default_factory=list)


class PurchaseCreate(BaseModel):
    reporting_month: str | None = None
    purchase_request_id: int | None = None
    purchase_request_code: str | None = None
    linked_asset_id: int | None = None
    purchase_date: date
    po_number: str | None = None
    asset_number: str | None = None
    supplier_name: str = Field(min_length=1)
    supplier_contact: str | None = None
    item_description: str = Field(min_length=1)
    warranty_number: str | None = None
    quantity: float = Field(default=1, gt=0)
    unit_price: float | None = Field(default=None, ge=0)
    total_price: float | None = Field(default=None, ge=0)
    received_date: date | None = None
    inspection_status: str | None = None
    approved_by: str | None = None
    department: str | None = None
    remarks: str | None = None


class PurchaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    purchase_code: str
    purchase_request_id: int | None = None
    linked_asset_id: int | None = None
    linked_asset_code_snapshot: str | None = None
    purchase_date: date
    po_number: str | None = None
    asset_number: str | None = None
    supplier_name: str
    supplier_contact: str | None = None
    item_description: str
    warranty_number: str | None = None
    quantity: float
    unit_price: float | None = None
    total_price: float | None = None
    received_date: date | None = None
    inspection_status: str | None = None
    approved_by: str | None = None
    department: str | None = None
    remarks: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    imported: bool
    created_by: str | None = None
    created_by_email: str | None = None
    created_by_role: str | None = None
    reporting_month: str | None = None
    created_at: datetime
