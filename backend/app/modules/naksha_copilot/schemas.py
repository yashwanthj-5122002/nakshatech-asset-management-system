from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PeriodType = Literal["month", "selected_months", "calendar_year", "financial_year"]


class CopilotAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=600)
    period_type: PeriodType = "selected_months"
    month: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    months: list[int] | None = None
    year: int | None = Field(default=None, ge=2020, le=2100)


class CopilotStatusResponse(BaseModel):
    enabled: bool
    configured: bool
    model: str
    privacy_mode: str
    allowed_roles: list[str]
    requests_per_hour: int


class CopilotAnswerResponse(BaseModel):
    request_id: str
    answer: str
    period_label: str
    period_type: PeriodType
    model: str
    privacy_mode: str
    sources: list[str]
