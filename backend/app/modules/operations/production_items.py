"""Optional FILE / TILE / ITEM tracking for work packages (V8.2, additive).

Extends the EXISTING authoritative work-package engine with an OPTIONAL per-area
file/tile/item child (``WorkPackageItem``) and an append-only per-file stage
activity log (``WorkPackageItemActivity``) for production / QC / QA / delivery.

Invariants:
- File tracking is OPTIONAL: packages with zero items keep working with area-level
  tracking exactly as before.
- Nothing is ever hard-deleted: an incorrect file is deactivated (``is_active``)
  and its activity history stays.
- Durations come from real ``started_at`` / ``ended_at`` timestamps (backend
  clock), never typed in, and cross-midnight sessions compute correctly.
- The one-day (configurable) buffer NEVER rewrites the original target date.
- Authorization mirrors the existing workflow contract: PM/Team Lead manage
  files; Production/QC/QA act only on their own assignments; Management/Admin
  are read-only. Work is always recorded under the ACTOR'S OWN user id.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceProject
from app.modules.notifications.service import create_global_notification
from app.modules.operations.models import (
    OrthoProjectMember,
    OrthoWorkPackage,
    WorkPackageItem,
    WorkPackageItemActivity,
)

ADMIN_ROLE = "admin"
MANAGEMENT_ROLE = "management"
EMPLOYEE_ROLE = "employee"

ITEM_STAGES: tuple[str, ...] = ("production", "qc", "qa", "delivery")
TIMED_STAGES: tuple[str, ...] = ("production", "qc", "qa")
STAGE_ASSIGN_ATTR: dict[str, str] = {
    "production": "production_user_id",
    "qc": "qc_user_id",
    "qa": "qa_user_id",
}

ITEM_STATUS_PRODUCTION_DONE = "production_completed"
ITEM_STATUS_QC_PASSED = "qc_passed"
ITEM_STATUS_QC_REJECTED = "qc_rejected"
ITEM_STATUS_QA_PASSED = "qa_passed"
ITEM_STATUS_QA_REJECTED = "qa_rejected"
ITEM_STATUS_DELIVERED = "delivered"

DELAY_CATEGORIES: tuple[str, ...] = (
    "Normal Work",
    "Large / Complex Building Data",
    "Heavy File / High Data Volume",
    "Poor Input Data Quality",
    "Rework / Correction",
    "System Malfunction",
    "Software Performance Issue",
    "Network / Server Issue",
    "Waiting for Required Data",
    "Other",
)

_REVIEW_STATUS_ALIASES = {
    "pass": "passed", "passed": "passed", "approve": "passed", "approved": "passed", "ok": "passed",
    "reject": "rejected", "rejected": "rejected", "fail": "rejected", "failed": "rejected",
    "rework": "rework", "changes_requested": "rework",
}

_PRODUCTION_STATUSES = ("completed", "in_progress", "blocked")


# ===========================================================================================
# Deadline / one-day buffer
# ===========================================================================================

def buffer_days_for(package: OrthoWorkPackage) -> int:
    """Per-package override, else the configurable global default (1 day)."""
    if package.production_buffer_days is not None:
        return max(0, int(package.production_buffer_days))
    return max(0, int(settings.production_buffer_days))


def deadline_status(
    package: OrthoWorkPackage,
    *,
    completed_at: datetime | date | None = None,
    today: date | None = None,
) -> dict:
    """Buffer/overdue state for one area. NEVER modifies target_date.

    Incomplete: before target = on_track, on target = due_today, within buffer =
    buffer_day, after buffer = overdue (+ days_overdue). Complete: on/before
    target = completed_on_time, within buffer = completed_in_buffer, after
    buffer = completed_late.
    """
    base = package.production_target_date or package.target_date
    days = buffer_days_for(package)
    today = today or date.today()
    if base is None:
        return {
            "target_date": None,
            "production_target_date": package.production_target_date.isoformat() if package.production_target_date else None,
            "buffer_days": days,
            "buffer_until": None,
            "status": "no_target",
            "days_overdue": 0,
        }
    buffer_until = base + timedelta(days=days)
    row = {
        "target_date": base.isoformat(),
        "production_target_date": package.production_target_date.isoformat() if package.production_target_date else None,
        "buffer_days": days,
        "buffer_until": buffer_until.isoformat(),
        "status": "no_target",
        "days_overdue": 0,
    }
    if completed_at is not None:
        done = completed_at.date() if isinstance(completed_at, datetime) else completed_at
        if done <= base:
            row["status"] = "completed_on_time"
        elif done <= buffer_until:
            row["status"] = "completed_in_buffer"
        else:
            row["status"] = "completed_late"
        row["days_late"] = max(0, (done - buffer_until).days)
        return row
    if today < base:
        row["status"] = "on_track"
    elif today == base:
        row["status"] = "due_today"
    elif today <= buffer_until:
        row["status"] = "buffer_day"
    else:
        row["status"] = "overdue"
        row["days_overdue"] = (today - buffer_until).days
    return row


# ===========================================================================================
# Context / authorization
# ===========================================================================================

def stage_deadline_status(
    target_date: date | None,
    *,
    completed_at: datetime | date | None = None,
    today: date | None = None,
) -> dict:
    """QC / QA stage deadline — NO buffer (buffer applies to Production only).

    Incomplete: not_due / due_today / overdue (+ days_overdue).
    Complete: completed_on_time (on/before target) / completed_late.
    """
    today = today or date.today()
    if target_date is None:
        return {"target_date": None, "status": "no_target", "days_overdue": 0}
    row = {"target_date": target_date.isoformat(), "status": "no_target", "days_overdue": 0}
    if completed_at is not None:
        done = completed_at.date() if isinstance(completed_at, datetime) else completed_at
        row["status"] = "completed_on_time" if done <= target_date else "completed_late"
        row["days_late"] = max(0, (done - target_date).days)
        return row
    if today < target_date:
        row["status"] = "not_due"
    elif today == target_date:
        row["status"] = "due_today"
    else:
        row["status"] = "overdue"
        row["days_overdue"] = (today - target_date).days
    return row


def item_stage_deadline(
    item: WorkPackageItem,
    stage: str,
    *,
    latest: dict[str, WorkPackageItemActivity] | None = None,
    today: date | None = None,
) -> dict:
    """Deadline for one file stage using the per-file targets (authoritative)."""
    latest = latest or {}
    activity = latest.get(stage)
    completed_at = activity.ended_at if activity is not None and activity.ended_at else None
    if stage == "production":
        # Production keeps the 1-day buffer (same semantics as the area-level helper).
        target = item.production_target_date
        if target is None:
            return {"target_date": None, "status": "no_target", "days_overdue": 0}
        buffer_until = target + timedelta(days=1)
        row = {
            "target_date": target.isoformat(),
            "buffer_until": buffer_until.isoformat(),
            "status": "no_target",
            "days_overdue": 0,
        }
        if completed_at is not None:
            done = completed_at.date()
            if done <= target:
                row["status"] = "completed_on_time"
            elif done <= buffer_until:
                row["status"] = "completed_in_buffer"
            else:
                row["status"] = "completed_late"
                row["days_late"] = max(0, (done - buffer_until).days)
            return row
        today = today or date.today()
        if today < target:
            row["status"] = "on_track"
        elif today == target:
            row["status"] = "due_today"
        elif today <= buffer_until:
            row["status"] = "buffer_day"
        else:
            row["status"] = "overdue"
            row["days_overdue"] = (today - buffer_until).days
        return row
    if stage == "qc":
        return stage_deadline_status(item.qc_target_date, completed_at=completed_at, today=today)
    if stage == "qa":
        return stage_deadline_status(item.qa_target_date, completed_at=completed_at, today=today)
    return {"target_date": None, "status": "no_target", "days_overdue": 0}


def _notify(
    db: Session,
    *,
    event_type: str,
    title: str,
    message: str,
    recipient_ids: Iterable[int | None],
    target_url: str | None,
    dedupe_key: str | None = None,
) -> None:
    recipients = sorted({int(uid) for uid in recipient_ids if uid})
    if not recipients:
        return
    create_global_notification(
        db,
        event_type=event_type,
        title=title,
        message=message,
        category="system",
        target_url=target_url,
        recipient_user_ids=recipients,
        dedupe_key=dedupe_key,
    )


def load_package(db: Session, work_package_id: int) -> OrthoWorkPackage:
    package = db.get(OrthoWorkPackage, work_package_id)
    if package is None:
        raise ValueError("Work package not found")
    return package


def load_item(db: Session, work_package_item_id: int) -> WorkPackageItem:
    item = db.get(WorkPackageItem, work_package_item_id)
    if item is None:
        raise ValueError("File not found")
    return item


def _project(db: Session, project_id: int) -> FinanceProject | None:
    return db.get(FinanceProject, project_id)


def actor_context(db: Session, package: OrthoWorkPackage, actor: User, role: str) -> dict:
    project = _project(db, package.project_id)
    pm_id = None
    if project is not None and project.master_profile is not None:
        pm_id = project.master_profile.project_manager_id
    is_pm = pm_id == actor.id
    is_tl = package.team_leader_user_id == actor.id
    if not is_tl:
        # Freshly imported areas have no per-package Team Lead yet: the PM-approved
        # project Team Lead (OrthoProjectMember) is authoritative until allocation sets it.
        is_tl = db.scalar(select(OrthoProjectMember.id).where(
            OrthoProjectMember.project_id == package.project_id,
            OrthoProjectMember.user_id == actor.id,
            OrthoProjectMember.member_role == "team_leader",
            OrthoProjectMember.is_active.is_(True),
        ).limit(1)) is not None
    read_only_role = role in {ADMIN_ROLE, MANAGEMENT_ROLE}
    return {
        "project": project,
        "pm_id": pm_id,
        "is_pm": is_pm,
        "is_tl": is_tl,
        "read_only_role": read_only_role,
        # PM and Team Lead manage files. Management/Admin stay READ-ONLY.
        "can_manage": (is_pm or is_tl) and not read_only_role,
        "privileged": is_pm or is_tl or read_only_role,
    }


def _ensure_mutable(ctx: dict) -> None:
    if ctx["read_only_role"]:
        raise PermissionError("Management/Admin access is read-only")
    if not ctx["can_manage"]:
        raise PermissionError("Only the Team Lead or Project Manager can manage files for this area")


def _ensure_stage_actor(
    db: Session, package: OrthoWorkPackage, item: WorkPackageItem, actor: User, role: str, stage: str
) -> str:
    """Return the performed_role for the actor; raise when not allowed."""
    ctx = actor_context(db, package, actor, role)
    if ctx["read_only_role"]:
        raise PermissionError("Management/Admin access is read-only")
    if stage == "production":
        if actor.id in {item.production_user_id, package.team_leader_user_id, ctx["pm_id"]}:
            if ctx["is_pm"]:
                return "project_manager"
            if ctx["is_tl"]:
                return "team_leader"
            return "production"
        raise PermissionError(
            "Only the Production employee assigned to this file, the Team Lead or the Project Manager can record Production"
        )
    if stage == "qc":
        if item.qc_user_id != actor.id:
            raise PermissionError("Only the QC employee assigned to this file can record QC")
        return "qc"
    if stage == "qa":
        if item.qa_user_id != actor.id:
            raise PermissionError("Only the QA employee assigned to this file can record QA")
        return "qa"
    raise ValueError(f"Unsupported stage: {stage}")


def _ensure_assignable(
    db: Session, package: OrthoWorkPackage, actor_ctx: dict, user_id: int, stage: str
) -> None:
    """Assignee must be an active team member for that role, the TL or the PM."""
    if user_id in {package.team_leader_user_id, actor_ctx["pm_id"]}:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ValueError("Assignee must be an active employee account")
    rows = db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == package.project_id,
        OrthoProjectMember.user_id == user_id,
        OrthoProjectMember.is_active.is_(True),
    )).all()
    if stage not in {row.member_role for row in rows}:
        raise ValueError(
            f"Assignee must be a PM-approved project team member assigned to the {stage.upper()} role"
        )


# ===========================================================================================
# Normalizers / validation
# ===========================================================================================

def normalize_review_status(value: str | None) -> str:
    v = (value or "").strip().lower()
    if v not in _REVIEW_STATUS_ALIASES:
        raise ValueError("Status must be one of: passed, rejected, rework")
    return _REVIEW_STATUS_ALIASES[v]


def normalize_production_status(value: str | None) -> str:
    v = (value or "completed").strip().lower()
    if v not in _PRODUCTION_STATUSES:
        raise ValueError("Production status must be one of: completed, in_progress, blocked")
    return v


def normalize_delay(
    delay_category: str | None,
    system_malfunction: bool,
) -> tuple[str | None, bool]:
    category = (delay_category or "").strip() or None
    if category is not None:
        match = next((c for c in DELAY_CATEGORIES if c.lower() == category.lower()), None)
        if match is None:
            raise ValueError(f"Unknown delay category. Allowed: {', '.join(DELAY_CATEGORIES)}")
        category = match
        if match == "System Malfunction":
            system_malfunction = True
    return category, bool(system_malfunction)


def _clean_number(value: Any) -> Decimal | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid quantity: {value!r}") from exc


# ===========================================================================================
# File management (Team Lead / PM)
# ===========================================================================================

def add_items(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_id: int,
    entries: list[dict],
) -> list[WorkPackageItem]:
    """Add one or many files. Duplicate file numbers fail loudly (nothing partial)."""
    package = load_package(db, work_package_id)
    ctx = actor_context(db, package, actor, role)
    _ensure_mutable(ctx)
    if not entries:
        raise ValueError("At least one file entry is required")

    existing = set(db.scalars(select(WorkPackageItem.item_number).where(
        WorkPackageItem.work_package_id == package.id
    )).all())
    seen: set[str] = set()
    duplicates: list[str] = []
    cleaned: list[dict] = []
    for entry in entries:
        number = (entry.get("item_number") or "").strip()
        if not number:
            raise ValueError("File number is required for every file")
        if len(number) > 120:
            raise ValueError(f"File number too long: {number[:40]}…")
        if number in existing or number in seen:
            duplicates.append(number)
            continue
        seen.add(number)
        cleaned.append({**entry, "item_number": number})
    if duplicates:
        raise ValueError(
            f"Duplicate file number(s) in this area: {', '.join(sorted(set(duplicates)))}. Nothing was created."
        )

    created: list[WorkPackageItem] = []
    for index, entry in enumerate(cleaned, start=1):
        for stage, key in STAGE_ASSIGN_ATTR.items():
            uid = entry.get(key)
            if uid:
                _ensure_assignable(db, package, ctx, int(uid), stage)
        item = WorkPackageItem(
            work_package_id=package.id,
            project_id=package.project_id,
            item_number=entry["item_number"],
            item_name=(entry.get("item_name") or "").strip() or None,
            sequence_no=entry.get("sequence_no") if entry.get("sequence_no") is not None else index,
            planned_quantity=_clean_number(entry.get("planned_quantity")),
            planned_unit=(entry.get("planned_unit") or "").strip() or None,
            production_user_id=int(entry["production_user_id"]) if entry.get("production_user_id") else None,
            qc_user_id=int(entry["qc_user_id"]) if entry.get("qc_user_id") else None,
            qa_user_id=int(entry["qa_user_id"]) if entry.get("qa_user_id") else None,
            status="not_started",
            is_active=True,
            created_by_id=actor.id,
        )
        db.add(item)
        created.append(item)
    db.flush()
    return created


def generate_sequence(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_id: int,
    prefix: str = "FILE",
    start: int = 1,
    count: int = 1,
    padding: int = 3,
    extension: str | None = None,
) -> list[WorkPackageItem]:
    """Generate sequential file numbers: FILE_001 … FILE_050 (duplicate-safe)."""
    prefix = (prefix or "FILE").strip()
    if not prefix or not all(c.isalnum() or c in "-_" for c in prefix):
        raise ValueError("Prefix may only contain letters, numbers, '-' and '_'")
    start = int(start)
    count = int(count)
    padding = max(1, min(10, int(padding)))
    if count < 1 or start < 1:
        raise ValueError("Start and count must be positive")
    if start + count - 1 > 1_000_000:
        raise ValueError("Refusing to generate more than 1,000,000 files at once")
    ext = (extension or "").strip()
    if ext and not ext.startswith("."):
        ext = f".{ext}"
    entries = []
    for n in range(start, start + count):
        entries.append({"item_number": f"{prefix}_{n:0{padding}d}{ext}", "sequence_no": n})
    return add_items(db, actor=actor, role=role, work_package_id=work_package_id, entries=entries)


_NUMBER_ALIASES = ("item_number", "item number", "file number", "file_number", "number", "file no", "item no")
_NAME_ALIASES = ("item_name", "item name", "file name", "file_name", "name")
_QTY_ALIASES = ("planned_quantity", "planned qty", "quantity", "qty", "length")
_UNIT_ALIASES = ("planned_unit", "unit", "uom")


def _map_header(header: str) -> str | None:
    h = (header or "").strip().lower()
    for aliases, field in ((_NUMBER_ALIASES, "item_number"), (_NAME_ALIASES, "item_name"),
                           (_QTY_ALIASES, "planned_quantity"), (_UNIT_ALIASES, "planned_unit")):
        if h in aliases:
            return field
    return None


def parse_items_file(filename: str, content: bytes) -> list[dict]:
    """Parse an uploaded CSV / Excel file into item entries with row-level errors."""
    name = (filename or "").lower()
    rows: list[list[Any]] = []
    if name.endswith(".csv") or not content[:2] == b"PK":
        text = None
        for encoding in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("Unable to decode the CSV file")
        import csv
        rows = [list(row) for row in csv.reader(text.splitlines())]
    else:
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            sheet = workbook.worksheets[0]
            rows = [list(row) for row in sheet.iter_rows(values_only=True)]
        finally:
            workbook.close()
    rows = [row for row in rows if any(cell is not None and str(cell).strip() for cell in row)]
    if not rows:
        raise ValueError("The uploaded file is empty")

    header = [str(cell or "").strip() if cell is not None else "" for cell in rows[0]]
    mapping = [_map_header(h) for h in header]
    if "item_number" in mapping:
        data_rows = rows[1:]
        offset = 1
    else:
        # Headerless CSV: first column = file number, second = file name, third = qty, fourth = unit.
        mapping = ["item_number", "item_name", "planned_quantity", "planned_unit"]
        data_rows = rows
        offset = 0

    entries: list[dict] = []
    errors: list[str] = []
    for i, row in enumerate(data_rows, start=offset + 1):
        entry: dict = {}
        for j, field in enumerate(mapping):
            if field and j < len(row):
                value = row[j]
                if value is None:
                    continue
                entry[field] = value if isinstance(value, (int, float)) else str(value).strip()
        if not str(entry.get("item_number") or "").strip():
            errors.append(f"row {i}: missing file number")
            continue
        if len(errors) >= 20:
            errors.append("…too many errors (stopped after 20)")
            break
        entries.append(entry)
    if errors:
        raise ValueError("Import validation failed — " + "; ".join(errors))
    if not entries:
        raise ValueError("No valid file rows were found in the uploaded file")
    return entries


def import_items(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_id: int,
    filename: str,
    content: bytes,
) -> list[WorkPackageItem]:
    entries = parse_items_file(filename, content)
    return add_items(db, actor=actor, role=role, work_package_id=work_package_id, entries=entries)


def assign_items(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_id: int,
    item_ids: list[int],
    production_user_id: int | None = None,
    qc_user_id: int | None = None,
    qa_user_id: int | None = None,
) -> list[WorkPackageItem]:
    """Bulk assign Production / QC / QA to the selected files."""
    package = load_package(db, work_package_id)
    ctx = actor_context(db, package, actor, role)
    _ensure_mutable(ctx)
    if not item_ids:
        raise ValueError("Select at least one file")
    items = db.scalars(select(WorkPackageItem).where(
        WorkPackageItem.id.in_(item_ids),
        WorkPackageItem.work_package_id == package.id,
    )).all()
    if len(items) != len(set(item_ids)):
        raise ValueError("Some selected files do not belong to this area")
    if production_user_id:
        _ensure_assignable(db, package, ctx, int(production_user_id), "production")
    if qc_user_id:
        _ensure_assignable(db, package, ctx, int(qc_user_id), "qc")
    if qa_user_id:
        _ensure_assignable(db, package, ctx, int(qa_user_id), "qa")
    for item in items:
        if production_user_id:
            item.production_user_id = int(production_user_id)
        if qc_user_id:
            item.qc_user_id = int(qc_user_id)
        if qa_user_id:
            item.qa_user_id = int(qa_user_id)
    db.flush()
    return list(items)


def update_item(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_item_id: int,
    changes: dict,
    provided: set[str],
) -> WorkPackageItem:
    """Update one file (rename, reassign, deactivate). History is never touched."""
    item = load_item(db, work_package_item_id)
    package = load_package(db, item.work_package_id)
    ctx = actor_context(db, package, actor, role)
    _ensure_mutable(ctx)
    if "item_number" in provided:
        number = (changes.get("item_number") or "").strip()
        if not number:
            raise ValueError("File number cannot be empty")
        clash = db.scalar(select(WorkPackageItem.id).where(
            WorkPackageItem.work_package_id == package.id,
            WorkPackageItem.item_number == number,
            WorkPackageItem.id != item.id,
        ))
        if clash is not None:
            raise ValueError(f"File number '{number}' already exists in this area")
        item.item_number = number
    if "item_name" in provided:
        item.item_name = (changes.get("item_name") or "").strip() or None
    if "planned_quantity" in provided:
        item.planned_quantity = _clean_number(changes.get("planned_quantity"))
    if "planned_unit" in provided:
        item.planned_unit = (changes.get("planned_unit") or "").strip() or None
    if "is_active" in provided:
        item.is_active = bool(changes.get("is_active"))
    for stage, key in STAGE_ASSIGN_ATTR.items():
        if key in provided:
            value = changes.get(key)
            if value:
                _ensure_assignable(db, package, ctx, int(value), stage)
                setattr(item, key, int(value))
            else:
                setattr(item, key, None)
    db.flush()
    return item


# ===========================================================================================
# Timed stage activities (Production / QC / QA) + delivery
# ===========================================================================================

def open_session_for(
    db: Session, *, item_id: int, stage: str, employee_user_id: int | None = None
) -> WorkPackageItemActivity | None:
    stmt = select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_item_id == item_id,
        WorkPackageItemActivity.stage == stage,
        WorkPackageItemActivity.ended_at.is_(None),
    )
    if employee_user_id is not None:
        stmt = stmt.where(WorkPackageItemActivity.employee_user_id == employee_user_id)
    return db.scalar(stmt)


def start_activity(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_item_id: int,
    stage: str,
    started_at: datetime | None = None,
) -> WorkPackageItemActivity:
    stage = (stage or "").strip().lower()
    if stage not in TIMED_STAGES:
        raise ValueError(f"Stage must be one of: {', '.join(TIMED_STAGES)}")
    item = load_item(db, work_package_item_id)
    if not item.is_active:
        raise ValueError("This file is inactive and cannot be worked on")
    package = load_package(db, item.work_package_id)
    performed_role = _ensure_stage_actor(db, package, item, actor, role, stage)

    # Workflow gates (server-side, authoritative): QC only after Production is
    # completed for that file; QA only after QC passed it.
    latest = latest_activities_by_item(db, [package.id]).get(item.id, {})
    if stage == "production":
        finished = latest.get("production")
        if finished is not None and finished.status == "completed":
            # A finalized file cannot be re-opened — EXCEPT when a QC/QA rejection left
            # rework outstanding (the existing rework loop must still be able to redo work).
            qc = latest.get("qc")
            qa = latest.get("qa")
            rework_open = (
                (qc is not None and qc.status in {"rejected", "rework"})
                or (qa is not None and qa.status in {"rejected", "rework"})
            )
            if not rework_open:
                raise ValueError("Production is already completed for this file")
    if stage == "qc":
        production = latest.get("production")
        if production is None or production.status != "completed":
            raise ValueError("Production must be completed for this file before QC can start")
        already = latest.get("qc")
        if already is not None and already.status == "passed":
            # A passed QC is final; only an outstanding rework may reopen QC (so a later
            # rejection can never contradict a file that was already passed/delivered).
            raise ValueError("QC has already passed for this file")
    elif stage == "qa":
        qc = latest.get("qc")
        if qc is None or qc.status != "passed":
            raise ValueError("QC must pass this file before QA can start")
        already_qa = latest.get("qa")
        if already_qa is not None and already_qa.status == "passed":
            raise ValueError("QA has already passed for this file")

    existing = open_session_for(db, item_id=item.id, stage=stage)
    if existing is not None:
        if existing.employee_user_id == actor.id:
            raise ValueError(f"You already have an open {stage.upper()} session for this file — complete it first")
        raise ValueError(f"Another employee already has an open {stage.upper()} session for this file")

    # Attempt metadata (V8.4): a repeat attempt for the same file+stage is a REWORK
    # attempt; the physical file still counts once regardless of how many attempts exist.
    prior_attempts = db.scalar(select(func.count(WorkPackageItemActivity.id)).where(
        WorkPackageItemActivity.work_package_item_id == item.id,
        WorkPackageItemActivity.stage == stage,
    )) or 0
    attempt_number = int(prior_attempts) + 1
    attempt_type = "REWORK" if attempt_number > 1 else "INITIAL"

    activity = WorkPackageItemActivity(
        project_id=package.project_id,
        work_package_id=package.id,
        work_package_item_id=item.id,
        stage=stage,
        employee_user_id=actor.id,
        performed_role=performed_role,
        from_status=item.status,
        started_at=started_at or utc_now(),
        status="in_progress",
        files_completed=0,
        attempt_type=attempt_type,
        attempt_number=attempt_number,
    )
    db.add(activity)
    if item.status == "not_started":
        item.status = "in_progress"
    db.flush()
    return activity


def stop_activity(
    db: Session,
    *,
    actor: User,
    activity_id: int,
    status: str | None = None,
    quantity_completed: Decimal | None = None,
    unit: str | None = None,
    files_completed: int | None = None,
    remarks: str | None = None,
    delay_category: str | None = None,
    affected_item_id: int | None = None,
    delay_reason: str | None = None,
    system_malfunction: bool = False,
    delay_remarks: str | None = None,
    ended_at: datetime | None = None,
    finalize: bool = True,
) -> WorkPackageItemActivity:
    """End a file stage session. Duration is derived from real timestamps.

    ``finalize=False`` = SAVE DAILY PROGRESS: the session closes and its quantity is
    recorded, but the physical file is NOT finished (files_completed stays 0, the
    item stays in progress and QC is NOT unlocked). ``finalize=True`` = COMPLETE
    PRODUCTION / QC / QA decision.
    """
    activity = db.get(WorkPackageItemActivity, activity_id)
    if activity is None:
        raise ValueError("Activity not found")
    if activity.employee_user_id != actor.id:
        raise PermissionError("Only the employee who started this session can complete it")
    if activity.ended_at is not None:
        raise ValueError("This session is already completed")

    end = ended_at or utc_now()
    if activity.started_at is None:
        raise ValueError("This session has no start timestamp")
    if end <= activity.started_at:
        raise ValueError("End time must be after the start time")
    duration = int((end - activity.started_at).total_seconds())
    if duration < 0:
        raise ValueError("Duration cannot be negative")

    stage = activity.stage
    if stage == "production":
        if finalize:
            final_status = normalize_production_status(status)
        else:
            # Progress saved: never finalize the file from ending a timer.
            final_status = "in_progress"
    else:
        if status is None:
            raise ValueError(f"{stage.upper()} completion requires a status: passed, rejected or rework")
        final_status = normalize_review_status(status)
        finalize = True

    category, malfunction = normalize_delay(delay_category, system_malfunction)

    if affected_item_id:
        affected = load_item(db, int(affected_item_id))
        if affected.work_package_id != activity.work_package_id:
            raise ValueError("Affected file must belong to the same area")

    activity.ended_at = end
    activity.duration_seconds = duration
    activity.status = final_status
    activity.quantity_completed = _clean_number(quantity_completed)
    activity.unit = (unit or "").strip() or None
    # FILE-LEVEL workflow: the specific file being completed is known, so the
    # completed-file contribution is automatic — and a physical file contributes exactly
    # ONCE across all its sessions (partial "save progress" sessions contribute 0 and a
    # re-finalization after rework does not count the file a second time).
    already_counted = False
    if stage == "production" and finalize:
        already_counted = db.scalar(select(WorkPackageItemActivity.id).where(
            WorkPackageItemActivity.work_package_item_id == activity.work_package_item_id,
            WorkPackageItemActivity.stage == "production",
            WorkPackageItemActivity.files_completed == 1,
            WorkPackageItemActivity.id != activity.id,
        ).limit(1)) is not None
    activity.files_completed = 1 if (stage == "production" and finalize and not already_counted) else 0
    activity.remarks = (remarks or "").strip() or None
    activity.delay_category = category
    activity.affected_item_id = int(affected_item_id) if affected_item_id else None
    activity.delay_reason = (delay_reason or "").strip() or None
    activity.system_malfunction = malfunction
    activity.delay_remarks = (delay_remarks or "").strip() or None

    item = load_item(db, activity.work_package_item_id)
    package = load_package(db, item.work_package_id)
    # stop_activity has no role parameter: the completing actor holds a session, so they
    # can never be a read-only viewer; PM/Team-Lead flags drive the notification targets.
    ctx = actor_context(db, package, actor, "")
    url = f"/production-tracking?project={package.project_id}"
    if stage == "production":
        if final_status == "completed":
            item.status = ITEM_STATUS_PRODUCTION_DONE
            # Final production completion -> QC becomes READY automatically.
            _notify(
                db, event_type="workflow.item.qc_ready",
                title=f"Ready for QC: {item.item_number}",
                message=(
                    f"Project {package.package_code} · file {item.item_number} production completed — "
                    f"QC can start."
                ),
                recipient_ids=[item.qc_user_id, package.team_leader_user_id],
                target_url=url, dedupe_key=f"item-qc-ready-{activity.id}",
            )
        else:
            # Progress saved for this session: the file stays in progress, QC stays locked.
            item.status = "in_progress"
    elif stage == "qc":
        if final_status == "passed":
            item.status = ITEM_STATUS_QC_PASSED
            _notify(
                db, event_type="workflow.item.qa_ready",
                title=f"Ready for QA: {item.item_number}",
                message=f"Project {package.package_code} · file {item.item_number} passed QC — QA can start.",
                recipient_ids=[item.qa_user_id, package.team_leader_user_id],
                target_url=url, dedupe_key=f"item-qa-ready-{activity.id}",
            )
        else:
            item.status = ITEM_STATUS_QC_REJECTED
            _notify(
                db, event_type="workflow.item.qc_rework",
                title=f"QC returned for rework: {item.item_number}",
                message=f"Project {package.package_code} · file {item.item_number} QC {final_status} — rework required.",
                recipient_ids=[item.production_user_id, package.team_leader_user_id],
                target_url=url, dedupe_key=f"item-qc-rework-{activity.id}",
            )
    else:
        if final_status == "passed":
            item.status = ITEM_STATUS_QA_PASSED
            readiness = delivery_readiness(db, package)
            if readiness["ready"]:
                _notify(
                    db, event_type="workflow.package.ready_for_delivery",
                    title=f"Ready for delivery: {package.package_code}",
                    message=(
                        f"All {readiness['total_files']} file(s) of {package.package_code} passed QA — "
                        f"confirm Ready for Delivery."
                    ),
                    recipient_ids=[package.team_leader_user_id, ctx["pm_id"]],
                    target_url=url, dedupe_key=f"package-ready-for-delivery-{package.id}",
                )
        else:
            item.status = ITEM_STATUS_QA_REJECTED
            _notify(
                db, event_type="workflow.item.qa_rework",
                title=f"QA returned for rework: {item.item_number}",
                message=f"Project {package.package_code} · file {item.item_number} QA {final_status} — rework required.",
                recipient_ids=[item.production_user_id, item.qc_user_id, package.team_leader_user_id],
                target_url=url, dedupe_key=f"item-qa-rework-{activity.id}",
            )
    db.flush()
    return activity


def delivery_readiness(
    db: Session,
    package: OrthoWorkPackage,
    *,
    items: list[WorkPackageItem] | None = None,
    latest: dict[int, dict[str, WorkPackageItemActivity]] | None = None,
) -> dict:
    """Server-calculated delivery readiness for one area (file-level only).

    READY only when every ACTIVE file has a latest QA PASS. Areas without files
    are ``applicable = False`` so the legacy area-level delivery flow is unchanged.
    """
    items = items if items is not None else items_for_packages(db, [package.id])
    active = [i for i in items if i.is_active]
    latest = latest if latest is not None else latest_activities_by_item(db, [package.id])
    counts = {
        "total_files": len(active),
        "production_completed": 0, "production_pending": 0,
        "qc_passed": 0, "qc_pending": 0, "qc_rework": 0,
        "qa_passed": 0, "qa_pending": 0, "qa_rework": 0,
    }
    for item in active:
        per = latest.get(item.id, {})
        prod, qc, qa = per.get("production"), per.get("qc"), per.get("qa")
        if prod is not None and prod.status == "completed":
            counts["production_completed"] += 1
            if qc is None:
                counts["qc_pending"] += 1
            elif qc.status == "passed":
                counts["qc_passed"] += 1
                if qa is None:
                    counts["qa_pending"] += 1
                elif qa.status == "passed":
                    counts["qa_passed"] += 1
                else:
                    counts["qa_rework"] += 1
            else:
                counts["qc_rework"] += 1
        else:
            counts["production_pending"] += 1
    ready = bool(active) and counts["qa_passed"] == len(active)
    return {
        "applicable": bool(active),
        "ready": ready,
        **counts,
        "ready_by_id": package.ready_for_delivery_by_id,
        "ready_at": package.ready_for_delivery_at.isoformat() if package.ready_for_delivery_at else None,
        "confirmed": package.ready_for_delivery_at is not None,
    }


def mark_ready_for_delivery(
    db: Session, *, actor: User, role: str, work_package_id: int
) -> dict:
    """Team Lead / PM confirms Ready for Delivery (server-validated, idempotent)."""
    package = load_package(db, work_package_id)
    ctx = actor_context(db, package, actor, role)
    if ctx["read_only_role"]:
        raise PermissionError("Management/Admin access is read-only")
    if not (ctx["is_tl"] or ctx["is_pm"]):
        raise PermissionError("Only the Team Lead or Project Manager can confirm Ready for Delivery")
    readiness = delivery_readiness(db, package)
    if not readiness["applicable"]:
        raise ValueError("This area tracks no files — use the existing area-level delivery flow")
    if not readiness["ready"]:
        pending = (
            f"Production pending {readiness['production_pending']}, "
            f"QC pending {readiness['qc_pending']}, QC rework {readiness['qc_rework']}, "
            f"QA pending {readiness['qa_pending']}, QA rework {readiness['qa_rework']}"
        )
        raise ValueError(f"Not all files passed QA yet — {pending}")
    if package.ready_for_delivery_at is None:
        package.ready_for_delivery_at = utc_now()
        package.ready_for_delivery_by_id = actor.id
        _notify(
            db, event_type="workflow.package.ready_confirmed",
            title=f"Ready for delivery confirmed: {package.package_code}",
            message=(
                f"{package.package_code} was confirmed Ready for Delivery by the Team Lead. "
                f"Project ID {package.project_id} — proceed with the authorized delivery workflow."
            ),
            recipient_ids=[ctx["pm_id"]],
            target_url=f"/production-tracking?project={package.project_id}",
            dedupe_key=f"package-ready-confirmed-{package.id}",
        )
        db.flush()
    return delivery_readiness(db, package)


def deliver_item(
    db: Session,
    *,
    actor: User,
    role: str,
    work_package_item_id: int,
    remarks: str | None = None,
    reference: str | None = None,
) -> WorkPackageItemActivity:
    """Record file delivery (authorized Team Lead / PM, mirroring mark_delivered)."""
    item = load_item(db, work_package_item_id)
    package = load_package(db, item.work_package_id)
    ctx = actor_context(db, package, actor, role)
    if ctx["read_only_role"]:
        raise PermissionError("Management/Admin access is read-only")
    if not (ctx["is_tl"] or ctx["is_pm"]):
        raise PermissionError("Only the Team Lead or Project Manager can record Delivery")

    latest_qa = db.scalar(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_item_id == item.id,
        WorkPackageItemActivity.stage == "qa",
    ).order_by(WorkPackageItemActivity.id.desc()))
    # Delivery is gated on this file actually passing QA (a missing QA assignment is NOT a
    # permission to deliver — otherwise QA pass % and delivered % would contradict).
    if latest_qa is None or latest_qa.status != "passed":
        raise ValueError("QA must pass this file before Delivery")

    now = utc_now()
    parts = [p for p in ((reference and f"Reference: {reference}"), remarks) if p]
    activity = WorkPackageItemActivity(
        project_id=package.project_id,
        work_package_id=package.id,
        work_package_item_id=item.id,
        stage="delivery",
        employee_user_id=actor.id,
        performed_role="team_leader" if ctx["is_tl"] else "project_manager",
        from_status=item.status,
        started_at=now,
        ended_at=now,
        duration_seconds=0,
        status="delivered",
        remarks=" — ".join(parts) if parts else None,
        files_completed=0,
    )
    db.add(activity)
    item.status = ITEM_STATUS_DELIVERED
    db.flush()
    return activity


# ===========================================================================================
# Reads / aggregations (server-side, indexed, no N+1)
# ===========================================================================================

def latest_activities_by_item(db: Session, package_ids: Iterable[int]) -> dict[int, dict[str, WorkPackageItemActivity]]:
    """Latest activity per (item, stage) for the given packages — 2 queries total."""
    package_ids = list(package_ids)
    if not package_ids:
        return {}
    latest_ids = db.scalars(
        select(func.max(WorkPackageItemActivity.id))
        .where(WorkPackageItemActivity.work_package_id.in_(package_ids))
        .group_by(WorkPackageItemActivity.work_package_item_id, WorkPackageItemActivity.stage)
    ).all()
    if not latest_ids:
        return {}
    rows = db.scalars(select(WorkPackageItemActivity).where(WorkPackageItemActivity.id.in_(latest_ids))).all()
    out: dict[int, dict[str, WorkPackageItemActivity]] = {}
    for row in rows:
        out.setdefault(row.work_package_item_id, {})[row.stage] = row
    return out


def all_activities_by_item(db: Session, package_ids: Iterable[int]) -> dict[int, list[WorkPackageItemActivity]]:
    """Every activity row per item (chronological) — sessions must never be lost."""
    package_ids = list(package_ids)
    if not package_ids:
        return {}
    rows = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_id.in_(package_ids)
    ).order_by(WorkPackageItemActivity.id.asc())).all()
    out: dict[int, list[WorkPackageItemActivity]] = {}
    for row in rows:
        out.setdefault(row.work_package_item_id, []).append(row)
    return out


def items_for_packages(db: Session, package_ids: Iterable[int]) -> list[WorkPackageItem]:
    package_ids = list(package_ids)
    if not package_ids:
        return []
    return list(db.scalars(
        select(WorkPackageItem)
        .where(WorkPackageItem.work_package_id.in_(package_ids))
        .order_by(WorkPackageItem.work_package_id.asc(), WorkPackageItem.sequence_no.asc(), WorkPackageItem.id.asc())
    ).all())


def _display_statuses(item: WorkPackageItem, latest: dict[str, WorkPackageItemActivity]) -> dict[str, str]:
    """Explicit per-stage status: derived from activities, never one generic status."""
    out: dict[str, str] = {}
    for stage in ITEM_STAGES:
        act = latest.get(stage)
        if act is not None:
            out[stage] = act.status
        else:
            out[stage] = "pending" if stage == "delivery" else "not_started"
    if item.status == ITEM_STATUS_DELIVERED:
        out["delivery"] = "delivered"
    return out


def build_item_rows(
    db: Session,
    package_ids: Iterable[int],
    *,
    users: dict[int, User] | None = None,
) -> list[dict]:
    """Flat per-file rows for the area detail drawer and the FILE ACTIVITY sheet."""
    package_ids = list(package_ids)
    items = items_for_packages(db, package_ids)
    if not items:
        return []
    latest = latest_activities_by_item(db, package_ids)
    all_ids: set[int] = set()
    for per_item in latest.values():
        for act in per_item.values():
            if act.employee_user_id:
                all_ids.add(act.employee_user_id)
    for item in items:
        all_ids.update(uid for uid in (item.production_user_id, item.qc_user_id, item.qa_user_id) if uid)
    if users is None:
        users = {}
    # Callers may pass a pre-built dict (e.g. package assignees); fetch anyone
    # else referenced by activities (deliveries, cross-stage actors) so names
    # like "Delivered By" are never silently missing.
    missing = sorted({uid for uid in all_ids if uid and uid not in users})
    if missing:
        users.update({u.id: u for u in db.scalars(select(User).where(User.id.in_(missing))).all()})

    def name_of(uid: int | None) -> str | None:
        if not uid:
            return None
        user = users.get(uid)
        return user.full_name if user else None

    open_rows = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_item_id.in_([i.id for i in items]),
        WorkPackageItemActivity.ended_at.is_(None),
    )).all()
    open_by_item: dict[int, WorkPackageItemActivity] = {row.work_package_item_id: row for row in open_rows}
    all_acts = all_activities_by_item(db, package_ids)
    packages = {p.id: p for p in db.scalars(
        select(OrthoWorkPackage).where(OrthoWorkPackage.id.in_(package_ids))
    ).all()}

    rows: list[dict] = []
    for item in items:
        per_stage = latest.get(item.id, {})
        statuses = _display_statuses(item, per_stage)
        prod = per_stage.get("production")
        qc = per_stage.get("qc")
        qa = per_stage.get("qa")
        delivery = per_stage.get("delivery")
        # Production sessions accumulate: one physical file may be worked across many
        # sessions/days. Quantity/time are SUMMED across closed sessions; the file is
        # finalized only by a session whose status is "completed".
        item_acts = all_acts.get(item.id, [])
        prod_sessions = [a for a in item_acts if a.stage == "production" and a.ended_at is not None]
        cumulative = sum((a.quantity_completed or Decimal("0")) for a in prod_sessions)
        total_seconds = sum(int(a.duration_seconds or 0) for a in prod_sessions)
        finalized = next((a for a in reversed(prod_sessions) if a.status == "completed"), None)
        files_completed_total = sum(int(a.files_completed or 0) for a in prod_sessions)
        affected = None
        if prod is not None and prod.affected_item_id:
            affected = db.get(WorkPackageItem, prod.affected_item_id)
        open_row = open_by_item.get(item.id)
        rows.append({
            "work_package_item_id": item.id,
            "work_package_id": item.work_package_id,
            "project_id": item.project_id,
            "item_number": item.item_number,
            "item_name": item.item_name,
            "sequence_no": item.sequence_no,
            "planned_quantity": float(item.planned_quantity) if item.planned_quantity is not None else None,
            "planned_unit": item.planned_unit,
            "production_target_date": item.production_target_date.isoformat() if item.production_target_date else None,
            "qc_target_date": item.qc_target_date.isoformat() if item.qc_target_date else None,
            "qa_target_date": item.qa_target_date.isoformat() if item.qa_target_date else None,
            "import_source": item.import_source,
            "supply_date": (packages[item.work_package_id].supply_date.isoformat()
                            if item.work_package_id in packages and packages[item.work_package_id].supply_date else None),
            "ready_for_delivery": bool(
                item.work_package_id in packages and packages[item.work_package_id].ready_for_delivery_at is not None
            ),
            "status": item.status,
            "is_active": item.is_active,
            "production_user_id": item.production_user_id,
            "production_user": name_of(item.production_user_id),
            "qc_user_id": item.qc_user_id,
            "qc_user": name_of(item.qc_user_id),
            "qa_user_id": item.qa_user_id,
            "qa_user": name_of(item.qa_user_id),
            "production_status": statuses["production"],
            "qc_status": statuses["qc"],
            "qa_status": statuses["qa"],
            "delivery_status": statuses["delivery"],
            "production_start": (prod_sessions[0].started_at.isoformat()
                                 if prod_sessions and prod_sessions[0].started_at
                                 else (prod.started_at.isoformat() if prod and prod.started_at else None)),
            "production_end": (prod_sessions[-1].ended_at.isoformat()
                               if prod_sessions and prod_sessions[-1].ended_at
                               else (prod.ended_at.isoformat() if prod and prod.ended_at else None)),
            "production_completed_at": finalized.ended_at.isoformat() if finalized and finalized.ended_at else None,
            "production_sessions": len(prod_sessions),
            "production_duration_seconds": (total_seconds if prod_sessions
                                            else (prod.duration_seconds if prod else None)),
            "production_quantity": (float(cumulative) if prod_sessions
                                    else (float(prod.quantity_completed) if prod and prod.quantity_completed is not None else None)),
            "production_unit": prod.unit if prod else (item.planned_unit),
            "production_files": files_completed_total,
            "qc_attempts": len([a for a in item_acts if a.stage == "qc" and a.ended_at is not None]),
            "qa_attempts": len([a for a in item_acts if a.stage == "qa" and a.ended_at is not None]),
            "production_attempt_type": prod.attempt_type if prod else None,
            "production_attempt_number": prod.attempt_number if prod else None,
            "qc_attempt_type": qc.attempt_type if qc else None,
            "qa_attempt_type": qa.attempt_type if qa else None,
            "production_remarks": prod.remarks if prod else None,
            "production_employee": name_of(prod.employee_user_id) if prod else None,
            "qc_start": qc.started_at.isoformat() if qc and qc.started_at else None,
            "qc_end": qc.ended_at.isoformat() if qc and qc.ended_at else None,
            "qc_duration_seconds": qc.duration_seconds if qc else None,
            "qc_remarks": qc.remarks if qc else None,
            "qc_employee": name_of(qc.employee_user_id) if qc else None,
            "qa_start": qa.started_at.isoformat() if qa and qa.started_at else None,
            "qa_end": qa.ended_at.isoformat() if qa and qa.ended_at else None,
            "qa_duration_seconds": qa.duration_seconds if qa else None,
            "qa_remarks": qa.remarks if qa else None,
            "qa_employee": name_of(qa.employee_user_id) if qa else None,
            "delivery_at": delivery.ended_at.isoformat() if delivery and delivery.ended_at else None,
            "delivery_by": name_of(delivery.employee_user_id) if delivery else None,
            "delivery_remarks": delivery.remarks if delivery else None,
            "delay_category": prod.delay_category if prod else None,
            "delay_reason": prod.delay_reason if prod else None,
            "delay_remarks": prod.delay_remarks if prod else None,
            "affected_item_number": affected.item_number if affected else None,
            "system_malfunction": bool(prod.system_malfunction) if prod else False,
            "production_deadline": item_stage_deadline(item, "production", latest=per_stage),
            "qc_deadline": item_stage_deadline(item, "qc", latest=per_stage),
            "qa_deadline": item_stage_deadline(item, "qa", latest=per_stage),
            "open_session": ({
                "activity_id": open_row.id,
                "stage": open_row.stage,
                "employee_user_id": open_row.employee_user_id,
                "started_at": open_row.started_at.isoformat() if open_row.started_at else None,
            } if open_row is not None else None),
        })
    return rows


def file_aggregates_for_packages(db: Session, package_ids: Iterable[int]) -> dict[int, dict]:
    """Per-package file counts and per-stage file progress — server-side, 3 queries."""
    package_ids = list(package_ids)
    if not package_ids:
        return {}
    items = items_for_packages(db, package_ids)
    latest = latest_activities_by_item(db, package_ids)
    agg: dict[int, dict] = {
        pid: {
            "files_expected": 0, "files_total": 0,
            "files_production_done": 0, "files_qc_passed": 0,
            "files_qa_passed": 0, "files_delivered": 0,
            "files_assigned": 0, "files_available": 0,
            "production_pending": 0, "production_in_progress": 0, "production_rework": 0,
            "qc_pending": 0, "qc_in_progress": 0, "qc_rework": 0,
            "qa_pending": 0, "qa_in_progress": 0, "qa_rework": 0,
            "ready": 0,
            "production_item_percent": 0.0, "qc_item_percent": 0.0,
            "qa_item_percent": 0.0, "delivery_item_percent": 0.0,
        }
        for pid in package_ids
    }
    for item in items:
        row = agg.setdefault(item.work_package_id, {})
        row["files_total"] = row.get("files_total", 0) + 1
        if not item.is_active:
            continue
        row["files_expected"] = row.get("files_expected", 0) + 1
        if item.production_user_id:
            row["files_assigned"] += 1
        else:
            row["files_available"] += 1
        per_stage = latest.get(item.id, {})
        prod, qc, qa = per_stage.get("production"), per_stage.get("qc"), per_stage.get("qa")
        # A QC reject/rework that is NEWER than the latest Production completion puts the
        # file back into ACTIVE production rework (still ONE physical file). If Production
        # has since been redone, the file is production-complete again and merely awaiting
        # QC re-inspection.
        rework_outstanding = (
            qc is not None and qc.status in {"rejected", "rework"}
            and (prod is None or prod.id < qc.id)
        )
        if prod is not None and prod.status == "completed" and rework_outstanding:
            row["production_rework"] += 1
            row["qc_rework"] += 1
            continue
        if prod is not None and prod.status == "completed":
            row["files_production_done"] += 1
        elif prod is not None and prod.status == "in_progress":
            row["production_in_progress"] += 1
            row["production_pending"] += 1
        else:
            row["production_pending"] += 1
        if prod is not None and prod.status == "completed":
            if qc is None:
                row["qc_pending"] += 1
            elif qc.status == "in_progress":
                row["qc_in_progress"] += 1
            elif qc.status == "passed":
                row["files_qc_passed"] += 1
                if qa is None:
                    row["qa_pending"] += 1
                elif qa.status == "in_progress":
                    row["qa_in_progress"] += 1
                elif qa.status == "passed":
                    row["files_qa_passed"] += 1
                else:
                    row["qa_rework"] += 1
            elif qc.status in {"rejected", "rework"}:
                row["qc_pending"] += 1          # production redone → awaiting QC retry
            else:
                row["qc_rework"] += 1
        if per_stage.get("delivery") is not None and per_stage["delivery"].status == "delivered":
            row["files_delivered"] += 1
    for row in agg.values():
        total = row.get("files_expected", 0)
        if total:
            row["production_item_percent"] = round(row["files_production_done"] * 100.0 / total, 2)
            row["qc_item_percent"] = round(row["files_qc_passed"] * 100.0 / total, 2)
            row["qa_item_percent"] = round(row["files_qa_passed"] * 100.0 / total, 2)
            row["delivery_item_percent"] = round(row["files_delivered"] * 100.0 / total, 2)
        row["ready_for_delivery"] = bool(total) and row["files_qa_passed"] == total
        # "Ready" file counter = distinct physical files that have passed QA (eligible).
        row["ready"] = row["files_qa_passed"]
    return agg


def package_completion_for_deadline(db: Session, package: OrthoWorkPackage) -> datetime | None:
    """Area completion datetime: area-level production completion, else all files done."""
    if package.production_completed_at is not None:
        return package.production_completed_at
    items = items_for_packages(db, [package.id])
    active = [i for i in items if i.is_active]
    if not active:
        return None
    latest = latest_activities_by_item(db, [package.id])
    ends: list[datetime] = []
    for item in active:
        act = latest.get(item.id, {}).get("production")
        if act is None or act.status != "completed" or act.ended_at is None:
            return None
        ends.append(act.ended_at)
    return max(ends)


def employee_productivity_rows(db: Session, package_ids: Iterable[int]) -> list[dict]:
    """Employee-wise per-area per-day summary (server-side; units never mixed)."""
    package_ids = list(package_ids)
    if not package_ids:
        return []
    activities = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_id.in_(package_ids),
        WorkPackageItemActivity.ended_at.is_not(None),
    ).order_by(WorkPackageItemActivity.id.asc())).all()
    if not activities:
        return []
    packages = {p.id: p for p in db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.id.in_(package_ids))).all()}
    items_by_id = {i.id: i for i in items_for_packages(db, package_ids)}
    employee_ids = {a.employee_user_id for a in activities}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(employee_ids))).all()}

    groups: dict[tuple, dict] = {}
    for act in activities:
        day = act.started_at.date() if act.started_at else (act.created_at.date() if act.created_at else None)
        key = (act.employee_user_id, act.work_package_id, day, act.unit or "")
        package = packages.get(act.work_package_id)
        entry = groups.setdefault(key, {
            "employee_user_id": act.employee_user_id,
            "employee": users.get(act.employee_user_id).full_name if act.employee_user_id in users else None,
            "role": act.performed_role,
            "work_package_id": act.work_package_id,
            "lot": package.lot_batch if package else None,
            "area_code": package.package_code if package else None,
            "area_name": package.package_name if package else None,
            "date": day.isoformat() if day else None,
            "files_completed": 0,
            "worked_item_ids": set(),
            "quantity_completed": Decimal("0"),
            "unit": act.unit,
            "production_seconds": 0,
            "qc_seconds": 0,
            "qa_seconds": 0,
            "delivery_seconds": 0,
            "on_time_count": 0,
            "late_count": 0,
            "rework_count": 0,
            "delay_categories": [],
            "system_malfunction_count": 0,
            "remarks": [],
        })
        entry["files_completed"] += int(act.files_completed or 0)
        entry["worked_item_ids"].add(act.work_package_item_id)
        if act.quantity_completed is not None:
            entry["quantity_completed"] += act.quantity_completed
        seconds = int(act.duration_seconds or 0)
        if act.stage == "production":
            entry["production_seconds"] += seconds
        elif act.stage == "qc":
            entry["qc_seconds"] += seconds
        elif act.stage == "qa":
            entry["qa_seconds"] += seconds
        else:
            entry["delivery_seconds"] += seconds
        # On-time / late against the per-file stage target (authoritative).
        item = items_by_id.get(act.work_package_item_id)
        target = None
        if item is not None:
            target = {
                "production": item.production_target_date,
                "qc": item.qc_target_date,
                "qa": item.qa_target_date,
            }.get(act.stage)
        if target is not None and act.ended_at is not None:
            if act.ended_at.date() <= target:
                entry["on_time_count"] += 1
            else:
                entry["late_count"] += 1
        if act.status in {"rejected", "rework"}:
            entry["rework_count"] += 1
        if act.delay_category and act.delay_category not in entry["delay_categories"]:
            entry["delay_categories"].append(act.delay_category)
        if act.system_malfunction:
            entry["system_malfunction_count"] += 1
        if act.remarks and act.remarks not in entry["remarks"]:
            entry["remarks"].append(act.remarks)

    rows = []
    for entry in sorted(groups.values(), key=lambda r: (r["employee"] or "", r["date"] or "", r["area_code"] or "")):
        entry["quantity_completed"] = float(entry["quantity_completed"])
        # Day-scoped distinct files worked that day (a file worked across days is not
        # multiplied inside a single day's row).
        entry["files_worked"] = len(entry.pop("worked_item_ids"))
        entry["total_seconds"] = entry["production_seconds"] + entry["qc_seconds"] + entry["qa_seconds"] + entry["delivery_seconds"]
        entry["delay_category"] = ", ".join(entry.pop("delay_categories"))
        entry["remarks"] = "; ".join(entry.pop("remarks"))[:500]
        rows.append(entry)
    return rows


def item_list(db: Session, *, actor: User, role: str, work_package_id: int) -> dict:
    """Area detail payload: visible files, per-stage timings, deadline and totals.

    Privileged viewers (PM / Team Lead / Management / Admin) see every file.
    A plain employee sees ONLY the files assigned to them (production/QC/QA).
    """
    package = load_package(db, work_package_id)
    ctx = actor_context(db, package, actor, role)
    rows = build_item_rows(db, [package.id])
    if not ctx["privileged"]:
        rows = [
            row for row in rows
            if actor.id in {row["production_user_id"], row["qc_user_id"], row["qa_user_id"]}
        ]
    completion = package_completion_for_deadline(db, package)
    totals = employee_file_totals(db, [package.id])
    if not ctx["privileged"]:
        totals = [row for row in totals if row["employee_user_id"] == actor.id]
    readiness = delivery_readiness(db, package)
    # Area-level stage targets = earliest per-stage target across the ACTIVE files.
    stage_targets: dict[str, date | None] = {"production": None, "qc": None, "qa": None}
    for item in items_for_packages(db, [package.id]):
        if not item.is_active:
            continue
        for stage, value in (
            ("production", item.production_target_date),
            ("qc", item.qc_target_date),
            ("qa", item.qa_target_date),
        ):
            if value is not None and (stage_targets[stage] is None or value < stage_targets[stage]):
                stage_targets[stage] = value
    pm = db.get(User, ctx["pm_id"]) if ctx["pm_id"] else None
    return {
        "work_package_id": package.id,
        "project_id": package.project_id,
        "package_code": package.package_code,
        "package_name": package.package_name,
        "lot_batch": package.lot_batch,
        "supply_date": package.supply_date.isoformat() if package.supply_date else None,
        "can_manage": ctx["can_manage"],
        "can_deliver": ctx["is_tl"] or ctx["is_pm"],
        "can_confirm_ready": ctx["is_tl"] or ctx["is_pm"],
        "my_user_id": actor.id,
        "deadline": deadline_status(package, completed_at=completion),
        "stage_targets": {
            "production": stage_targets["production"].isoformat() if stage_targets["production"] else None,
            "qc": stage_targets["qc"].isoformat() if stage_targets["qc"] else None,
            "qa": stage_targets["qa"].isoformat() if stage_targets["qa"] else None,
        },
        "stage_deadlines": {
            "production": deadline_status(package, completed_at=completion),
            "qc": stage_deadline_status(stage_targets["qc"]),
            "qa": stage_deadline_status(stage_targets["qa"]),
        },
        "readiness": readiness,
        "project_manager": {"id": pm.id, "full_name": pm.full_name} if pm else None,
        "employee_totals": totals,
        "items": rows,
    }


def item_history(db: Session, *, actor: User, role: str, work_package_item_id: int) -> list[dict]:
    """Full append-only activity history for one file (detail-on-demand)."""
    item = load_item(db, work_package_item_id)
    package = load_package(db, item.work_package_id)
    ctx = actor_context(db, package, actor, role)
    allowed = ctx["privileged"] or actor.id in {
        item.production_user_id, item.qc_user_id, item.qa_user_id,
    }
    if not allowed:
        raise PermissionError("You are not assigned to this file")
    activities = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_item_id == item.id
    ).order_by(WorkPackageItemActivity.id.asc())).all()
    employee_ids = {a.employee_user_id for a in activities}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(employee_ids))).all()} if employee_ids else {}
    return [{
        "id": a.id,
        "stage": a.stage,
        "status": a.status,
        "attempt_type": a.attempt_type,
        "attempt_number": a.attempt_number,
        "employee_user_id": a.employee_user_id,
        "employee": users.get(a.employee_user_id).full_name if a.employee_user_id in users else None,
        "performed_role": a.performed_role,
        "from_status": a.from_status,
        "started_at": a.started_at.isoformat() if a.started_at else None,
        "ended_at": a.ended_at.isoformat() if a.ended_at else None,
        "duration_seconds": a.duration_seconds,
        "quantity_completed": float(a.quantity_completed) if a.quantity_completed is not None else None,
        "unit": a.unit,
        "files_completed": a.files_completed,
        "remarks": a.remarks,
        "delay_category": a.delay_category,
        "delay_reason": a.delay_reason,
        "delay_remarks": a.delay_remarks,
        "system_malfunction": bool(a.system_malfunction),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a in activities]


def item_dashboard_context(db: Session, packages: Iterable[OrthoWorkPackage]) -> dict[int, dict]:
    """Per-package item context for the Project Operations (/ortho) dashboard.

    ONE source of truth: when an area tracks ACTIVE files, visibility, counts and
    stage assignees are derived from ``WorkPackageItem`` (+ its activities) exactly
    like Production Tracking does. Areas with zero active files return
    ``{"has_items": False}`` so the legacy package-level behaviour is preserved.
    """
    package_list = list(packages)
    package_ids = [p.id for p in package_list]
    if not package_ids:
        return {}
    rows_by_pkg: dict[int, list[dict]] = {}
    for row in build_item_rows(db, package_ids):
        rows_by_pkg.setdefault(row["work_package_id"], []).append(row)
    agg = file_aggregates_for_packages(db, package_ids)

    context: dict[int, dict] = {}
    for package in package_list:
        rows = rows_by_pkg.get(package.id, [])
        active = [r for r in rows if r["is_active"]]
        if not active:
            context[package.id] = {"has_items": False}
            continue
        counts = agg.get(package.id, {})

        def assignee_list(id_key: str, name_key: str) -> list[dict]:
            seen: dict[int, str | None] = {}
            for row in active:
                uid = row.get(id_key)
                if uid:
                    seen[int(uid)] = row.get(name_key)
            return [{"id": uid, "full_name": name} for uid, name in sorted(seen.items())]

        total = counts.get("files_expected", len(active)) or len(active)
        production_done = counts.get("files_production_done", 0)
        qc_passed = counts.get("files_qc_passed", 0)
        qa_passed = counts.get("files_qa_passed", 0)
        delivered = counts.get("files_delivered", 0)
        if total and delivered == total:
            bucket = "delivered"
        elif total and qa_passed == total:
            bucket = "delivery_ready"
        elif total and qc_passed == total:
            bucket = "qa"
        elif total and production_done == total:
            bucket = "qc"
        else:
            bucket = "production"
        production_actual = sum(
            (row["production_quantity"] or 0.0) for row in active
        )
        team_leader = None
        if package.team_leader_user_id:
            tl = db.get(User, package.team_leader_user_id)
            team_leader = {"id": package.team_leader_user_id,
                           "full_name": tl.full_name if tl else None}
        context[package.id] = {
            "has_items": True,
            "active_count": len(active),
            "rows": rows,  # all rows (active + inactive) with names resolved
            "aggregate": counts,
            "stage_bucket": bucket,
            "production_actual": production_actual,
            "declared_total_files": package.total_files,
            "ready_confirmed": package.ready_for_delivery_at is not None,
            # Derived per-stage activity flags so every screen can show the SAME
            # stage status (no screen may report "not started" once work has begun).
            "stage_started": {
                stage: any((row.get(f"{stage}_status") or "not_started") != "not_started" for row in active)
                for stage in ("production", "qc", "qa")
            },
            "stage_rework": {
                stage: any((row.get(f"{stage}_status") or "") in {"rejected", "rework"} for row in active)
                for stage in ("qc", "qa")
            },
            "team_leader": team_leader,
            "item_assignees": {
                "production": assignee_list("production_user_id", "production_user"),
                "qc": assignee_list("qc_user_id", "qc_user"),
                "qa": assignee_list("qa_user_id", "qa_user"),
            },
        }
    return context


def activity_rows_for_packages(db: Session, package_ids: Iterable[int]) -> list[dict]:
    """Append-only activity rows (one per session/attempt) for the ACTIVITY HISTORY and
    LEGACY TILE ACTIVITY report sheets. Sessions are never merged into one row."""
    package_ids = list(package_ids)
    if not package_ids:
        return []
    acts = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_id.in_(package_ids)
    ).order_by(WorkPackageItemActivity.work_package_item_id.asc(), WorkPackageItemActivity.id.asc())).all()
    if not acts:
        return []
    items = {i.id: i for i in items_for_packages(db, package_ids)}
    packages = {p.id: p for p in db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.id.in_(package_ids))).all()}
    user_ids = {a.employee_user_id for a in acts if a.employee_user_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    rows: list[dict] = []
    for act in acts:
        item = items.get(act.work_package_item_id)
        package = packages.get(act.work_package_id) if item is not None or act.work_package_id else None
        started = act.started_at
        rows.append({
            "activity_id": act.id,
            "work_package_item_id": act.work_package_item_id,
            "item_number": item.item_number if item else None,
            "item_name": item.item_name if item else None,
            "planned_quantity": float(item.planned_quantity) if item and item.planned_quantity is not None else None,
            "planned_unit": item.planned_unit if item else None,
            "work_package_id": act.work_package_id,
            "package_code": package.package_code if package else None,
            "area_name": package.package_name if package else None,
            "lot_batch": package.lot_batch if package else None,
            "stage": act.stage,
            "employee_user_id": act.employee_user_id,
            "employee": users.get(act.employee_user_id).full_name if act.employee_user_id in users else None,
            "performed_role": act.performed_role,
            "date": started.date().isoformat() if started else None,
            "started_at": started.isoformat() if started else None,
            "ended_at": act.ended_at.isoformat() if act.ended_at else None,
            "duration_seconds": act.duration_seconds,
            "quantity_completed": float(act.quantity_completed) if act.quantity_completed is not None else None,
            "unit": act.unit,
            "files_completed": int(act.files_completed or 0),
            "status": act.status,
            "attempt_type": act.attempt_type,
            "attempt_number": act.attempt_number,
            "finalized": act.stage == "production" and act.status == "completed",
            "remarks": act.remarks,
            "delay_category": act.delay_category,
            "delay_reason": act.delay_reason,
            "delay_remarks": act.delay_remarks,
            "system_malfunction": bool(act.system_malfunction),
        })
    return rows


def item_rows_for_viewer(rows: list[dict], *, viewer_id: int, privileged: bool) -> list[dict]:
    """Employee viewers see ONLY files they are assigned to (any stage)."""
    if privileged:
        return rows
    return [
        row for row in rows
        if viewer_id in {row.get("production_user_id"), row.get("qc_user_id"), row.get("qa_user_id")}
    ]


def employee_file_totals(db: Session, package_ids: Iterable[int]) -> list[dict]:
    """Employee-wise file/quantity/duration totals for one area (or many).

    Includes ASSIGNED / COMPLETED / PENDING file counts per employee (server-side),
    so the area drawer and EMPLOYEE PRODUCTIVITY never need to compute them in the client.
    """
    package_ids = list(package_ids)
    if not package_ids:
        return []
    items = items_for_packages(db, package_ids)
    latest = latest_activities_by_item(db, package_ids)
    activities = db.scalars(select(WorkPackageItemActivity).where(
        WorkPackageItemActivity.work_package_id.in_(package_ids),
        WorkPackageItemActivity.ended_at.is_not(None),
    )).all()

    assign_stats: dict[int, dict] = {}

    def ensure(uid: int) -> dict:
        return assign_stats.setdefault(uid, {
            "production_assigned": 0, "production_completed": 0, "production_pending": 0,
            "qc_assigned": 0, "qc_passed": 0, "qc_pending": 0,
            "qa_assigned": 0, "qa_passed": 0, "qa_pending": 0,
        })

    # Distinct physical files actually worked per employee (never per session).
    worked_files: dict[int, set[int]] = {}
    for act in activities:
        worked_files.setdefault(act.employee_user_id, set()).add(act.work_package_item_id)
    for uid, file_ids in worked_files.items():
        assign_stats.setdefault(uid, {
            "production_assigned": 0, "production_completed": 0, "production_pending": 0,
            "qc_assigned": 0, "qc_passed": 0, "qc_pending": 0,
            "qa_assigned": 0, "qa_passed": 0, "qa_pending": 0,
        })["files_worked"] = len(file_ids)

    for item in items:
        if not item.is_active:
            continue
        per = latest.get(item.id, {})
        prod_done = per.get("production") is not None and per["production"].status == "completed"
        qc_passed = per.get("qc") is not None and per["qc"].status == "passed"
        qa_passed = per.get("qa") is not None and per["qa"].status == "passed"
        if item.production_user_id:
            stat = ensure(item.production_user_id)
            stat["production_assigned"] += 1
            stat["production_completed" if prod_done else "production_pending"] += 1
        if item.qc_user_id:
            stat = ensure(item.qc_user_id)
            stat["qc_assigned"] += 1
            if qc_passed:
                stat["qc_passed"] += 1
            elif prod_done:
                stat["qc_pending"] += 1
        if item.qa_user_id:
            stat = ensure(item.qa_user_id)
            stat["qa_assigned"] += 1
            if qa_passed:
                stat["qa_passed"] += 1
            elif qc_passed:
                stat["qa_pending"] += 1

    totals: dict[tuple[int, str], dict] = {}
    for act in activities:
        key = (act.employee_user_id, act.unit or "")
        entry = totals.setdefault(key, {
            "employee_user_id": act.employee_user_id,
            "employee": None,
            "files_completed": 0,
            "quantity_completed": Decimal("0"),
            "unit": act.unit,
            "duration_seconds": 0,
        })
        entry["files_completed"] += int(act.files_completed or 0)
        if act.quantity_completed is not None:
            entry["quantity_completed"] += act.quantity_completed
        entry["duration_seconds"] += int(act.duration_seconds or 0)
    # Employees who are assigned but have not worked yet still appear (0 progress).
    for uid in assign_stats:
        if not any(key[0] == uid for key in totals):
            totals[(uid, "")] = {
                "employee_user_id": uid, "employee": None, "files_completed": 0,
                "quantity_completed": Decimal("0"), "unit": None, "duration_seconds": 0,
            }

    user_ids = {uid for uid in assign_stats} | {act.employee_user_id for act in activities}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    rows = sorted(totals.values(), key=lambda r: (r["employee_user_id"], r["unit"] or ""))
    for row in rows:
        row["employee"] = users.get(row["employee_user_id"]).full_name if row["employee_user_id"] in users else None
        row["quantity_completed"] = float(row["quantity_completed"])
        row.update(assign_stats.get(row["employee_user_id"], {
            "production_assigned": 0, "production_completed": 0, "production_pending": 0,
            "qc_assigned": 0, "qc_passed": 0, "qc_pending": 0,
            "qa_assigned": 0, "qa_passed": 0, "qa_pending": 0, "files_worked": 0,
        }))
        row.setdefault("files_worked", 0)
    return rows
