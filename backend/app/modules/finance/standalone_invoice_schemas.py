from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

MONEY = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class StandalonePartyInput(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=3000)
    gstin: str | None = Field(default=None, max_length=32)
    pan: str | None = Field(default=None, max_length=20)
    email: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("company_name", "address", "gstin", "pan", "email", "phone", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class StandaloneSellerInput(StandalonePartyInput):
    msme_registration: str | None = Field(default=None, max_length=120)
    website: str | None = Field(default=None, max_length=255)


class StandaloneBankInput(BaseModel):
    bank_name: str | None = Field(default=None, max_length=255)
    account_name: str | None = Field(default=None, max_length=255)
    account_number: str | None = Field(default=None, max_length=80)
    ifsc_code: str | None = Field(default=None, max_length=30)
    swift_code: str | None = Field(default=None, max_length=30)
    bank_address: str | None = Field(default=None, max_length=1000)

    @field_validator("*", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value


class StandaloneLineItemInput(BaseModel):
    sequence: int = Field(ge=1, le=999)
    description: str = Field(min_length=1, max_length=500)
    detail: str | None = Field(default=None, max_length=3000)
    hsn_sac: str | None = Field(default=None, max_length=30)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: str = Field(min_length=1, max_length=30)
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    tax_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=6, decimal_places=2)
    tax_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)

    @field_validator("description", "detail", "hsn_sac", "unit", mode="before")
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_calculations(self):
        expected_amount = money(self.quantity * self.rate)
        if self.amount != expected_amount:
            raise ValueError(f"Line {self.sequence}: amount must equal quantity x rate ({expected_amount})")
        expected_tax = money(expected_amount * self.tax_percent / Decimal("100"))
        if self.tax_amount != expected_tax:
            raise ValueError(f"Line {self.sequence}: tax amount must equal amount x tax percent ({expected_tax})")
        return self


class StandaloneInvoiceCreate(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    terms: str | None = Field(default=None, max_length=255)
    due_date: date | None = None
    reference_work_order: str | None = Field(default=None, max_length=160)
    place_of_supply: str | None = Field(default=None, max_length=160)
    seller: StandaloneSellerInput
    bill_to: StandalonePartyInput
    ship_to: StandalonePartyInput
    bank: StandaloneBankInput = Field(default_factory=StandaloneBankInput)
    line_items: list[StandaloneLineItemInput] = Field(min_length=1, max_length=200)
    tax_mode: Literal["none", "cgst_sgst", "igst"] = "none"
    cgst_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=6, decimal_places=2)
    sgst_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=6, decimal_places=2)
    igst_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=6, decimal_places=2)
    notes: str | None = Field(default=None, max_length=10_000)
    terms_conditions: str | None = Field(default=None, max_length=20_000)
    authorized_signatory_name: str | None = Field(default=None, max_length=255)
    qr_data: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "invoice_number", "terms", "reference_work_order", "place_of_supply", "notes",
        "terms_conditions", "authorized_signatory_name", "qr_data", mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            return value.strip() or None
        return value

    @model_validator(mode="after")
    def validate_invoice(self):
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("Due date cannot be before invoice date")
        sequences = [item.sequence for item in self.line_items]
        if len(sequences) != len(set(sequences)):
            raise ValueError("Line item sequence numbers must be unique")
        expected_rate = Decimal("0")
        if self.tax_mode == "cgst_sgst":
            if self.igst_percent:
                raise ValueError("IGST cannot be combined with CGST/SGST")
            expected_rate = self.cgst_percent + self.sgst_percent
        elif self.tax_mode == "igst":
            if self.cgst_percent or self.sgst_percent:
                raise ValueError("CGST/SGST cannot be combined with IGST")
            expected_rate = self.igst_percent
        elif self.cgst_percent or self.sgst_percent or self.igst_percent:
            raise ValueError("Tax percentages require CGST/SGST or IGST mode")
        for item in self.line_items:
            if item.tax_percent != expected_rate:
                raise ValueError(
                    f"Line {item.sequence}: tax percent {item.tax_percent} must match invoice tax rate {expected_rate}"
                )
        return self
