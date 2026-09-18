from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


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
    project_manager_id: int | None = Field(default=None, gt=0)
    comments: str | None = Field(default=None, max_length=5000)

    @field_validator("project_code")
    @classmethod
    def normalize_project_code(cls, value: str | None) -> str | None:
        return value.strip() if value else None


class BDProjectManagerUpdate(BaseModel):
    project_manager_id: int = Field(gt=0)
    comments: str | None = Field(default=None, max_length=5000)


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


# V8 authoritative BD -> Finance -> Ortho workflow schemas.
class WorkflowProjectCreate(BaseModel):
    client_id: int = Field(gt=0)
    project_code: str = Field(min_length=2, max_length=80)
    project_name: str = Field(min_length=2, max_length=255)
    start_date: date
    end_date: date
    scope_text: str = Field(min_length=2, max_length=10000)
    quantity: Decimal | None = Field(default=None, ge=0)
    quantity_unit: str = Field(default="unit", min_length=1, max_length=30)
    priority: Literal["low", "medium", "high", "urgent"] = "medium"
    commercial_value: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", min_length=2, max_length=12)
    po_wo_number: str | None = Field(default=None, max_length=160)
    attachment_references: list[str] = Field(default_factory=list, max_length=20)
    description: str | None = Field(default=None, max_length=5000)

    @field_validator("project_code", mode="before")
    @classmethod
    def normalize_workflow_project_code(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/. " )
        if not value or any(char not in allowed for char in value):
            raise ValueError("Project ID may contain letters, numbers, spaces, hyphen, underscore, slash or dot")
        return value

    @field_validator("project_name", "scope_text", "quantity_unit", "currency", "po_wo_number", "description", mode="before")
    @classmethod
    def strip_workflow_project_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("Project end date cannot be earlier than project start date")
        return self

    @field_validator("attachment_references")
    @classmethod
    def normalize_attachment_references(cls, value):
        cleaned = [str(item).strip() for item in (value or []) if str(item).strip()]
        if any(len(item) > 1000 for item in cleaned):
            raise ValueError("Each attachment reference must be 1000 characters or fewer")
        return list(dict.fromkeys(cleaned))


class WorkflowFinanceReview(BaseModel):
    decision: Literal["approve", "return"]
    feedback: str | None = Field(default=None, max_length=5000)

    @field_validator("feedback", mode="before")
    @classmethod
    def strip_feedback(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def require_return_feedback(self):
        if self.decision == "return" and not self.feedback:
            raise ValueError("Finance feedback is mandatory when returning a project")
        return self


class WorkflowPMAssignment(BaseModel):
    project_manager_id: int = Field(gt=0)


class WorkflowTeamSetup(BaseModel):
    team_leader_user_id: int = Field(gt=0)
    production_user_ids: list[int] = Field(min_length=1, max_length=500)
    qc_user_ids: list[int] = Field(min_length=1, max_length=500)
    qa_user_ids: list[int] = Field(min_length=1, max_length=500)

    @field_validator("production_user_ids", "qc_user_ids", "qa_user_ids")
    @classmethod
    def unique_workflow_team_ids(cls, value):
        return list(dict.fromkeys(value or []))


class WorkflowWorkAllocation(BaseModel):
    package_code: str = Field(min_length=1, max_length=120)
    area_name: str = Field(min_length=1, max_length=255)
    quantity: Decimal = Field(gt=0)
    quantity_unit: str = Field(default="unit", min_length=1, max_length=30)
    target_date: date
    instructions: str = Field(min_length=1, max_length=5000)
    production_user_id: int = Field(gt=0)
    qc_user_id: int = Field(gt=0)
    qa_user_id: int = Field(gt=0)

    @field_validator("package_code", "area_name", "quantity_unit", "instructions", mode="before")
    @classmethod
    def strip_work_allocation_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class WorkflowDailyActivity(BaseModel):
    update_date: date | None = None
    work_type: str = Field(default="Production", min_length=1, max_length=255)
    quantity_completed: Decimal = Field(ge=0)
    files_completed: int = Field(default=0, ge=0)
    hours_spent: Decimal | None = Field(default=None, ge=0)
    status: Literal["on_track", "at_risk", "blocked", "completed"] = "on_track"
    blockers: str | None = Field(default=None, max_length=5000)
    remarks: str | None = Field(default=None, max_length=5000)


class WorkflowReviewRequest(BaseModel):
    decision: Literal["approve", "reject"]
    comments: str | None = Field(default=None, max_length=5000)


class WorkflowDeliveryRequest(BaseModel):
    remarks: str | None = Field(default=None, max_length=5000)


class WorkflowOperationalCompletion(BaseModel):
    completion_date: date
    final_delivery_reference: str | None = Field(default=None, max_length=255)
    remarks: str | None = Field(default=None, max_length=5000)


class WorkflowFinanceClosure(BaseModel):
    remarks: str = Field(min_length=2, max_length=5000)


TechnicalDepartmentCode = Literal["ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"]
ProjectWorkstreamStatus = Literal["planned", "ready", "in_progress", "blocked", "completed"]


class ProjectWorkstreamInput(BaseModel):
    department_code: TechnicalDepartmentCode
    project_manager_user_id: int = Field(gt=0)
    sequence_order: int = Field(default=1, ge=1, le=50)
    notes: str | None = Field(default=None, max_length=5000)


class ProjectWorkstreamConfig(BaseModel):
    workstreams: list[ProjectWorkstreamInput] = Field(min_length=1, max_length=6)

    @field_validator("workstreams")
    @classmethod
    def unique_departments(cls, value):
        codes = [item.department_code for item in value]
        if len(codes) != len(set(codes)):
            raise ValueError("Each technical department can appear only once in a project")
        return value


class ProjectWorkstreamStatusUpdate(BaseModel):
    status: ProjectWorkstreamStatus
    notes: str | None = Field(default=None, max_length=5000)
