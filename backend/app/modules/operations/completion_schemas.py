from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class DepartmentCompletionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=4000)


class MasterProjectDeliveryRequest(BaseModel):
    final_output_reference: str = Field(min_length=3, max_length=1500)
    remarks: str | None = Field(default=None, max_length=8000)


FinanceClosureStatus = Literal["billing_in_progress", "financially_closed"]


class FinanceClosureUpdate(BaseModel):
    status: FinanceClosureStatus
    note: str | None = Field(default=None, max_length=8000)
