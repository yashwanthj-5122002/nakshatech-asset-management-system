from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Severity = Literal["high", "medium", "low", "info"]


class DataQualityMonth(BaseModel):
    key: str
    label: str
    source: str
    status: str
    is_live: bool
    data_available: bool


class DataQualityRecord(BaseModel):
    record_type: str
    record_id: str
    asset_code: str | None = None
    device_type: str | None = None
    status: str | None = None
    department: str | None = None
    serial_number: str | None = None
    current_value: str | None = None
    expected_value: str | None = None
    note: str | None = None


class DataQualityIssue(BaseModel):
    code: str
    title: str
    severity: Severity
    scope: str
    description: str
    count: int = Field(ge=0)
    records: list[DataQualityRecord] = Field(default_factory=list)


class DataQualitySummaryResponse(BaseModel):
    read_only: bool = True
    allowed_actions: list[str] = Field(default_factory=lambda: ["view", "filter", "refresh"])
    checked_at: str
    month: DataQualityMonth
    metrics: dict[str, int]
    reconciliation: dict[str, int | str | bool]
    issues: list[DataQualityIssue]
