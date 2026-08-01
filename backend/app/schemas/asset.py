from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class AssetFields(BaseModel):
    used_by: str | None = None
    workstation_no: str | None = None
    department: str | None = None
    cpu_asset_tag: str | None = None
    monitor_asset_tags: str | None = None
    mouse_asset_tag: str | None = None
    keyboard_asset_tag: str | None = None
    system_name: str | None = None
    device_type: str = "Computer"
    processor: str | None = None
    memory_gb: str | None = None
    ssd: str | None = None
    hdd: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    graphics_card: str | None = None
    operating_system: str | None = None
    antivirus: str | None = None
    network_type: str | None = None
    performed_by: str | None = None
    approved_by: str | None = None
    price: float | None = Field(default=None, ge=0)
    remarks: str | None = None
    asset_date: date | None = None
    location: str | None = None
    work_mode: str = "office"
    status: str = "available"

    @field_validator(
        "used_by", "workstation_no", "department", "cpu_asset_tag", "monitor_asset_tags",
        "mouse_asset_tag", "keyboard_asset_tag", "system_name", "processor", "memory_gb",
        "ssd", "hdd", "ip_address", "mac_address", "graphics_card", "operating_system",
        "antivirus", "network_type", "performed_by", "approved_by", "remarks", "location",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class AssetCreate(AssetFields):
    pass


class AssetUpdate(BaseModel):
    used_by: str | None = None
    workstation_no: str | None = None
    department: str | None = None
    cpu_asset_tag: str | None = None
    monitor_asset_tags: str | None = None
    mouse_asset_tag: str | None = None
    keyboard_asset_tag: str | None = None
    system_name: str | None = None
    device_type: str | None = None
    processor: str | None = None
    memory_gb: str | None = None
    ssd: str | None = None
    hdd: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    graphics_card: str | None = None
    operating_system: str | None = None
    antivirus: str | None = None
    network_type: str | None = None
    approved_by: str | None = None
    price: float | None = Field(default=None, ge=0)
    remarks: str | None = None
    asset_date: date | None = None
    location: str | None = None
    work_mode: str | None = None
    status: str | None = None

    @field_validator(
        "used_by", "workstation_no", "department", "cpu_asset_tag", "monitor_asset_tags",
        "mouse_asset_tag", "keyboard_asset_tag", "system_name", "processor", "memory_gb",
        "ssd", "hdd", "ip_address", "mac_address", "graphics_card", "operating_system",
        "antivirus", "network_type", "approved_by", "remarks", "location",
        mode="before",
    )
    @classmethod
    def clean_optional_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class AssetStatusUpdate(BaseModel):
    status: str
    remarks: str | None = None


class AssetAssignment(BaseModel):
    used_by: str = Field(min_length=2)
    department: str = Field(min_length=1)
    workstation_no: str | None = None
    location: str | None = None
    work_mode: str = "office"
    assigned_date: date | None = None
    remarks: str | None = None


class AssetReturn(BaseModel):
    final_status: str = "available"
    return_date: date | None = None
    condition: str = "working"
    all_components_returned: bool = True
    remarks: str | None = None


class AssetResponse(AssetFields):
    id: int
    asset_code: str
    source_sheet: str | None = None
    source_row: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
