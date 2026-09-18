from __future__ import annotations

from pydantic import BaseModel, Field


class TechnicalRoutingActivateRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=2000)
