from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


ReturnMode = Literal["complete_return", "return_without_monitor"]


class AssetVendorReturnCreate(BaseModel):
    return_mode: ReturnMode
    return_date: date
    vendor_name: str = Field(min_length=2, max_length=255)
    return_reference: str | None = Field(default=None, max_length=160)
    condition: str | None = Field(default=None, max_length=160)
    reason: str = Field(min_length=2)
    remarks: str | None = None
    reporting_month: str | None = None
    spare_location: str | None = Field(default="IT Store", max_length=180)
    confirm_vendor_return: bool = False

    @field_validator(
        "vendor_name",
        "return_reference",
        "condition",
        "reason",
        "remarks",
        "reporting_month",
        "spare_location",
        mode="before",
    )
    @classmethod
    def clean_text(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @model_validator(mode="after")
    def validate_return(self):
        if self.return_mode == "return_without_monitor" and not self.spare_location:
            raise ValueError("Spare monitor location is required when retaining the monitor")
        if not self.confirm_vendor_return:
            raise ValueError("Confirm that this is a rental/vendor asset being physically returned")
        return self
