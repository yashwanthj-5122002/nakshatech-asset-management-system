from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ProjectDataHandoverCreate(BaseModel):
    project_id: int = Field(gt=0)
    from_workstream_id: int = Field(gt=0)
    to_workstream_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=255)
    expected_output: str = Field(min_length=3, max_length=10000)


class ProjectDataHandoverSubmit(BaseModel):
    output_reference: str = Field(min_length=3, max_length=1500)
    notes: str | None = Field(default=None, max_length=5000)


class ProjectDataHandoverDecision(BaseModel):
    decision: Literal["accepted", "revision_requested"]
    feedback: str | None = Field(default=None, max_length=5000)
