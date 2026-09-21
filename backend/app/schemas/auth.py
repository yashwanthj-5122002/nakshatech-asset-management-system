from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str | None = None
    access_mode: str | None = None


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: str
    branch: str
    employee_id: str | None = None
    department: str | None = None
    designation: str | None = None
    phone_number: str | None = None
    joining_date: date | None = None
    date_of_birth: date | None = None
    created_at: datetime | None = None
    selected_branch_id: int | None = None
    selected_branch_name: str | None = None
    email_verified: bool = False
    mfa_enabled: bool = False


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    phone_number: str | None = Field(default=None, max_length=40)
    date_of_birth: date | None = None


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)


class LoginResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    user: UserResponse | None = None
    requires_mfa: bool = False
    mfa_setup_required: bool = False
    pre_auth_token: str | None = None
    mfa_setup_token: str | None = None
    otpauth_uri: str | None = None
    qr_code_data_uri: str | None = None
    password_change_required: bool = False
    password_change_token: str | None = None
    branch_selection_required: bool = False
