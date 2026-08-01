from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re

from openpyxl import load_workbook
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Asset


DEVICE_TYPES = {"computer": "Computer", "laptop": "Laptop", "smartphone": "Smartphone", "mobile": "Smartphone"}

DEPARTMENT_MAP = {
    "ldr": "LiDAR",
    "lidar": "LiDAR",
    "lider": "LiDAR",
    "mapping": "Mapping",
    "ortho": "Ortho / GIS",
    "orthophoto": "Ortho / GIS",
    "ortho/gis": "Ortho / GIS",
    "pg": "Photogrammetry",
    "photogramettry": "Photogrammetry",
    "photogrammetry": "Photogrammetry",
    "bim": "BIM",
    "civil": "Civil",
    "drone": "Drone",
    "drone assembly": "Drone Assembly",
    "it": "IT",
    "management": "Management",
    "hr-management": "HR / Management",
    "hr- management": "HR / Management",
    "finance": "Finance",
    "bd": "Business Development",
    "gis cordinator": "GIS Coordination",
}


def _text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan"}:
        return None
    return text


def _clean_optional(value) -> str | None:
    text = _text(value)
    if text in {"-", "--", "N/a", "N/A", "n/a"}:
        return None
    return text


def _normalise_department(value) -> str | None:
    text = _clean_optional(value)
    if not text:
        return None
    key = re.sub(r"\s+", " ", text).strip().lower()
    return DEPARTMENT_MAP.get(key, text.title())


def _to_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _device_type(value) -> str | None:
    text = _clean_optional(value)
    if not text:
        return None
    return DEVICE_TYPES.get(text.lower())


def _work_mode(workstation: str | None, remarks: str | None) -> str:
    combined = f"{workstation or ''} {remarks or ''}".lower()
    if "wfh" in combined or "work from home" in combined:
        return "wfh"
    if "field" in combined or "feld" in combined:
        return "field"
    return "office"


def _location(workstation: str | None, work_mode: str) -> str:
    if work_mode == "wfh":
        return "Work From Home"
    if work_mode == "field":
        return "Field"
    text = (workstation or "").strip()
    if "floor" in text.lower() or text.lower() == "office":
        return text.title()
    return "Head Office"


def _status(used_by: str | None, work_mode: str, remarks: str | None) -> str:
    note = (remarks or "").lower()
    if "replacement pending" in note or "replace pending" in note:
        return "replacement_pending"
    if "missing" in note:
        return "missing"
    if "destroy" in note or "beyond repair" in note:
        return "beyond_repair"
    if "repair" in note or "not working" in note or "slow working" in note or "problem" in note:
        return "repair"
    if "returned" in note or "return to" in note or "returnrd" in note:
        return "returned"
    if work_mode == "wfh":
        return "wfh"
    if work_mode == "field":
        return "field_deployment"
    if not used_by or used_by == "-":
        return "available"
    return "assigned"


def _next_asset_number(db: Session, prefix: str) -> int:
    existing = db.scalars(select(Asset.asset_code).where(Asset.asset_code.like(f"{prefix}-%"))).all()
    numbers = []
    for code in existing:
        match = re.search(r"(\d+)$", code)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _code_prefix(device_type: str) -> str:
    return {"Computer": "NT-PC", "Laptop": "NT-LAP", "Smartphone": "NT-MOB"}.get(device_type, "NT-IT")


def _latest_sheet_name(workbook) -> str:
    month_numbers = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    ranked: list[tuple[int, int, str]] = []
    for name in workbook.sheetnames:
        match = re.search(r"([A-Za-z]+)[ -](\d{4})", name)
        if not match:
            continue
        month = month_numbers.get(match.group(1)[:3].lower())
        if month:
            ranked.append((int(match.group(2)), month, name))
    return max(ranked)[2] if ranked else workbook.sheetnames[0]


def import_nakshatech_workbook(db: Session, source: bytes | str | Path) -> dict:
    workbook = load_workbook(BytesIO(source) if isinstance(source, bytes) else source, data_only=True)
    sheet_name = _latest_sheet_name(workbook)
    ws = workbook[sheet_name]

    counters = {
        "NT-PC": _next_asset_number(db, "NT-PC"),
        "NT-LAP": _next_asset_number(db, "NT-LAP"),
        "NT-MOB": _next_asset_number(db, "NT-MOB"),
        "NT-IT": _next_asset_number(db, "NT-IT"),
    }
    result = {"sheet": sheet_name, "created": 0, "updated": 0, "skipped": 0, "errors": []}

    for row_number in range(2, ws.max_row + 1):
        values = [ws.cell(row_number, column).value for column in range(1, 26)]
        device_type = _device_type(values[9])
        if not device_type:
            continue

        used_by = _clean_optional(values[1])
        workstation = _clean_optional(values[2])
        remarks = _clean_optional(values[23])
        cpu_tag = _clean_optional(values[4])
        system_name = _clean_optional(values[8])
        work_mode = _work_mode(workstation, remarks)

        existing = None
        if cpu_tag and cpu_tag.upper() != "OWN":
            existing = db.scalar(select(Asset).where(Asset.cpu_asset_tag == cpu_tag))
        if not existing and system_name:
            existing = db.scalar(select(Asset).where(Asset.system_name == system_name, Asset.device_type == device_type))

        payload = dict(
            source_sheet=sheet_name,
            source_row=row_number,
            used_by=used_by,
            workstation_no=workstation,
            department=_normalise_department(values[3]),
            cpu_asset_tag=cpu_tag,
            monitor_asset_tags=_clean_optional(values[5]),
            mouse_asset_tag=_clean_optional(values[6]),
            keyboard_asset_tag=_clean_optional(values[7]),
            system_name=system_name,
            device_type=device_type,
            processor=_clean_optional(values[10]),
            memory_gb=_clean_optional(values[11]),
            ssd=_clean_optional(values[12]),
            hdd=_clean_optional(values[13]),
            ip_address=_clean_optional(values[14]),
            mac_address=_clean_optional(values[15]),
            graphics_card=_clean_optional(values[16]),
            operating_system=_clean_optional(values[17]),
            antivirus=_clean_optional(values[18]),
            network_type=_clean_optional(values[19]),
            performed_by=_clean_optional(values[20]),
            approved_by=_clean_optional(values[21]),
            price=float(values[22]) if isinstance(values[22], (int, float)) else None,
            remarks=remarks,
            asset_date=_to_date(values[24]),
            location=_location(workstation, work_mode),
            work_mode=work_mode,
            status=_status(used_by, work_mode, remarks),
        )

        if existing:
            for key, value in payload.items():
                setattr(existing, key, value)
            result["updated"] += 1
        else:
            prefix = _code_prefix(device_type)
            asset_code = f"{prefix}-{counters[prefix]:04d}"
            counters[prefix] += 1
            db.add(Asset(asset_code=asset_code, **payload))
            result["created"] += 1

    db.commit()
    return result


def import_assets_workbook(db: Session, content: bytes) -> dict:
    return import_nakshatech_workbook(db, content)
