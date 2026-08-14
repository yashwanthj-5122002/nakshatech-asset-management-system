from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.schemas.replacement import ReplacementCreate, ReplacementResubmit


class ManagementPurchaseDecision(ReplacementCreate.__base__):
    action: Literal["approve", "reject", "send_back"]
    remarks: str | None = None
    approved_amount: float | None = Field(default=None, ge=0)


class ITReplacementCreate(ReplacementCreate):
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ITReplacementProcess(ReplacementCreate.__base__):
    new_asset_id: int | None = None
    remarks: str | None = None
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ITReplacementResubmit(ReplacementResubmit):
    approval_recipient_name: str = Field(min_length=1, max_length=255)
    approval_recipient_email: str = Field(min_length=3, max_length=255)


class ManagementControlFilter(ReplacementCreate.__base__):
    month: str | None = None
