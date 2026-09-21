from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

BusinessViewer = Literal["finance", "management", "bd", "project_manager", "unavailable"]
BusinessRecordStatus = Literal["submitted", "verified"]


class BusinessTotals(BaseModel):
    total: float = 0.0
    released: float = 0.0
    decided: float = 0.0
    pending: float = 0.0
    currency: str = "INR"


class BusinessBreakdownRow(BaseModel):
    key: str
    label: str
    total: float = 0.0
    released: float = 0.0
    decided: float = 0.0
    pending: float = 0.0
    project_count: int = 0


class BusinessRecordRow(BaseModel):
    record_id: int | None = None
    project_id: int
    project_code: str
    project_name: str
    client_id: int | None = None
    client_code: str | None = None
    client_name: str | None = None
    project_manager_user_id: int | None = None
    project_manager_name: str | None = None
    department_code: str
    department_label: str
    amount_total: float = 0.0
    amount_released: float = 0.0
    amount_decided: float = 0.0
    amount_pending: float = 0.0
    currency: str = "INR"
    notes: str | None = None
    status: BusinessRecordStatus = "submitted"
    verified_at: datetime | None = None
    updated_at: datetime | None = None


class BusinessMonthPoint(BaseModel):
    month: str
    label: str
    total: float = 0.0
    released: float = 0.0
    decided: float = 0.0
    pending: float = 0.0


class BusinessHistoryEntry(BaseModel):
    id: int
    action: str
    actor_name: str | None = None
    actor_role: str | None = None
    reporting_month: str
    changes: dict[str, dict[str, float | str | None]] | None = None
    created_at: datetime


class BusinessOverview(BaseModel):
    month: str
    viewer: BusinessViewer
    can_enter: bool = False
    totals: BusinessTotals = Field(default_factory=BusinessTotals)
    by_department: list[BusinessBreakdownRow] = Field(default_factory=list)
    by_project_manager: list[BusinessBreakdownRow] = Field(default_factory=list)
    by_client: list[BusinessBreakdownRow] = Field(default_factory=list)
    rows: list[BusinessRecordRow] = Field(default_factory=list)
    months: list[str] = Field(default_factory=list)
    my_monthly_history: list[BusinessMonthPoint] = Field(default_factory=list)


class BusinessRecordUpsertRequest(BaseModel):
    project_id: int = Field(gt=0)
    reporting_month: str
    amount_total: float = Field(default=0, ge=0, le=1_000_000_000_000)
    amount_released: float = Field(default=0, ge=0, le=1_000_000_000_000)
    amount_decided: float = Field(default=0, ge=0, le=1_000_000_000_000)
    amount_pending: float = Field(default=0, ge=0, le=1_000_000_000_000)
    currency: str = Field(default="INR", min_length=1, max_length=12)
    department_code: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("notes", mode="before")
    @classmethod
    def strip_notes(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class BusinessVerifyRequest(BaseModel):
    reporting_month: str
    verified: bool = True
