"""Department stage profiles and progress formulas for shared production tracking (V8.1).

One work-package record is the shared production record for its whole life
(Allocation → Daily Production → Production Complete → QC → QA → Delivery, plus
optional additional processing stages). This module is the single place that:

1. declares which stages are applicable per performing department (LiDAR adds
   Import / DXF / Inspection / Upload on top of the universal
   Production → QC → QA → Delivery chain; every other department keeps the
   universal chain unchanged);
2. derives each stage's completion from the AUTHORITATIVE workflow state already
   maintained by ``workflow_service`` (never from typed-in percentages);
3. computes package / project production and workflow progress with explicit,
   documented rules for zero targets, null targets, unknown units, mixed
   measurement types and over-target production.

Extension point: add a department code to ``STAGE_PROFILES`` — no existing
department's behaviour changes, and the core Production → QC → QA → Delivery
transitions are never re-implemented here.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Iterable

from app.modules.operations.uom import measurement_type, normalize_quantity

STAGE_PRODUCTION = "production"
STAGE_QC = "qc"
STAGE_QA = "qa"
STAGE_DELIVERY = "delivery"

STAGE_IMPORT = "import"
STAGE_DXF = "dxf"
STAGE_INSPECTION = "inspection"
STAGE_UPLOAD = "upload"

UNIVERSAL_STAGES: tuple[str, ...] = (STAGE_PRODUCTION, STAGE_QC, STAGE_QA, STAGE_DELIVERY)

# Department stage profiles. Departments absent from this map use UNIVERSAL_STAGES.
STAGE_PROFILES: dict[str, tuple[str, ...]] = {
    "lidar": (STAGE_IMPORT, STAGE_PRODUCTION, STAGE_QC, STAGE_QA, STAGE_DXF, STAGE_INSPECTION, STAGE_DELIVERY, STAGE_UPLOAD),
}

# Stages handled by the additive generic stage endpoint (production/qc/qa/delivery
# keep their existing authoritative workflow endpoints untouched).
TRACKABLE_STAGES: tuple[str, ...] = (STAGE_IMPORT, STAGE_DXF, STAGE_INSPECTION, STAGE_UPLOAD)

STAGE_STATUSES: dict[str, tuple[str, ...]] = {
    STAGE_IMPORT: ("not_started", "in_progress", "completed", "on_hold"),
    STAGE_DXF: ("not_started", "pending", "in_progress", "approved", "rejected"),
    STAGE_INSPECTION: ("pending", "inspected", "not_inspected"),
    STAGE_UPLOAD: ("pending", "in_progress", "uploaded", "on_hold"),
}

STAGE_STATUS_ATTR: dict[str, str] = {
    STAGE_IMPORT: "import_status",
    STAGE_DXF: "dxf_status",
    STAGE_INSPECTION: "inspection_status",
    STAGE_UPLOAD: "upload_status",
}
STAGE_TIMESTAMP_ATTR: dict[str, str] = {
    STAGE_IMPORT: "imported_at",
    STAGE_DXF: "dxf_at",
    STAGE_INSPECTION: "inspected_at",
    STAGE_UPLOAD: "uploaded_at",
}

STAGE_COMPLETED_STATUSES: dict[str, frozenset[str]] = {
    STAGE_PRODUCTION: frozenset({"completed"}),
    STAGE_QC: frozenset({"approved"}),
    STAGE_QA: frozenset({"approved"}),
    STAGE_DELIVERY: frozenset({"delivered"}),
    STAGE_IMPORT: frozenset({"completed"}),
    STAGE_DXF: frozenset({"approved"}),
    STAGE_INSPECTION: frozenset({"inspected"}),
    STAGE_UPLOAD: frozenset({"uploaded"}),
}

STAGE_LABELS: dict[str, str] = {
    STAGE_PRODUCTION: "Production",
    STAGE_QC: "QC",
    STAGE_QA: "QA",
    STAGE_DELIVERY: "Delivery",
    STAGE_IMPORT: "Import",
    STAGE_DXF: "DXF",
    STAGE_INSPECTION: "Inspection",
    STAGE_UPLOAD: "Upload",
}


def stage_profile_for_department(department_code: str | None) -> tuple[str, ...]:
    """Applicable, ordered stage list for a performing department."""
    code = (department_code or "").strip().lower()
    return STAGE_PROFILES.get(code, UNIVERSAL_STAGES)


def stage_status(package: Any, stage: str) -> str | None:
    """Current status of a stage derived from the package's authoritative fields."""
    if stage == STAGE_PRODUCTION:
        return getattr(package, "production_state", None)
    if stage == STAGE_QC:
        return getattr(package, "qc_state", None)
    if stage == STAGE_QA:
        return getattr(package, "qa_state", None)
    if stage == STAGE_DELIVERY:
        return "delivered" if getattr(package, "current_stage", None) == "delivered" else "pending"
    attr = STAGE_STATUS_ATTR.get(stage)
    return getattr(package, attr, None) if attr else None


def stage_is_complete(package: Any, stage: str) -> bool:
    status = stage_status(package, stage)
    if status is None:
        return False
    if stage == STAGE_DELIVERY:
        return status == "delivered"
    return status in STAGE_COMPLETED_STATUSES.get(stage, frozenset())


def pending_stages(package: Any, department_code: str | None) -> list[str]:
    return [stage for stage in stage_profile_for_department(department_code) if not stage_is_complete(package, stage)]


def item_stage_complete(item_ctx: dict | None, stage: str) -> bool | None:
    """File-tracked areas derive stage completion from their item rollups.

    Returns None when the area is NOT file-tracked (caller falls back to the legacy
    package-level field). This keeps ONE source of truth: for areas with active
    WorkPackageItems, Production/QC/QA/Delivery completion is counted from the same
    file counts the dashboards and reports use.
    """
    if not item_ctx or not item_ctx.get("has_items"):
        return None
    counts = item_ctx.get("aggregate") or {}
    expected = int(counts.get("files_expected") or item_ctx.get("active_count") or 0)
    if expected <= 0:
        return None
    if stage == STAGE_PRODUCTION:
        return int(counts.get("files_production_done", 0)) >= expected
    if stage == STAGE_QC:
        return int(counts.get("files_qc_passed", 0)) >= expected
    if stage == STAGE_QA:
        return int(counts.get("files_qa_passed", 0)) >= expected
    if stage == STAGE_DELIVERY:
        return int(counts.get("files_delivered", 0)) >= expected
    return None


def effective_stage_is_complete(package: Any, stage: str, item_ctx: dict | None = None) -> bool:
    item_done = item_stage_complete(item_ctx, stage)
    return stage_is_complete(package, stage) if item_done is None else item_done


def effective_pending_stages(package: Any, department_code: str | None, item_ctx: dict | None = None) -> list[str]:
    """Pending applicable stages, item-aware for file-tracked areas."""
    return [stage for stage in stage_profile_for_department(department_code)
            if not effective_stage_is_complete(package, stage, item_ctx)]


def item_stage_status(item_ctx: dict | None, package: Any, stage: str) -> str | None:
    """Effective display status for one stage, item-aware when the area tracks files.

    Returns None when the area is not file-tracked (caller uses the legacy field).
    """
    if not item_ctx or not item_ctx.get("has_items"):
        return None
    counts = item_ctx.get("aggregate") or {}
    expected = int(counts.get("files_expected") or item_ctx.get("active_count") or 0)
    started = item_ctx.get("stage_started") or {}
    rework = item_ctx.get("stage_rework") or {}
    if expected <= 0:
        return None
    if stage == STAGE_PRODUCTION:
        if int(counts.get("files_production_done", 0)) >= expected:
            return "completed"
        return "in_progress" if started.get("production") else "not_started"
    if stage == STAGE_QC:
        if int(counts.get("files_qc_passed", 0)) >= expected:
            return "approved"
        if rework.get("qc"):
            return "rejected"
        return "in_progress" if started.get("qc") else "pending"
    if stage == STAGE_QA:
        if int(counts.get("files_qa_passed", 0)) >= expected:
            return "approved"
        if rework.get("qa"):
            return "rejected"
        return "in_progress" if started.get("qa") else "pending"
    if stage == STAGE_DELIVERY:
        return "delivered" if int(counts.get("files_delivered", 0)) >= expected else None
    return None


def package_workflow_progress(package: Any, department_code: str | None, item_ctx: dict | None = None) -> float:
    """Workflow % = completed applicable stages / total applicable stages * 100.

    For file-tracked areas the core stages are derived from the item rollups so
    completed Production/QC/QA can never coexist with a 0 % workflow figure.
    """
    stages = stage_profile_for_department(department_code)
    if not stages:
        return 0.0
    completed = 0
    for stage in stages:
        item_done = item_stage_complete(item_ctx, stage)
        if item_done is not None:
            completed += 1 if item_done else 0
        elif stage_is_complete(package, stage):
            completed += 1
    return round(completed * 100.0 / len(stages), 2)


def package_production_progress(total: Decimal | None, target: Decimal | None) -> dict:
    """Production % for one package (documented, never user-typed).

    - progress = min(100, total / target * 100) when target > 0 (same formula as
      the existing daily-activity calculation in workflow_service);
    - target 0 / null -> 0 % (zero-safe, never divides by zero);
    - actual > target -> 100 % plus an explicit over-target variance so the
      over-target amount is displayed, never discarded.
    """
    total_q = total if total is not None else Decimal("0")
    target_q = target if target is not None else Decimal("0")
    if target_q <= 0:
        percent = 0.0
        remaining = Decimal("0")
    else:
        percent = min(100.0, float((total_q / target_q) * Decimal("100")))
        remaining = max(Decimal("0"), target_q - total_q)
    over = max(Decimal("0"), total_q - target_q)
    return {
        "progress_percent": round(percent, 2),
        "remaining_quantity": remaining,
        "over_target_quantity": over,
    }


def aggregate_project_progress(
    packages: Iterable[Any], department_code: str | None, item_contexts: dict[int, dict] | None = None,
) -> dict:
    """Project-level progress without naive averaging and without mixing units.

    - Packages are grouped by the MEASUREMENT TYPE of their unit (unknown legacy
      units group as their own opaque type and keep working unchanged).
    - Within a single-type group: quantity-weighted production progress
      = sum(base completed) / sum(base target), after converting to the group's
      base unit (1000 m = 1 km; 1 000 000 sq.m = 1 sq.km; 1 hectare = 10000 sq.m).
    - If a project mixes measurement types, each type-group gets an EQUAL voice
      in the overall figure (no authoritative cross-type weighting exists), and
      the per-group breakdown is always exposed. Incompatible units are never
      summed.
    - Workflow progress = mean of per-package workflow progress.
    """
    package_rows = list(packages)
    item_contexts = item_contexts or {}
    groups: dict[str, dict] = {}
    workflow_total = 0.0
    for package in package_rows:
        item_ctx = item_contexts.get(getattr(package, "id", None))
        if item_ctx and item_ctx.get("has_items"):
            # File-tracked area: authoritative actual = cumulative item production quantity.
            total = Decimal(str(item_ctx.get("production_actual", 0.0)))
        else:
            total = getattr(package, "cumulative_total", None)
            if total is None:
                total = sum((row.achieved_area or Decimal("0")) for row in getattr(package, "daily_updates", []))
        target = getattr(package, "area", None) or Decimal("0")
        unit = getattr(package, "area_unit", None)
        ptype = measurement_type(unit) or "opaque:unknown"
        group = groups.setdefault(ptype, {
            "measurement_type": ptype, "display_unit": unit,
            "planned_base": Decimal("0"), "completed_base": Decimal("0"), "packages": 0,
        })
        base_completed, _ = normalize_quantity(total, unit)
        base_target, _ = normalize_quantity(target, unit)
        group["completed_base"] += base_completed
        group["planned_base"] += base_target
        group["packages"] += 1
        workflow_total += package_workflow_progress(package, department_code, item_ctx)

    group_rows = []
    group_percentages: list[float] = []
    for group in groups.values():
        planned = group["planned_base"]
        completed = group["completed_base"]
        percent = 0.0 if planned <= 0 else min(100.0, float((completed / planned) * Decimal("100")))
        group_rows.append({
            "measurement_type": group["measurement_type"],
            "display_unit": group["display_unit"],
            "planned_base_quantity": planned,
            "completed_base_quantity": completed,
            "remaining_base_quantity": max(Decimal("0"), planned - completed),
            "over_target_base_quantity": max(Decimal("0"), completed - planned),
            "production_progress_percent": round(percent, 2),
            "packages": group["packages"],
        })
        group_percentages.append(round(percent, 2))
    group_rows.sort(key=lambda row: row["measurement_type"])
    production_percent = round(sum(group_percentages) / len(group_percentages), 2) if group_percentages else 0.0
    workflow_percent = round(workflow_total / len(package_rows), 2) if package_rows else 0.0
    return {
        "measurement_groups": group_rows,
        "production_progress_percent": production_percent,
        "workflow_progress_percent": workflow_percent,
        "packages": len(package_rows),
        "mixed_measurement_types": len(group_rows) > 1,
        "weighting": "quantity_weighted_within_measurement_type; equal_type_group_weight_across_mixed_types",
    }


