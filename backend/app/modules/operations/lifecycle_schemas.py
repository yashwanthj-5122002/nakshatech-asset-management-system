from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.modules.commercial.currencies import is_supported_currency
from app.modules.commercial.fx_service import OVERRIDE_MODES


class FeedbackRequestCreate(BaseModel):
    message: str | None = Field(default=None, max_length=10_000)
    expiry_days: int = Field(default=14, ge=1, le=90)


class FeedbackAttachmentCreate(BaseModel):
    original_filename: str = Field(min_length=1, max_length=255)
    storage_key: str = Field(min_length=1, max_length=512)
    mime_type: str | None = Field(default=None, max_length=120)
    file_size: int | None = Field(default=None, ge=0, le=50 * 1024 * 1024)
    content_sha256: str | None = Field(default=None, min_length=64, max_length=64)


class FeedbackResponseCreate(BaseModel):
    response_type: Literal["accepted", "correction", "additional_scope"]
    comments: str | None = Field(default=None, max_length=20_000)
    correction_description: str | None = Field(default=None, max_length=20_000)
    client_name: str | None = Field(default=None, max_length=255)
    client_email: EmailStr | None = None
    external_message_id: str | None = Field(default=None, max_length=255)
    attachments: list[FeedbackAttachmentCreate] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def require_negative_detail(self):
        if self.response_type != "accepted" and not (self.correction_description or "").strip():
            raise ValueError("Correction or additional-scope description is required")
        return self


class FeedbackClassification(BaseModel):
    classification: Literal["correction", "additional_scope"]
    remarks: str | None = Field(default=None, max_length=10_000)
    commercial_impact: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=12)


class NoFeedbackRecommendation(BaseModel):
    remarks: str = Field(min_length=3, max_length=10_000)


class DeemedAcceptanceCreate(BaseModel):
    authority_basis: str = Field(min_length=5, max_length=10_000)


class ReworkStageUpdate(BaseModel):
    stage: Literal["production", "qc", "qa", "delivered"]
    comments: str | None = Field(default=None, max_length=10_000)
    delivery_reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_delivery_reference(self):
        if self.stage == "delivered" and not (self.delivery_reference or "").strip():
            raise ValueError("Delivery reference is required for a rework delivery")
        return self


class ChangeRequestDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comments: str = Field(min_length=3, max_length=10_000)
    commercial_impact: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=12)


class _InvoiceFxFields(BaseModel):
    fx_rate_to_inr: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    fx_rate_mode: str | None = Field(default=None, max_length=30)
    fx_override_reason: str | None = Field(default=None, max_length=5000)

    @field_validator("fx_rate_mode", mode="before")
    @classmethod
    def normalize_fx_mode(cls, value):
        if value is None:
            return None
        return str(value).strip().upper() or None

    @field_validator("fx_override_reason", mode="before")
    @classmethod
    def normalize_fx_reason(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class InvoiceDraftCreate(_InvoiceFxFields):
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=16, decimal_places=2)
    tax_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    currency: str = Field(default="INR", min_length=3, max_length=3)
    payment_terms: str | None = Field(default=None, max_length=255)
    po_wo_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=10_000)
    # Optional traceability to the approved commercial revision / PM billing basis this invoice is prepared from.
    estimate_revision_id: int | None = Field(default=None, gt=0)
    billing_basis_id: int | None = Field(default=None, gt=0)
    billed_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    billed_milestone_id: int | None = Field(default=None, gt=0)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_invoice_currency(cls, value):
        code = str(value or "INR").strip().upper()
        if not is_supported_currency(code):
            raise ValueError(f"Unsupported ISO 4217 currency code: {code}")
        return code

    @model_validator(mode="after")
    def validate_dates_and_fx(self):
        if self.due_date < self.invoice_date:
            raise ValueError("Due date cannot be before invoice date")
        if self.fx_rate_to_inr is not None:
            mode = self.fx_rate_mode or "MANUAL_OVERRIDE"
            if self.currency != "INR" and mode not in OVERRIDE_MODES:
                raise ValueError("A manual FX rate must use an override/contract/bank-realization mode")
            if self.currency != "INR" and not self.fx_override_reason:
                raise ValueError("Reason is required when entering a manual FX rate")
        elif self.fx_rate_mode in OVERRIDE_MODES:
            raise ValueError("Manual FX mode requires fx_rate_to_inr")
        return self


class InvoiceRaise(_InvoiceFxFields):
    notes: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def validate_manual_fx(self):
        if self.fx_rate_to_inr is not None and not self.fx_override_reason:
            raise ValueError("Reason is required when entering a manual FX rate")
        if self.fx_rate_to_inr is None and self.fx_rate_mode in OVERRIDE_MODES:
            raise ValueError("Manual FX mode requires fx_rate_to_inr")
        return self


class InvoicePaymentCreate(_InvoiceFxFields):
    payment_reference: str = Field(min_length=1, max_length=180)
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    payment_mode: str = Field(default="bank_transfer", min_length=2, max_length=40)
    comments: str | None = Field(default=None, max_length=10_000)

    @model_validator(mode="after")
    def validate_manual_fx(self):
        if self.fx_rate_to_inr is not None and not self.fx_override_reason:
            raise ValueError("Reason is required when entering a manual FX rate")
        if self.fx_rate_to_inr is None and self.fx_rate_mode in OVERRIDE_MODES:
            raise ValueError("Manual FX mode requires fx_rate_to_inr")
        return self


class InvoiceClose(BaseModel):
    comments: str | None = Field(default=None, max_length=10_000)


class ProjectMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    recipient_user_id: int | None = Field(default=None, gt=0)
