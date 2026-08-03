from __future__ import annotations

from datetime import datetime
import re
from zoneinfo import ZoneInfo

from fastapi import HTTPException

IST = ZoneInfo("Asia/Kolkata")
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def current_reporting_month() -> str:
    return datetime.now(IST).strftime("%Y-%m")


def normalize_reporting_month(value: str | None) -> str:
    month = (value or current_reporting_month()).strip()
    if not MONTH_PATTERN.fullmatch(month):
        raise HTTPException(status_code=400, detail="Reporting month must be in YYYY-MM format")
    return month
