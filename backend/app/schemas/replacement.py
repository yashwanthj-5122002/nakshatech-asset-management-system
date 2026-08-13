from datetime import datetime

from pydantic import BaseModel
from typing import Literal


class ReplacementCreate(BaseModel):
    reporting_month: str | None = None
    old_asset_id: int
    new_asset_id: int | None = None
    reason: str
    damage_category: str = "technical_failure"
    inspection_finding: str | None = None
    final_action: str = "replacement_pending"


class ReplacementApproval(BaseModel):
    approval_status: Literal["approved", "rejected", "returned"]
    new_asset_id: int | None = None
    final_action: str | None = None
    remarks: str | None = None


class ReplacementResubmit(BaseModel):
    reporting_month: str | None = None
    new_asset_id: int | None = None
    reason: str
    damage_category: str = "technical_failure"
    inspection_finding: str | None = None
    final_action: str = "replacement_pending"


class ReplacementResponse(BaseModel):
    id: int
    replacement_code: str
    old_asset_id: int
    old_asset_code: str
    new_asset_id: int | None = None
    new_asset_code: str | None = None
    reason: str
    damage_category: str
    inspection_finding: str | None = None
    approval_status: str
    final_action: str
    requested_by: str | None = None
    requested_by_email: str | None = None
    requested_by_role: str | None = None
    approved_by: str | None = None
    approved_by_email: str | None = None
    approved_by_role: str | None = None
    reporting_month: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    decision_remarks: str | None = None
    updated_at: datetime | None = None
