from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.replacement import ReplacementCreate, ReplacementResubmit


class ManagementPurchaseDecision(BaseModel):
    action: Literal["approve", "reject", "send_back"]
    remarks: str | None = None
    approved_amount: float | None = Field(default=None, ge=0)


class ITReplacementCreate(ReplacementCreate):
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ITReplacementProcess(BaseModel):
    new_asset_id: int | None = None
    remarks: str | None = None
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ITReplacementResubmit(ReplacementResubmit):
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ManagementControlFilter(BaseModel):
    month: str | None = None
