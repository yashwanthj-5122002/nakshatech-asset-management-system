from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectWorkstreamProgressUpdate(BaseModel):
    progress_percent: int = Field(ge=0, le=100)
    note: str | None = Field(default=None, max_length=5000)


class ProjectHandoverScheduleUpdate(BaseModel):
    due_at: datetime | None = None
    note: str | None = Field(default=None, max_length=5000)
