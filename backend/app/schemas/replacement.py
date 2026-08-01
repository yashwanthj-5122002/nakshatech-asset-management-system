from datetime import datetime

from pydantic import BaseModel


class ReplacementCreate(BaseModel):
    old_asset_id: int
    new_asset_id: int | None = None
    reason: str
    damage_category: str = "technical_failure"
    inspection_finding: str | None = None
    final_action: str = "replacement_pending"


class ReplacementApproval(BaseModel):
    approval_status: str
    new_asset_id: int | None = None
    final_action: str | None = None
    remarks: str | None = None


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
    approved_by: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
