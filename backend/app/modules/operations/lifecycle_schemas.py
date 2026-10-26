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


class ManualFeedbackResponseCreate(BaseModel):
    """BD records an offline client outcome (call, email or letter) that never
    arrived through the secure client feedback link."""

    response_type: Literal["accepted", "correction", "additional_scope"]
    comments: str = Field(min_length=3, max_length=20_000)
    correction_description: str | None = Field(default=None, max_length=20_000)
    client_name: str | None = Field(default=None, max_length=255)
    reference: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def require_negative_detail(self):
        if self.response_type != "accepted" and not (self.correction_description or "").strip():
            raise ValueError("Correction or additional-scope description is required")
        return self


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


class InvoiceLineItemCreate(BaseModel):
    """One Invoice Generation V2 line item. ``amount`` must equal ``quantity * rate``."""

    sequence: int = Field(ge=1, le=999)
    description: str = Field(min_length=1, max_length=2000)
    hsn_sac: str | None = Field(default=None, max_length=20)
    unit: str = Field(default="Nos", min_length=1, max_length=30)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    @field_validator("description", "unit", mode="before")
    @classmethod
    def strip_text(cls, value):
        return str(value).strip() if isinstance(value, str) else value

    @field_validator("hsn_sac", mode="before")
    @classmethod
    def normalize_hsn(cls, value):
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_line_amount(self):
        expected = (self.quantity * self.rate).quantize(Decimal("0.01"))
        if abs(expected - self.amount) > Decimal("0.01"):
            raise ValueError(
                f"Line item {self.sequence}: amount {self.amount} does not match quantity x rate ({expected})"
            )
        return self


class InvoiceBillingSnapshotOverride(BaseModel):
    """Optional Manual-mode overrides for the billing/company/bank snapshot.

    Any field left blank falls back to the live Client Master / app configuration value
    at invoice-creation time, exactly as Auto Fill mode does. Once captured, the snapshot
    never changes even if the Client Master or company configuration changes later.
    """

    billing_name: str | None = Field(default=None, max_length=255)
    billing_address: str | None = Field(default=None, max_length=2000)
    billing_gstin: str | None = Field(default=None, max_length=20)
    billing_pan: str | None = Field(default=None, max_length=20)
    billing_email: str | None = Field(default=None, max_length=255)
    billing_phone: str | None = Field(default=None, max_length=40)
    company_name: str | None = Field(default=None, max_length=255)
    company_address: str | None = Field(default=None, max_length=2000)
    company_gstin: str | None = Field(default=None, max_length=20)
    company_pan: str | None = Field(default=None, max_length=20)
    company_phone: str | None = Field(default=None, max_length=40)
    company_email: str | None = Field(default=None, max_length=255)
    company_website: str | None = Field(default=None, max_length=255)
    company_hsn_sac: str | None = Field(default=None, max_length=20)
    bank_name: str | None = Field(default=None, max_length=255)
    bank_account_name: str | None = Field(default=None, max_length=255)
    bank_account_number: str | None = Field(default=None, max_length=60)
    bank_ifsc: str | None = Field(default=None, max_length=20)
    bank_swift: str | None = Field(default=None, max_length=20)
    bank_branch: str | None = Field(default=None, max_length=255)

    @field_validator("*", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class InvoiceUpdate(BaseModel):
    """Safe edit of an EXISTING invoice (never a duplicate). Only provided fields change.

    ``theme``/``notes``/``payment_terms`` are presentation-only; the remaining fields are
    MATERIAL — they are refused once payments or a Bad Debt case exist, and they invalidate a
    previous signature so it can never represent changed financial content.
    """

    theme: Literal["blue_classic", "blue_topographic", "green_gold_premium"] | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    payment_terms: str | None = Field(default=None, max_length=255)
    po_wo_reference: str | None = Field(default=None, max_length=160)
    place_of_supply: str | None = Field(default=None, max_length=160)
    invoice_date: date | None = None
    due_date: date | None = None
    work_order_date: date | None = None
    dispatch_date: date | None = None
    dispatch_details: str | None = Field(default=None, max_length=255)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)
    tax_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    tax_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    # Switching GST type clears the split fields that no longer apply ("none" clears all).
    gst_mode: Literal["none", "cgst_sgst", "igst"] | None = None
    cgst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    cgst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    sgst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    sgst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    igst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    igst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)


class InvoiceSign(BaseModel):
    """Optional remarks recorded with the authorised-signatory approval."""

    remarks: str | None = Field(default=None, max_length=2000)


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
    # V8.7 A4 presentation theme chosen by Finance. Stored on the invoice so it is restored
    # on reload; omitted/NULL keeps the legacy classic design.
    theme: Literal["blue_classic", "blue_topographic", "green_gold_premium"] | None = None

    # --- Invoice Generation V2 (additive; all optional, legacy behaviour when omitted) ----
    entry_mode: Literal["auto_fill", "manual"] | None = None
    line_items: list[InvoiceLineItemCreate] = Field(default_factory=list, max_length=200)
    cgst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    cgst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    sgst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    sgst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    igst_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=6, decimal_places=2)
    igst_amount: Decimal | None = Field(default=None, ge=0, max_digits=16, decimal_places=2)
    work_order_date: date | None = None
    dispatch_details: str | None = Field(default=None, max_length=255)
    dispatch_date: date | None = None
    place_of_supply: str | None = Field(default=None, max_length=160)
    billing_snapshot: InvoiceBillingSnapshotOverride | None = None

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

    @model_validator(mode="after")
    def validate_line_items_and_gst_reconciliation(self):
        tolerance = Decimal("0.01")
        if self.line_items:
            sequences = [item.sequence for item in self.line_items]
            if len(set(sequences)) != len(sequences):
                raise ValueError("Line item sequence numbers must be unique")
            line_total = sum((item.amount for item in self.line_items), Decimal("0"))
            if abs(line_total - self.amount) > tolerance:
                raise ValueError(
                    f"Sum of line item amounts ({line_total}) must equal the taxable amount ({self.amount})"
                )

        gst_fields = (self.cgst_amount, self.sgst_amount, self.igst_amount)
        if any(value is not None for value in gst_fields):
            cgst = self.cgst_amount or Decimal("0")
            sgst = self.sgst_amount or Decimal("0")
            igst = self.igst_amount or Decimal("0")
            if igst > 0 and (cgst > 0 or sgst > 0):
                raise ValueError("IGST cannot be combined with CGST/SGST on the same invoice")
            gst_total = cgst + sgst + igst
            if abs(gst_total - self.tax_amount) > tolerance:
                raise ValueError(
                    f"CGST + SGST + IGST ({gst_total}) must equal the tax amount ({self.tax_amount})"
                )
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


class BadDebtProposalCreate(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)
    collection_attempts: str = Field(min_length=3, max_length=4000)
    last_followup_date: date | None = None
    finance_remarks: str | None = Field(default=None, max_length=4000)
    # Optional partial write-off. Omitted/None = the full collectible balance.
    proposed_amount: Decimal | None = Field(default=None, gt=0, max_digits=16, decimal_places=2)


class BadDebtDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comments: str = Field(min_length=3, max_length=4000)


class BadDebtRecoveryCreate(BaseModel):
    """Client pays back part/all of a Management-approved Bad Debt write-off."""

    amount: Decimal = Field(gt=0, max_digits=16, decimal_places=2)
    payment_date: date
    payment_reference: str = Field(min_length=1, max_length=180)
    payment_mode: str = Field(default="bank_transfer", min_length=2, max_length=40)
    remarks: str | None = Field(default=None, max_length=4000)


class ProjectMessageCreate(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)
    recipient_user_id: int | None = Field(default=None, gt=0)
