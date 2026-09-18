from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


TechnicalDepartmentCode = Literal["ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"]


class TechnicalSampleRequestCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    instructions: str = Field(min_length=5, max_length=10000)
    department_codes: list[TechnicalDepartmentCode] = Field(min_length=1, max_length=6)
    due_date: date | None = None

    @field_validator("department_codes")
    @classmethod
    def unique_departments(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Each technical department can be selected only once")
        return value


class TechnicalSampleSubmit(BaseModel):
    sample_reference: str = Field(min_length=3, max_length=1000)
    notes: str | None = Field(default=None, max_length=5000)


class TechnicalSampleClientDecision(BaseModel):
    decision: Literal["approved", "revision"]
    feedback: str | None = Field(default=None, max_length=5000)
    revision_department_codes: list[TechnicalDepartmentCode] = Field(default_factory=list, max_length=6)

    @field_validator("revision_department_codes")
    @classmethod
    def unique_revision_departments(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("A revision department can appear only once")
        return value

    @model_validator(mode="after")
    def validate_revision_selection(self):
        if self.decision == "revision" and not self.revision_department_codes:
            raise ValueError("Select at least one department when the client requests a revision")
        if self.decision == "approved" and self.revision_department_codes:
            raise ValueError("Revision departments are not used for an approved client decision")
        return self
