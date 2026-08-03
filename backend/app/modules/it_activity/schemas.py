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


class HandoverResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_code: str
    asset_id: int | None = None
    asset_code_snapshot: str | None = None
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


class PurchaseCreate(BaseModel):
    reporting_month: str | None = None
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
