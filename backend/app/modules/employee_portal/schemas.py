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


class BranchResponse(BaseModel):
    id: int
    code: str
    name: str
    address: str | None = None


class BranchSelectionRequest(BaseModel):
    branch_id: int


class TicketCreateRequest(BaseModel):
    department: str
    category: str | None = Field(default=None, max_length=120)
    title: str = Field(min_length=4, max_length=255)
    description: str = Field(min_length=8, max_length=10000)
    priority: str = "medium"
    location: str | None = Field(default=None, max_length=255)
    asset_number: str | None = Field(default=None, max_length=120)


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
    assigned_to_name: str | None
    created_at: datetime
    updated_at: datetime
    can_handle: bool


class TicketMessageResponse(BaseModel):
    id: int
    author_id: int
    author_name: str
    author_email: EmailStr
    author_role: str
    message: str
    created_at: datetime


class TicketDetailResponse(TicketSummaryResponse):
    description: str
    location: str | None
    asset_number: str | None
    resolution: str | None
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
