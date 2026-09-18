from __future__ import annotations

from pydantic import BaseModel, Field


class TechnicalDirectoryMemberCreate(BaseModel):
    user_id: int = Field(gt=0)
    pm_eligible: bool = True
    receive_sample_notifications: bool = True
    receive_handover_notifications: bool = True
    receive_completion_notifications: bool = True
    notes: str | None = Field(default=None, max_length=2000)


class TechnicalDirectoryMemberUpdate(BaseModel):
    pm_eligible: bool | None = None
    receive_sample_notifications: bool | None = None
    receive_handover_notifications: bool | None = None
    receive_completion_notifications: bool | None = None
    is_active: bool | None = None
    notes: str | None = Field(default=None, max_length=2000)
