from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ManagementClientInput(BaseModel):
    client_code: str = Field(min_length=2, max_length=32)
    client_name: str = Field(min_length=2, max_length=255)
    client_email: str | None = Field(default=None, max_length=255)
    organization_email: str | None = Field(default=None, max_length=255)
    address: str | None = Field(default=None, max_length=3000)
    country: str = Field(default="India", min_length=2, max_length=100)
    gst_number: str | None = Field(default=None, max_length=32)
    contact_person_name: str = Field(min_length=2, max_length=255)
    contact_person_email: str | None = Field(default=None, max_length=255)
    contact_person_phone: str | None = Field(default=None, max_length=40)
    work_description: str | None = Field(default=None, max_length=5000)

    @field_validator("client_code", mode="before")
    @classmethod
    def normalize_client_code(cls, value):
        if not isinstance(value, str):
            return value
        value = value.strip().upper()
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_/. ")
        if any(character not in allowed for character in value):
            raise ValueError("Client ID contains unsupported characters")
        return value

    @field_validator(
        "client_name", "client_email", "organization_email", "address", "country",
        "gst_number", "contact_person_name", "contact_person_email", "contact_person_phone",
        "work_description", mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @field_validator("client_email", "organization_email", "contact_person_email")
    @classmethod
    def validate_email(cls, value):
        if not value:
            return value
        value = value.lower()
        local, separator, domain = value.partition("@")
        if not separator or not local or not domain or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter a valid email address")
        return value

    @field_validator("gst_number")
    @classmethod
    def normalize_gst(cls, value):
        return value.upper().replace(" ", "") if value else value


class ManagementClientResponse(ManagementClientInput):
    model_config = ConfigDict(from_attributes=True)
    can_request_project: bool = False

    id: int
    source_person_name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
