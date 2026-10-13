from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.modules.finance.advance import ADVANCE_FOLLOWUP_CHANNELS, ADVANCE_PAYMENT_MODES


class ClientAdvanceTransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("100000000000"), max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    payment_date: date
    payment_mode: str = Field(min_length=2, max_length=30)
    reference_number: str | None = Field(default=None, max_length=160)
    bank_reference: str | None = Field(default=None, max_length=160)
    attachment: str | None = Field(default=None, max_length=512)

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, value):
        return value.strip().upper() if isinstance(value, str) else value

    @field_validator("payment_mode", mode="before")
    @classmethod
    def normalize_payment_mode(cls, value):
        normalized = value.strip().lower().replace(" ", "_") if isinstance(value, str) else value
        if normalized not in ADVANCE_PAYMENT_MODES:
            raise ValueError(f"Payment mode must be one of: {', '.join(ADVANCE_PAYMENT_MODES)}")
        return normalized

    @field_validator("reference_number", "bank_reference", "attachment", mode="before")
    @classmethod
    def strip_optional_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ClientAdvanceApplyToInvoice(BaseModel):
    """Settle an invoice with money already received as a client advance.

    The amount is written back onto the existing client-advance receipt rows
    (``adjusted_invoice_id`` / ``adjusted_amount_inr`` / ``adjusted_at``). No
    duplicate invoice payment and no invoice face-value change is ever created.
    """

    invoice_id: int = Field(gt=0)
    amount: Decimal = Field(gt=0, le=Decimal("100000000000"), max_digits=18, decimal_places=2)
    remarks: str | None = Field(default=None, max_length=5_000)

    @field_validator("remarks", mode="before")
    @classmethod
    def strip_apply_remarks(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ClientAdvanceFollowUpCreate(BaseModel):
    contact_person: str = Field(min_length=2, max_length=255)
    communication_type: str = Field(min_length=2, max_length=30)
    remarks: str = Field(min_length=2, max_length=5000)
    next_followup_date: date | None = None

    @field_validator("communication_type", mode="before")
    @classmethod
    def normalize_communication_type(cls, value):
        normalized = value.strip().lower().replace(" ", "_") if isinstance(value, str) else value
        if normalized not in ADVANCE_FOLLOWUP_CHANNELS:
            raise ValueError(
                f"Communication type must be one of: {', '.join(ADVANCE_FOLLOWUP_CHANNELS)}"
            )
        return normalized

    @field_validator("contact_person", "remarks", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value
