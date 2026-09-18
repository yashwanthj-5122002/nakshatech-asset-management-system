from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


FinanceClaimType = Literal["advance", "reimbursement", "additional_advance"]
FinanceDecisionAction = Literal["approve", "reject", "send_back"]
FinancePaymentMode = Literal["bank_transfer", "upi", "cash", "cheque", "card", "other"]
FinanceReportPeriod = Literal["month", "quarter", "year", "all"]
FinanceClientSourceTeam = Literal["bd_team", "software_team", "team_manager", "manager", "department_head", "management", "other"]
FinanceProjectMasterStatus = Literal["active", "on_hold", "completed", "inactive"]
FinanceClientType = Literal["client", "uav"]
SettlementStatus = Literal[
    "draft",
    "submitted",
    "admin_approved",
    "admin_rejected",
    "admin_sent_back",
    "finance_finalized",
    "finance_rejected",
    "finance_sent_back",
]


class FinanceProjectAssignedEmployeeResponse(BaseModel):
    id: int
    full_name: str
    email: str
    employee_id: str | None = None
    department: str | None = None


class FinanceProjectUserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    employee_id: str | None = None
    department: str | None = None
    designation: str | None = None
    role: str


class FinanceProjectResponse(BaseModel):
    id: int
    project_code: str
    project_name: str
    client_id: int | None = None
    client_code: str | None = None
    client_name: str | None = None
    project_number: int | None = None
    project_source_team: FinanceClientSourceTeam | None = None
    project_source_person_name: str | None = None
    client_awarded_by_name: str | None = None
    project_award_date: date | None = None
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_active: bool
    lifecycle_status: str = "active"
    expense_allowed: bool = True
    expense_block_reason: str | None = None
    task: str | None = None
    project_status: FinanceProjectMasterStatus = "active"
    project_manager_id: int | None = None
    project_manager_name: str | None = None
    reporting_manager_id: int | None = None
    reporting_manager_name: str | None = None
    assigned_employee_ids: list[int] = Field(default_factory=list)
    assigned_employees: list[FinanceProjectAssignedEmployeeResponse] = Field(default_factory=list)


class FinanceClientBaseRequest(BaseModel):
    vendor_code: str | None = Field(default=None, max_length=80)
    client_type: FinanceClientType = "client"
    client_name: str = Field(min_length=2, max_length=255)
    primary_phone: str | None = Field(default=None, max_length=40)
    client_email: str | None = Field(default=None, max_length=255)
    organization_email: str | None = Field(default=None, max_length=255)
    contact_person_name: str = Field(min_length=2, max_length=255)
    contact_person_phone: str | None = Field(default=None, max_length=40)
    contact_person_email: str | None = Field(default=None, max_length=255)
    task: str | None = Field(default=None, max_length=5000)
    bd_name: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=3000)
    description: str | None = Field(default=None, max_length=5000)
    country: str = Field(default="India", min_length=2, max_length=100)
    gst_number: str | None = Field(default=None, max_length=32)
    source_team: FinanceClientSourceTeam = "bd_team"
    source_person_name: str | None = Field(default=None, max_length=255)
    is_active: bool = True

    @field_validator("vendor_code", "client_name", "primary_phone", "client_email", "organization_email", "contact_person_name", "contact_person_phone", "contact_person_email", "task", "bd_name", "address", "description", "country", "gst_number", "source_person_name", mode="before")
    @classmethod
    def strip_client_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("gst_number")
    @classmethod
    def normalize_gst(cls, value):
        return value.upper().replace(" ", "") if value else value

    @field_validator("client_email", "organization_email", "contact_person_email")
    @classmethod
    def normalize_client_email(cls, value):
        if not value:
            return value
        value = value.strip().lower()
        local, sep, domain = value.partition("@")
        if not sep or not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter a valid client email address")
        return value


class FinanceClientCreateRequest(FinanceClientBaseRequest):
    client_code: str = Field(min_length=2, max_length=32)

    @field_validator("client_code", mode="before")
    @classmethod
    def normalize_client_code(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/. ")
        if not value or any(char not in allowed for char in value):
            raise ValueError("Client ID / Code may contain letters, numbers, spaces, hyphen, underscore, slash or dot")
        return value


class FinanceClientUpdateRequest(FinanceClientBaseRequest):
    pass


class FinanceClientResponse(BaseModel):
    id: int
    vendor_code: str | None = None
    client_type: FinanceClientType = "client"
    import_source: str | None = None
    imported_at: datetime | None = None
    client_code: str
    client_name: str
    primary_phone: str | None = None
    client_email: str | None = None
    organization_email: str | None = None
    contact_person_name: str
    contact_person_phone: str | None = None
    contact_person_email: str | None = None
    task: str | None = None
    bd_name: str | None = None
    address: str | None = None
    location: str | None = None
    description: str | None = None
    country: str
    gst_number: str | None = None
    source_team: FinanceClientSourceTeam
    source_person_name: str | None = None
    is_active: bool
    project_count: int = 0
    active_project_count: int = 0
    created_at: datetime
    updated_at: datetime
    created_by_name: str | None = None
    created_by_email: str | None = None
    updated_by_name: str | None = None
    updated_by_email: str | None = None


class FinanceClientProjectBaseRequest(BaseModel):
    project_name: str = Field(min_length=2, max_length=255)
    task: str | None = Field(default=None, max_length=5000)
    project_status: FinanceProjectMasterStatus | None = None
    project_manager_id: int | None = Field(default=None, ge=1)
    reporting_manager_id: int | None = Field(default=None, ge=1)
    assigned_employee_ids: list[int] = Field(default_factory=list, max_length=500)
    project_source_team: FinanceClientSourceTeam
    project_source_person_name: str = Field(min_length=2, max_length=255)
    client_awarded_by_name: str | None = Field(default=None, max_length=255)
    project_award_date: date | None = None
    description: str | None = Field(default=None, max_length=5000)
    start_date: date
    end_date: date
    is_active: bool = True

    @field_validator("project_name", "task", "project_source_person_name", "client_awarded_by_name", "description", mode="before")
    @classmethod
    def strip_project_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("assigned_employee_ids")
    @classmethod
    def unique_employee_ids(cls, value):
        return list(dict.fromkeys(value or []))

    @model_validator(mode="after")
    def validate_project_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError("Project end date cannot be earlier than project start date")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("Project schedule cannot span more than 10 years")
        return self


class FinanceClientProjectCreateRequest(FinanceClientProjectBaseRequest):
    project_code: str = Field(min_length=2, max_length=80)

    @field_validator("project_code", mode="before")
    @classmethod
    def normalize_project_code(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/. ")
        if not value or any(char not in allowed for char in value):
            raise ValueError("Project ID / Number may contain letters, numbers, spaces, hyphen, underscore, slash or dot")
        return value


class FinanceClientProjectUpdateRequest(FinanceClientProjectBaseRequest):
    pass


class FinanceProjectStatusUpdate(BaseModel):
    project_status: FinanceProjectMasterStatus


class FinanceProjectScheduleUpdate(BaseModel):
    start_date: date
    end_date: date
    is_active: bool = True

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.end_date < self.start_date:
            raise ValueError("Project end date cannot be earlier than project start date")
        if (self.end_date - self.start_date).days > 3650:
            raise ValueError("Project schedule cannot span more than 10 years")
        return self


class ExpenseClaimItemInput(BaseModel):
    category: str = Field(min_length=2, max_length=80)
    other_category: str | None = Field(default=None, max_length=160)
    description: str = Field(min_length=2, max_length=1000)
    amount: float = Field(gt=0, le=100_000_000)
    payment_mode: FinancePaymentMode | None = None
    expense_date: date | None = None

    @field_validator("category", "other_category", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @model_validator(mode="after")
    def validate_other_category(self):
        if self.category.strip().lower() == "other" and not (self.other_category or "").strip():
            raise ValueError("Describe the expense category when Other is selected")
        return self


class ExpenseClaimCreateRequest(BaseModel):
    project_id: int
    claim_type: FinanceClaimType
    purpose_description: str = Field(min_length=10, max_length=5000)
    requested_work_start_date: date
    requested_work_end_date: date
    parent_advance_claim_id: int | None = Field(default=None, ge=1)
    previous_advance_amount: float | None = Field(default=None, ge=0, le=100_000_000)
    amount_already_used: float | None = Field(default=None, ge=0, le=100_000_000)
    items: list[ExpenseClaimItemInput] = Field(min_length=1, max_length=25)

    @field_validator("purpose_description", mode="before")
    @classmethod
    def strip_description(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_type_specific_fields(self):
        if self.requested_work_end_date < self.requested_work_start_date:
            raise ValueError("Work end date cannot be earlier than the work start date")
        if (self.requested_work_end_date - self.requested_work_start_date).days > 366:
            raise ValueError("A single expense request cannot span more than 366 days")
        if self.claim_type == "additional_advance":
            if self.parent_advance_claim_id is None:
                raise ValueError("Select the original Advance Request for an additional advance")
            if self.previous_advance_amount is None or self.previous_advance_amount <= 0:
                raise ValueError("Previous company advance amount is required for an additional advance request")
            if self.amount_already_used is None or self.amount_already_used < 0:
                raise ValueError("Amount already used is required for an additional advance request")
        elif self.parent_advance_claim_id is not None:
            raise ValueError("Only an additional advance can be linked to an original Advance Request")
        return self


class ExpenseClaimUpdateRequest(ExpenseClaimCreateRequest):
    pass


class ExpenseClaimDecisionRequest(BaseModel):
    action: FinanceDecisionAction
    comments: str = Field(min_length=2, max_length=3000)
    approved_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    approved_work_start_date: date | None = None
    approved_work_end_date: date | None = None
    settlement_due_date: date | None = None

    @field_validator("comments", mode="before")
    @classmethod
    def strip_comments(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_dates(self):
        if self.approved_work_start_date and self.approved_work_end_date and self.approved_work_end_date < self.approved_work_start_date:
            raise ValueError("Approved work end date cannot be earlier than approved work start date")
        if self.settlement_due_date and self.approved_work_end_date and self.settlement_due_date < self.approved_work_end_date:
            raise ValueError("Settlement due date cannot be earlier than the approved work end date")
        return self


class ExpensePaymentRequest(BaseModel):
    payment_reference: str = Field(min_length=2, max_length=180)
    paid_amount: float | None = Field(default=None, gt=0, le=100_000_000)
    payment_mode: FinancePaymentMode = "bank_transfer"
    payment_date: date | None = None
    comments: str | None = Field(default=None, max_length=3000)

    @field_validator("payment_reference", "comments", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class ExpenseClaimItemResponse(BaseModel):
    id: int
    category: str
    other_category: str | None = None
    description: str
    amount: float
    payment_mode: FinancePaymentMode | None = None
    expense_date: date | None = None


class ExpenseClaimAttachmentResponse(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    content_sha256: str | None = None
    uploaded_by_id: int
    uploaded_by_name: str
    created_at: datetime


class ExpenseClaimEventResponse(BaseModel):
    id: int
    action: str
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    from_status: str | None = None
    to_status: str
    comments: str | None = None
    created_at: datetime


class ExpenseClaimPaymentResponse(BaseModel):
    id: int
    payment_reference: str
    payment_mode: FinancePaymentMode
    amount: float
    payment_date: date
    recorded_by_id: int
    recorded_by_name: str
    comments: str | None = None
    created_at: datetime


class SettlementItemInput(BaseModel):
    category: str = Field(min_length=2, max_length=80)
    other_category: str | None = Field(default=None, max_length=160)
    description: str = Field(min_length=2, max_length=1000)
    amount: float = Field(gt=0, le=100_000_000)
    payment_mode: FinancePaymentMode
    expense_date: date | None = None

    @field_validator("category", "other_category", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_other_category(self):
        if self.category.strip().lower() == "other" and not (self.other_category or "").strip():
            raise ValueError("Describe the settlement category when Other is selected")
        return self


class SettlementUpsertRequest(BaseModel):
    items: list[SettlementItemInput] = Field(min_length=1, max_length=100)


class SettlementDecisionRequest(BaseModel):
    action: FinanceDecisionAction
    comments: str = Field(min_length=2, max_length=3000)

    @field_validator("comments", mode="before")
    @classmethod
    def strip_comments(cls, value):
        return value.strip() if isinstance(value, str) else value


class SettlementItemResponse(BaseModel):
    id: int
    category: str
    other_category: str | None = None
    description: str
    amount: float
    payment_mode: FinancePaymentMode
    expense_date: date | None = None


class SettlementAttachmentResponse(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    file_size: int
    content_sha256: str | None = None
    uploaded_by_id: int
    uploaded_by_name: str
    created_at: datetime


class SettlementEventResponse(BaseModel):
    id: int
    action: str
    actor_name: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    from_status: str | None = None
    to_status: str
    comments: str | None = None
    created_at: datetime


class SettlementResponse(BaseModel):
    id: int
    settlement_code: str
    root_claim_id: int
    root_claim_code: str
    requester_id: int
    requester_name: str
    project: FinanceProjectResponse
    status: str
    total_advance_received: float
    total_expense_amount: float
    balance_to_return: float
    shortage_amount: float
    tally_status: str
    submitted_at: datetime | None = None
    finalized_at: datetime | None = None
    admin_decision_by_name: str | None = None
    admin_decision_at: datetime | None = None
    admin_comments: str | None = None
    finance_decision_by_name: str | None = None
    finance_decision_at: datetime | None = None
    finance_comments: str | None = None
    items: list[SettlementItemResponse]
    attachments: list[SettlementAttachmentResponse]
    events: list[SettlementEventResponse]
    can_edit: bool = False
    can_submit: bool = False
    can_admin_decide: bool = False
    can_finance_decide: bool = False


class ExpenseClaimResponse(BaseModel):
    id: int
    claim_code: str
    requester_id: int
    requester_name: str
    requester_email: str
    requester_department: str | None = None
    project: FinanceProjectResponse
    claim_type: FinanceClaimType
    purpose_description: str
    currency: str
    total_amount: float
    previous_advance_amount: float | None = None
    amount_already_used: float | None = None
    parent_advance_claim_id: int | None = None
    parent_advance_claim_code: str | None = None
    requested_work_start_date: date | None = None
    requested_work_end_date: date | None = None
    requested_work_days: int | None = None
    approved_work_start_date: date | None = None
    approved_work_end_date: date | None = None
    approved_work_days: int | None = None
    settlement_due_date: date | None = None
    settlement_status: str
    settlement_overdue: bool = False
    status: str
    admin_decision_by_name: str | None = None
    admin_decision_at: datetime | None = None
    admin_comments: str | None = None
    finance_decision_by_name: str | None = None
    finance_decision_at: datetime | None = None
    finance_comments: str | None = None
    finance_approved_amount: float | None = None
    remaining_amount: float
    payment_reference: str | None = None
    paid_amount: float | None = None
    paid_at: datetime | None = None
    submitted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    items: list[ExpenseClaimItemResponse]
    attachments: list[ExpenseClaimAttachmentResponse]
    events: list[ExpenseClaimEventResponse]
    payments: list[ExpenseClaimPaymentResponse]
    settlement: SettlementResponse | None = None
    linked_additional_advance_ids: list[int] = []
    can_edit: bool = False
    can_submit: bool = False
    can_admin_decide: bool = False
    can_finance_decide: bool = False
    can_mark_paid: bool = False
    can_settle_advance: bool = False
    can_request_additional_advance: bool = False


class FinanceBreakdownItem(BaseModel):
    key: str
    label: str
    amount: float
    count: int


class FinanceDashboardResponse(BaseModel):
    total_claims: int
    total_requested_amount: float
    pending_admin_count: int
    pending_admin_amount: float
    pending_finance_count: int
    pending_finance_amount: float
    approved_count: int
    approved_amount: float
    paid_count: int
    paid_amount: float
    outstanding_amount: float
    rejected_count: int
    sent_back_count: int
    partially_paid_count: int
    pending_settlement_count: int = 0
    overdue_settlement_count: int = 0
    settlement_under_review_count: int = 0
    settled_count: int = 0
    by_type: list[FinanceBreakdownItem]
    by_category: list[FinanceBreakdownItem]
    by_project: list[FinanceBreakdownItem]
    recent_claims: list[ExpenseClaimResponse]


class FinanceReportClaimRow(BaseModel):
    id: int
    claim_code: str
    submitted_at: datetime | None = None
    requester_name: str
    requester_email: str
    requester_department: str | None = None
    project_code: str
    project_name: str
    claim_type: FinanceClaimType
    status: str
    requested_amount: float
    approved_amount: float
    paid_amount: float
    outstanding_amount: float
    attachment_count: int
    payment_count: int
    updated_at: datetime


class FinanceReportMetric(BaseModel):
    label: str
    value: float
    count: int | None = None


class FinanceReportResponse(BaseModel):
    period: FinanceReportPeriod
    period_label: str
    start_date: date | None = None
    end_date: date | None = None
    available_years: list[int]
    total_records: int
    page: int
    page_size: int
    total_pages: int
    requested_amount: float
    approved_amount: float
    paid_amount: float
    outstanding_amount: float
    payment_period_amount: float
    payment_period_count: int
    pending_admin_amount: float
    pending_finance_amount: float
    integrity_issue_count: int
    by_project: list[FinanceBreakdownItem]
    by_employee: list[FinanceBreakdownItem]
    by_category: list[FinanceBreakdownItem]
    by_type: list[FinanceBreakdownItem]
    by_status: list[FinanceBreakdownItem]
    claims: list[FinanceReportClaimRow]
