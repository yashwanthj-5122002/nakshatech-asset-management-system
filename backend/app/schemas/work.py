from datetime import date, datetime

from pydantic import BaseModel, Field


class WorkRecordCreate(BaseModel):
    reporting_month: str | None = None
    module: str = "it"
    asset_id: int | None = None
    title: str
    work_type: str = "General"
    project: str | None = None
    assigned_to: str | None = None
    technician: str | None = None
    priority: str = "medium"
    issue_description: str | None = None
    details: str | None = None
    start_date: date | None = None
    expected_completion_date: date | None = None


class WorkRecordUpdate(BaseModel):
    reporting_month: str | None = None
    status: str | None = None
    technician: str | None = None
    root_cause: str | None = None
    resolution: str | None = None
    replaced_component: str | None = None
    replacement_asset_tag: str | None = None
    cost: float | None = Field(default=None, ge=0)
    approval_status: str | None = None


class WorkRecordResponse(WorkRecordCreate):
    id: int
    work_code: str
    status: str
    root_cause: str | None = None
    resolution: str | None = None
    replaced_component: str | None = None
    replacement_asset_tag: str | None = None
    cost: float | None = None
    approval_status: str
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    asset_code: str | None = None

    model_config = {"from_attributes": True}
