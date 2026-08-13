from datetime import date, datetime

from pydantic import BaseModel, Field
from typing import Literal


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


class WorkApprovalDecision(BaseModel):
    action: Literal["approve", "return"]
    comments: str | None = None


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
    submitted_by_name: str | None = None
    submitted_by_email: str | None = None
    submitted_by_role: str | None = None
    submitted_at: datetime | None = None
    approved_by_name: str | None = None
    approved_by_email: str | None = None
    approved_by_role: str | None = None
    approved_at: datetime | None = None
    approval_comments: str | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    asset_code: str | None = None

    model_config = {"from_attributes": True}
