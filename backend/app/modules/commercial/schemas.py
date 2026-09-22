from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.commercial.currencies import is_supported_currency
from app.modules.commercial.fx_service import OVERRIDE_MODES


class FxInputMixin(BaseModel):
    currency_code: str = Field(default="INR", min_length=3, max_length=3)
    fx_rate_to_inr: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    fx_rate_date: date | None = None
    fx_rate_mode: str | None = Field(default=None, max_length=30)
    fx_override_reason: str | None = Field(default=None, max_length=5000)

    @field_validator("currency_code", mode="before")
    @classmethod
    def normalize_currency_code(cls, value):
        code = str(value or "INR").strip().upper()
        if not is_supported_currency(code):
            raise ValueError(f"Unsupported ISO 4217 currency code: {code}")
        return code

    @field_validator("fx_rate_mode", mode="before")
    @classmethod
    def normalize_fx_mode(cls, value):
        if value is None:
            return None
        return str(value).strip().upper() or None

    @field_validator("fx_override_reason", mode="before")
    @classmethod
    def strip_override_reason(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_manual_fx(self):
        if self.fx_rate_to_inr is not None:
            mode = self.fx_rate_mode or "MANUAL_OVERRIDE"
            if mode not in OVERRIDE_MODES and self.currency_code != "INR":
                raise ValueError("A manual FX rate must use an override/contract/bank-realization mode")
            if self.currency_code != "INR" and not self.fx_override_reason:
                raise ValueError("Reason is required when entering a manual FX rate")
        elif self.fx_rate_mode in OVERRIDE_MODES:
            raise ValueError("Manual FX mode requires fx_rate_to_inr")
        return self


class FxPreviewRequest(FxInputMixin):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    event_date: date


BILLING_TYPES = {
    "fixed_price": "Fixed Price",
    "per_site": "Per Site",
    "per_sq_km": "Per Sq.Km",
    "per_km": "Per Km",
    "per_deliverable": "Per Deliverable",
    "milestone": "Milestone",
    "time_material": "Time & Material",
    "other": "Other",
    "unit_rate": "Unit Rate",   # legacy label kept so already-saved estimates stay valid
}
# Billing types priced as quantity x rate: the approved revision must carry a rate and a unit.
UNIT_RATE_BILLING_TYPES = {"per_site", "per_sq_km", "per_km", "per_deliverable", "unit_rate"}
# Types where Finance may also recommend quantity x rate when a rate happens to be recorded.
QUANTITY_BILLING_TYPES = UNIT_RATE_BILLING_TYPES | {"time_material"}
DEFAULT_QUANTITY_UNITS = {
    "per_site": "site", "per_sq_km": "sq.km", "per_km": "km", "per_deliverable": "deliverable",
    "unit_rate": "unit", "time_material": "hour",
}
_BILLING_ALIASES = {
    "fixed price": "fixed_price", "per site": "per_site", "per sq.km": "per_sq_km", "per sq km": "per_sq_km",
    "per sqkm": "per_sq_km", "per km": "per_km", "per deliverable": "per_deliverable", "milestone": "milestone",
    "time & material": "time_material", "time and material": "time_material", "time_and_material": "time_material",
    "t&m": "time_material", "other": "other", "unit rate": "unit_rate",
}


def normalize_billing_type(value: str | None) -> str:
    raw = (value or "").strip().lower()
    code = _BILLING_ALIASES.get(raw, raw.replace("-", "_").replace(" ", "_"))
    if code not in BILLING_TYPES:
        raise ValueError("Unsupported billing type: choose Fixed Price, Per Site, Per Sq.Km, Per Km, Per Deliverable, Milestone, Time & Material or Other")
    return code


class EstimateMilestoneInput(BaseModel):
    milestone_name: str = Field(min_length=2, max_length=255)
    percent: Decimal | None = Field(default=None, gt=0, le=100, max_digits=6, decimal_places=2)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)

    @field_validator("milestone_name", mode="before")
    @classmethod
    def strip_milestone_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def percent_or_amount(self):
        if self.percent is None and self.amount is None:
            raise ValueError("Each milestone needs a percentage or an amount")
        return self


class CommercialEstimateInput(FxInputMixin):
    quotation_reference: str | None = Field(default=None, max_length=160)
    po_wo_reference: str | None = Field(default=None, max_length=160)
    scope_description: str = Field(min_length=2, max_length=20_000)
    billing_type: str = Field(default="fixed_price", min_length=2, max_length=30)
    payment_terms: str | None = Field(default=None, max_length=255)
    expected_billing_milestone: str | None = Field(default=None, max_length=255)
    projected_payment_date: date | None = None
    notes: str | None = Field(default=None, max_length=10_000)
    estimated_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    taxable_base_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    tax_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=6, decimal_places=2)
    estimated_direct_cost_inr: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    unit_rate: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    estimated_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    quantity_unit: str | None = Field(default=None, max_length=30)
    milestones: list[EstimateMilestoneInput] = Field(default_factory=list, max_length=30)
    estimate_date: date
    reason: str | None = Field(default=None, max_length=10_000)

    @field_validator(
        "quotation_reference", "po_wo_reference", "scope_description", "billing_type",
        "payment_terms", "expected_billing_milestone", "notes", "reason", "quantity_unit", mode="before",
    )
    @classmethod
    def strip_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def normalize_taxable_base(self):
        if self.taxable_base_amount is None:
            self.taxable_base_amount = self.estimated_amount
        if self.taxable_base_amount > self.estimated_amount:
            # Headline contract value may be net or gross in old data, but for new explicit estimates
            # taxable base cannot exceed the entered commercial amount.
            raise ValueError("Taxable base amount cannot exceed estimated amount")
        self.billing_type = normalize_billing_type(self.billing_type)
        if self.billing_type in UNIT_RATE_BILLING_TYPES:
            if self.unit_rate is None:
                raise ValueError("A rate per unit is required for this billing type")
            if not self.quantity_unit:
                self.quantity_unit = DEFAULT_QUANTITY_UNITS[self.billing_type]
        elif self.billing_type == "time_material" and self.unit_rate is not None and not self.quantity_unit:
            self.quantity_unit = DEFAULT_QUANTITY_UNITS["time_material"]
        if self.billing_type == "milestone":
            if not self.milestones:
                raise ValueError("Milestone billing needs at least one billing milestone")
            total_percent = sum((m.percent or Decimal("0")) for m in self.milestones)
            if total_percent > Decimal("100.00"):
                raise ValueError("Milestone percentages cannot add up to more than 100%")
            names = [m.milestone_name.lower() for m in self.milestones]
            if len(set(names)) != len(names):
                raise ValueError("Milestone names must be unique")
        elif self.milestones:
            raise ValueError("Milestones apply only to Milestone billing")
        return self


class ProjectCommercialInput(CommercialEstimateInput):
    """Initial Commercial & Billing Details (Revision 1) entered on the Create Project form."""

    estimate_date: date = Field(default_factory=date.today)

    @model_validator(mode="after")
    def require_initial_commercial_terms(self):
        if not self.payment_terms or len(self.payment_terms) < 2:
            raise ValueError("Payment terms are required (for example: 30 days, or 30% advance / 70% on delivery)")
        return self


class CommercialEstimateDecision(BaseModel):
    decision: Literal["approve", "reject", "return"]
    comments: str = Field(min_length=2, max_length=10_000)

    @field_validator("comments", mode="before")
    @classmethod
    def strip_comments(cls, value):
        return str(value or "").strip()


class ProjectExpenseInput(BaseModel):
    expense_date: date
    category: str = Field(min_length=2, max_length=40)
    purpose: str = Field(min_length=2, max_length=10_000)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_source: Literal["EMPLOYEE_PAID", "COMPANY_PAID"] = "EMPLOYEE_PAID"
    remarks: str | None = Field(default=None, max_length=5000)
    phase_key: str = Field(default="ORIGINAL", min_length=2, max_length=30)
    linked_vendor_invoice_id: int | None = Field(default=None, gt=0)

    @field_validator("category", "purpose", "remarks", "phase_key", mode="before")
    @classmethod
    def strip_expense_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ProjectExpenseDecision(BaseModel):
    decision: Literal["approve", "return", "reject"]
    approved_amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    comments: str = Field(min_length=2, max_length=10_000)
    adjustment_reason: str | None = Field(default=None, max_length=5000)

    @field_validator("comments", "adjustment_reason", mode="before")
    @classmethod
    def strip_expense_decision_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_approval(self):
        if self.decision == "approve" and self.approved_amount is None:
            raise ValueError("Approved amount is required for Finance approval")
        if self.decision != "approve" and self.approved_amount is not None:
            raise ValueError("Approved amount is only valid for an approval decision")
        return self


class ProjectExpenseReimbursement(BaseModel):
    reimbursement_reference: str = Field(min_length=2, max_length=180)
    comments: str | None = Field(default=None, max_length=5000)

    @field_validator("reimbursement_reference", "comments", mode="before")
    @classmethod
    def strip_reimbursement_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class ProjectExpenseDeclarationInput(BaseModel):
    phase_key: str = Field(default="ORIGINAL", min_length=2, max_length=30)
    declaration_status: Literal["HAS_EXPENSES", "NO_MORE_EXPENSES"]

    @field_validator("phase_key", mode="before")
    @classmethod
    def normalize_phase(cls, value):
        return str(value or "ORIGINAL").strip().upper()


class VendorInvoiceInput(FxInputMixin):
    vendor_name: str = Field(min_length=2, max_length=255)
    vendor_gstin: str | None = Field(default=None, max_length=32)
    invoice_number: str = Field(min_length=1, max_length=100)
    invoice_date: date
    due_date: date | None = None
    po_wo_reference: str | None = Field(default=None, max_length=160)
    category: str = Field(min_length=2, max_length=40)
    description: str = Field(min_length=2, max_length=10_000)
    hsn_sac: str | None = Field(default=None, max_length=20)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=3)
    rate: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    taxable_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    cgst: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    sgst: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    igst: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    other_tax: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=18, decimal_places=2)
    payment_source: Literal["COMPANY_PAID", "EMPLOYEE_PAID"] = "COMPANY_PAID"
    linked_employee_expense_id: int | None = Field(default=None, gt=0)
    remarks: str | None = Field(default=None, max_length=5000)

    @field_validator(
        "vendor_name", "vendor_gstin", "invoice_number", "po_wo_reference", "category",
        "description", "hsn_sac", "remarks", mode="before",
    )
    @classmethod
    def strip_vendor_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_vendor_dates_and_link(self):
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("Vendor invoice due date cannot be before invoice date")
        if self.payment_source == "EMPLOYEE_PAID" and self.linked_employee_expense_id is None:
            raise ValueError("Employee-paid vendor invoices must link to the corresponding employee expense")
        if self.payment_source == "COMPANY_PAID" and self.linked_employee_expense_id is not None:
            raise ValueError("Company-paid vendor invoices must not link to an employee reimbursement")
        return self


class VendorPaymentInput(FxInputMixin):
    payment_date: date
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    payment_reference: str | None = Field(default=None, max_length=180)
    payment_mode: str = Field(default="bank_transfer", min_length=2, max_length=40)

    @field_validator("payment_reference", "payment_mode", mode="before")
    @classmethod
    def strip_vendor_payment_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class AttachmentMetadataInput(BaseModel):
    owner_type: Literal["ESTIMATE_REVISION", "EXPENSE", "VENDOR_INVOICE", "CLIENT_INVOICE"]
    owner_id: int = Field(gt=0)
    doc_type: Literal["QUOTATION", "PO", "WO", "APPROVAL", "RECEIPT", "INVOICE", "OTHER"] = "OTHER"


class BillingBasisInput(BaseModel):
    """PM confirmation of what is billable. Operational facts only: no rate, value, FX or margin field exists here."""

    cumulative_billable_quantity: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=3)
    quantity_unit: str | None = Field(default=None, max_length=30)
    milestone_id: int | None = Field(default=None, gt=0)
    completion_percent: Decimal | None = Field(default=None, ge=0, le=100, max_digits=5, decimal_places=2)
    delivery_accepted: bool = False
    acceptance_reference: str | None = Field(default=None, max_length=255)
    pm_remarks: str | None = Field(default=None, max_length=5000)
    billing_readiness_date: date | None = None

    @field_validator("quantity_unit", "acceptance_reference", "pm_remarks", mode="before")
    @classmethod
    def strip_basis_text(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value
