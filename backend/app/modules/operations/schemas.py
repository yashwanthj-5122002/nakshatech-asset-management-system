from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator


BDStage = Literal[
    "opportunity",
    "technical_sample",
    "client_review",
    "revision",
    "accepted",
    "finance_handoff",
    "project_linked",
    "production",
    "delivery_ready",
    "delivered",
    "closed",
]
OrthoMemberRole = Literal["project_manager", "team_leader", "production", "qc", "qa"]
ReviewDecision = Literal["approve", "reject"]
WorkAction = Literal["start", "pause", "resume", "complete"]


class BDOpportunityCreate(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    client_id: int | None = None
    client_name: str | None = Field(default=None, max_length=255)
    requirement: str = Field(min_length=5, max_length=10000)
    service_type: str = Field(default="ortho_lidar", min_length=2, max_length=80)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    expected_value: Decimal | None = Field(default=None, ge=0)
    expected_start_date: date | None = None
    expected_delivery_date: date | None = None


class BDStageUpdate(BaseModel):
    stage: BDStage
    comments: str | None = Field(default=None, max_length=5000)
    technical_sample_notes: str | None = Field(default=None, max_length=5000)
    client_feedback: str | None = Field(default=None, max_length=5000)


class BDProjectLink(BaseModel):
    project_id: int | None = None
    project_code: str | None = Field(default=None, max_length=80)
    comments: str | None = Field(default=None, max_length=5000)

    @field_validator("project_code")
    @classmethod
    def normalize_project_code(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class OrthoProjectActivate(BaseModel):
    project_id: int | None = None
    project_code: str | None = Field(default=None, max_length=80)
    opportunity_id: int | None = None
    total_area: Decimal | None = Field(default=None, ge=0)
    area_unit: str = Field(default="ha", min_length=1, max_length=30)
    scope_text: str | None = Field(default=None, max_length=10000)
    planned_hours: Decimal | None = Field(default=None, ge=0)
    target_value: Decimal | None = Field(default=None, ge=0)


class OrthoMemberUpsert(BaseModel):
    user_id: int | None = None
    employee_name: str | None = Field(default=None, max_length=255)
    employee_email: str | None = Field(default=None, max_length=255)
    member_role: OrthoMemberRole
    is_active: bool = True
    send_email: bool = True

    @field_validator("employee_name", "employee_email")
    @classmethod
    def normalize_identity_text(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None


class OrthoTeamSetup(BaseModel):
    team_leader_user_id: int = Field(gt=0)
    production_user_id: int = Field(gt=0)
    qc_user_id: int = Field(gt=0)
    qa_user_id: int = Field(gt=0)
    apply_to_unassigned_packages: bool = True


class OrthoWorkPackageCreate(BaseModel):
    package_code: str = Field(min_length=1, max_length=120)
    package_name: str = Field(min_length=1, max_length=255)
    area: Decimal | None = Field(default=None, ge=0)
    area_unit: str = Field(default="ha", min_length=1, max_length=30)
    target_hours: Decimal | None = Field(default=None, ge=0)
    team_leader_user_id: int | None = None
    production_user_id: int | None = None
    qc_user_id: int | None = None
    qa_user_id: int | None = None

    @field_validator("package_code", "package_name", "area_unit")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class OrthoWorkPackageAssignments(BaseModel):
    team_leader_user_id: int | None = None
    production_user_id: int | None = None
    qc_user_id: int | None = None
    qa_user_id: int | None = None




class OrthoDailyUpdateRequest(BaseModel):
    update_date: date | None = None
    achieved_area: Decimal | None = Field(default=None, ge=0)
    progress_percent: Decimal | None = Field(default=None, ge=0, le=100)
    hours_spent: Decimal | None = Field(default=None, ge=0)
    status: Literal["on_track", "at_risk", "blocked", "completed"] = "on_track"
    blockers: str | None = Field(default=None, max_length=5000)
    remarks: str | None = Field(default=None, max_length=5000)


class OrthoWorkActionRequest(BaseModel):
    action: WorkAction


class OrthoReviewRequest(BaseModel):
    decision: ReviewDecision
    comments: str | None = Field(default=None, max_length=5000)


class OrthoDeliveryRequest(BaseModel):
    remarks: str | None = Field(default=None, max_length=5000)
