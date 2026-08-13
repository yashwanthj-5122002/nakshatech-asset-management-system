from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class OTPRequest(BaseModel):
    email: EmailStr


class OTPRequestResponse(BaseModel):
    message: str
    expires_in_seconds: int | None = None
    development_otp: str | None = None


class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class RegistrationOTPVerifyResponse(BaseModel):
    registration_token: str


class RegistrationCompleteRequest(BaseModel):
    registration_token: str
    full_name: str = Field(min_length=2, max_length=255)
    employee_id: str = Field(min_length=2, max_length=80)
    department: str = Field(min_length=2, max_length=120)
    designation: str | None = Field(default=None, max_length=160)
    phone_number: str | None = Field(default=None, max_length=40)
    branch_id: int
    password: str = Field(min_length=10, max_length=128)

    @field_validator("full_name", "employee_id", "department", "designation", "phone_number")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class MFASetupResponse(BaseModel):
    mfa_setup_token: str
    otpauth_uri: str
    qr_code_data_uri: str
    issuer: str
    account_name: str


class MFAConfirmRequest(BaseModel):
    mfa_setup_token: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class MFALoginVerifyRequest(BaseModel):
    pre_auth_token: str
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotPasswordVerifyResponse(BaseModel):
    reset_token: str


class PasswordResetRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=10, max_length=128)


class ManagementPasswordSetupRequest(BaseModel):
    password_change_token: str
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)


class ManagementPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=6, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    confirm_password: str = Field(min_length=10, max_length=128)


class BranchResponse(BaseModel):
    id: int
    code: str
    name: str
    address: str | None = None


class BranchSelectionRequest(BaseModel):
    branch_id: int


class TicketAssetResponse(BaseModel):
    id: int
    asset_code: str
    cpu_asset_tag: str | None = None
    workstation_no: str | None = None
    used_by: str | None = None
    department: str | None = None
    system_name: str | None = None
    device_type: str
    processor: str | None = None
    memory_gb: str | None = None
    ssd: str | None = None
    hdd: str | None = None
    operating_system: str | None = None
    location: str | None = None
    work_mode: str | None = None
    status: str
    monitor_asset_tags: str | None = None
    mouse_asset_tag: str | None = None
    keyboard_asset_tag: str | None = None


class TicketProblemOption(BaseModel):
    code: str
    label: str


class TicketComponentOption(BaseModel):
    code: str
    label: str
    problems: list[TicketProblemOption]


class TicketCatalogResponse(BaseModel):
    components: list[TicketComponentOption]


class TicketImpactAssessment(BaseModel):
    work_stopped: bool = False
    alternative_available: bool = True
    multiple_users_affected: bool = False
    data_loss_risk: bool = False
    security_risk: bool = False
    client_delivery_affected: bool = False
    recurring_issue: bool = False
    started_when: str | None = Field(default=None, max_length=120)


class TicketPriorityPreviewRequest(BaseModel):
    component: str
    problem_code: str
    impact: TicketImpactAssessment


class TicketPriorityPreviewResponse(BaseModel):
    priority: str
    priority_label: str
    reason: str
    sla_target_minutes: int
    problem_label: str


class TicketCreateRequest(BaseModel):
    department: str
    reporting_manager_email: EmailStr
    category: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=10, max_length=10000)
    priority: str | None = "medium"
    location: str | None = Field(default=None, max_length=255)
    asset_id: int | None = Field(default=None, ge=1)
    asset_number: str | None = Field(default=None, max_length=120)
    component: str | None = Field(default=None, max_length=80)
    problem_code: str | None = Field(default=None, max_length=120)
    impact: TicketImpactAssessment | None = None

    @field_validator("reporting_manager_email")
    @classmethod
    def validate_reporting_manager_email(cls, value: EmailStr) -> str:
        normalized = str(value).strip().lower()
        if not normalized.endswith("@nakshatech.com"):
            raise ValueError("Reporting Manager Email must use the @nakshatech.com domain")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Problem Description must contain at least 10 characters")
        return value


class TicketMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class TicketUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    assign_to_self: bool = False
    resolution: str | None = Field(default=None, max_length=10000)


class TicketSummaryResponse(BaseModel):
    id: int
    ticket_code: str
    requester_name: str
    requester_email: EmailStr
    branch_id: int
    branch_name: str
    department: str
    category: str | None
    title: str
    priority: str
    status: str
    asset_number: str | None
    component: str | None
    component_asset_tag: str | None
    problem_code: str | None
    problem_label: str | None
    priority_reason: str | None
    sla_target_minutes: int | None
    sla_status: str = "not_applicable"
    sla_due_at: datetime | None = None
    sla_warning_at: datetime | None = None
    sla_first_response_at: datetime | None = None
    sla_remaining_seconds: int | None = None
    sla_warning: bool = False
    sla_breached: bool = False
    sla_escalation_level: str = "none"
    assigned_to_name: str | None
    queue_position: int | None = None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    can_handle: bool


class TicketMessageResponse(BaseModel):
    id: int
    author_id: int
    author_name: str
    author_email: EmailStr
    author_role: str
    message: str
    created_at: datetime


class TicketAttachmentResponse(BaseModel):
    id: int
    ticket_id: int
    message_id: int | None = None
    uploaded_by_id: int
    uploaded_by_name: str
    original_filename: str
    mime_type: str
    file_size: int
    created_at: datetime


class TicketDetailResponse(TicketSummaryResponse):
    description: str
    reporting_manager_email: EmailStr | None
    location: str | None
    asset_number: str | None
    asset_id: int | None
    asset_snapshot: TicketAssetResponse | None
    impact_assessment: TicketImpactAssessment | None
    resolution: str | None
    attachments: list[TicketAttachmentResponse]
    messages: list[TicketMessageResponse]


class NotificationResponse(BaseModel):
    id: int
    ticket_id: int
    ticket_code: str
    notification_type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime


class AuditPageViewRequest(BaseModel):
    path: str = Field(min_length=1, max_length=255)
    title: str | None = Field(default=None, max_length=255)


class SoftwareUserResponse(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    employee_id: str | None
    department: str | None
    designation: str | None
    phone_masked: str | None
    role: str
    branch: str
    email_verified: bool
    account_status: str
    mfa_enabled: bool
    is_active: bool
    last_login_at: datetime | None
    last_logout_at: datetime | None
    created_at: datetime


class AuditEventResponse(BaseModel):
    id: int
    actor_email: str | None
    event_type: str
    result: str
    branch_name: str | None
    module: str | None
    target_type: str | None
    target_id: str | None
    details: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
