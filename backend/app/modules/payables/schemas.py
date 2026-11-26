from __future__ import annotations
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field


class BillInput(BaseModel):
    bill_name: str = Field(min_length=2, max_length=220)
    bill_number: str = Field(min_length=1, max_length=120)
    bill_category: str = Field(min_length=2, max_length=100)
    vendor_name: str = Field(min_length=2, max_length=220)
    vendor_gstin: str | None = Field(default=None, max_length=15)
    bill_date: date
    due_date: date
    billing_period: str | None = Field(default=None, max_length=80)
    cost_center: str | None = Field(default=None, max_length=120)
    base_amount: Decimal = Field(gt=0, max_digits=13, decimal_places=2)
    gst_rate: Decimal = Field(default=Decimal('0'), ge=0, le=28, decimal_places=2)
    priority: Literal['normal', 'urgent'] = 'normal'
    remarks: str | None = Field(default=None, max_length=4000)


class DecisionInput(BaseModel):
    decision: Literal['approved', 'rejected']
    comment: str | None = Field(default=None, max_length=1000)
