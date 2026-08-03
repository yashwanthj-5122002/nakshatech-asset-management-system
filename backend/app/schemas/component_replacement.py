from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ChangeType = Literal["upgrade", "replacement", "downgrade", "upgrade_replacement"]


class ComponentReplacementCreate(BaseModel):
    reporting_month: str | None = None
    asset_id: int
    component_type: str = Field(min_length=2)
    change_type: ChangeType = "replacement"
    old_value: str | None = None
    new_value: str = Field(min_length=1)
    reason: str = Field(min_length=2)
    old_condition: str | None = None
    technician: str | None = None
    replacement_date: date | None = None
    approved_by: str | None = None
    remarks: str | None = None

    @field_validator(
        "component_type", "old_value", "new_value", "reason", "old_condition",
        "technician", "approved_by", "remarks", mode="before"
    )
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ComponentChangeItem(BaseModel):
    component_type: str = Field(min_length=2)
    change_type: ChangeType | None = None
    old_value: str | None = None
    new_value: str = Field(min_length=1)
    reason: str = Field(min_length=2)
    old_condition: str | None = None

    @field_validator("component_type", "old_value", "new_value", "reason", "old_condition", mode="before")
    @classmethod
    def clean_item_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ComponentChangeBatchCreate(BaseModel):
    reporting_month: str | None = None
    asset_id: int
    change_type: ChangeType
    items: list[ComponentChangeItem] = Field(min_length=1, max_length=25)
    technician: str | None = None
    replacement_date: date | None = None
    approved_by: str | None = None
    remarks: str | None = None

    @field_validator("technician", "approved_by", "remarks", mode="before")
    @classmethod
    def clean_batch_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def validate_item_actions(self):
        if self.change_type == "upgrade_replacement":
            for item in self.items:
                if item.change_type is None:
                    raise ValueError("Select Upgrade or Replacement for every component when using Upgrade + Replacement")
        return self


class ComponentReplacementResponse(BaseModel):
    id: int
    replacement_code: str
    batch_code: str | None = None
    sequence_no: int = 1
    asset_id: int
    asset_code: str
    cpu_asset_tag: str | None = None
    workstation_no: str | None = None
    component_type: str
    change_type: str = "replacement"
    field_name: str
    old_value: str | None = None
    new_value: str
    reason: str
    old_condition: str | None = None
    technician: str | None = None
    replacement_date: date | None = None
    performed_by: str | None = None
    performed_by_email: str | None = None
    performed_by_role: str | None = None
    approved_by: str | None = None
    remarks: str | None = None
    work_record_id: int | None = None
    work_code: str | None = None
    reporting_month: str | None = None
    created_at: datetime


class ComponentChangeBatchResponse(BaseModel):
    batch_code: str
    work_code: str
    asset_id: int
    asset_code: str
    cpu_asset_tag: str | None = None
    workstation_no: str | None = None
    change_type: str
    records: list[ComponentReplacementResponse]
