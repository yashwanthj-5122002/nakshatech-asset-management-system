from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ManagementPurchaseDecision(BaseModel):
    action: Literal["approve", "reject", "send_back"]
    remarks: str | None = None
    approved_amount: float | None = Field(default=None, ge=0)


class ITReplacementProcess(BaseModel):
    new_asset_id: int | None = None
    remarks: str | None = None


class ManagementControlFilter(BaseModel):
    month: str | None = None
