from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, model_validator


def _lat(value: float) -> float:
    if value < -90 or value > 90:
        raise ValueError("Latitude must be between -90 and 90")
    return value


def _lon(value: float) -> float:
    if value < -180 or value > 180:
        raise ValueError("Longitude must be between -180 and 180")
    return value




class TravelKmEmailRoutingRequest(BaseModel):
    reporting_manager_email: EmailStr
    to_emails: list[EmailStr] = Field(default_factory=list, min_length=1, max_length=25)
    cc_emails: list[EmailStr] = Field(default_factory=list, max_length=25)

    @model_validator(mode="after")
    def validate_recipients(self):
        all_addresses = [
            str(self.reporting_manager_email).strip().lower(),
            *[str(value).strip().lower() for value in self.to_emails],
            *[str(value).strip().lower() for value in self.cc_emails],
        ]
        if len(set(all_addresses)) > 50:
            raise ValueError("A Travel/KM email can contain at most 50 unique recipients")
        return self


class TravelKmClaimCreateRequest(BaseModel):
    project_id: int = Field(gt=0)
    travel_date: date
    purpose_description: str = Field(min_length=5, max_length=4000)
    start_km: Decimal = Field(ge=0)
    start_latitude: float
    start_longitude: float
    start_accuracy_m: float | None = Field(default=None, ge=0)
    start_captured_at: datetime
    email_routing: TravelKmEmailRoutingRequest | None = None

    @model_validator(mode="after")
    def validate_coordinates(self):
        self.start_latitude = _lat(self.start_latitude)
        self.start_longitude = _lon(self.start_longitude)
        return self


class TravelKmEndRequest(BaseModel):
    end_km: Decimal = Field(ge=0)
    end_latitude: float
    end_longitude: float
    end_accuracy_m: float | None = Field(default=None, ge=0)
    end_captured_at: datetime

    @model_validator(mode="after")
    def validate_coordinates(self):
        self.end_latitude = _lat(self.end_latitude)
        self.end_longitude = _lon(self.end_longitude)
        return self


class TravelKmTrackPointRequest(BaseModel):
    latitude: float
    longitude: float
    accuracy_m: float | None = Field(default=None, ge=0)
    speed_mps: float | None = Field(default=None, ge=0)
    heading_deg: float | None = Field(default=None, ge=0, le=360)
    captured_at: datetime

    @model_validator(mode="after")
    def validate_coordinates(self):
        self.latitude = _lat(self.latitude)
        self.longitude = _lon(self.longitude)
        return self


class TravelKmReviseRequest(BaseModel):
    purpose_description: str | None = Field(default=None, min_length=5, max_length=4000)
    travel_date: date | None = None
    start_km: Decimal | None = Field(default=None, ge=0)
    end_km: Decimal | None = Field(default=None, ge=0)


class TravelKmDecisionRequest(BaseModel):
    action: Literal["approve", "send_back", "reject"]
    comments: str = Field(default="", max_length=4000)
    eligible_km: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def comments_required_for_negative_or_adjusted(self):
        if self.action in {"send_back", "reject"} and not self.comments.strip():
            raise ValueError("Comments are required when sending back or rejecting a claim")
        return self


class TravelKmFinanceDecisionRequest(BaseModel):
    action: Literal["approve", "reject"] = "approve"
    comments: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_finance_decision(self):
        if self.action == "reject" and not self.comments.strip():
            raise ValueError("Comments are required when Finance rejects a claim")
        return self


class TravelKmPaymentRequest(BaseModel):
    """Backward-compatible request for the legacy /finance-payment route.

    Travel allowance is now approved for monthly salary processing. Legacy
    callers may still send action=pay and old payment fields, but the server
    treats pay as Finance approval and does not record payment/UTR details.
    """

    action: Literal["pay", "approve", "reject"] = "pay"
    payment_reference: str | None = Field(default=None, max_length=180)
    payment_mode: str | None = Field(default=None, max_length=80)
    comments: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_legacy_finance_action(self):
        if self.action == "reject" and not self.comments.strip():
            raise ValueError("Comments are required when Finance rejects a claim")
        return self


class TravelKmProjectGeofenceRequest(BaseModel):
    site_name: str = Field(min_length=2, max_length=255)
    center_latitude: float
    center_longitude: float
    radius_m: float = Field(default=500.0, ge=50.0, le=10000.0)
    is_active: bool = True

    @model_validator(mode="after")
    def validate_geofence_coordinates(self):
        self.center_latitude = _lat(self.center_latitude)
        self.center_longitude = _lon(self.center_longitude)
        return self
