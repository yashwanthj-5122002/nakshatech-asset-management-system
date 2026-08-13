from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

# Batch 3A keeps one authoritative classification layer for dashboard KPIs,
# drill-downs and reports. External HDDs remain a separate inventory register
# and therefore do not inflate the primary Total IT Assets KPI.
PRIMARY_EXCLUDED_DEVICE_TYPES = {"External HDD"}

DEVICE_TYPE_ALIASES = {
    "computer": "Computer",
    "desktop": "Computer",
    "desktop computer": "Computer",
    "desktop pc": "Computer",
    "pc": "Computer",
    "workstation": "Computer",
    "laptop": "Laptop",
    "notebook": "Laptop",
    "smartphone": "Smartphone",
    "smart phone": "Smartphone",
    "mobile": "Smartphone",
    "mobile phone": "Smartphone",
    "phone": "Smartphone",
    "printer": "Printer",
    "external hdd": "External HDD",
    "external hard drive": "External HDD",
    "external hard disk": "External HDD",
    "portable hard drive": "External HDD",
    "server": "Server",
    "network device": "Network Device",
    "network equipment": "Network Device",
    "network": "Network Device",
    "other": "Other",
}

CANONICAL_DEVICE_TYPES = {
    "Computer",
    "Laptop",
    "Smartphone",
    "Printer",
    "External HDD",
    "Server",
    "Network Device",
    "Other",
}

ASSIGNED_LIFECYCLE_STATUSES = {
    "assigned",
    "in_use",
    "wfh",
    "field_deployment",
    "issued",
    "permanently_issued",
}
REPAIR_LIFECYCLE_STATUSES = {"repair", "under_repair", "under_inspection"}
REPLACEMENT_LIFECYCLE_STATUSES = {"replacement_pending"}
DAMAGED_LIFECYCLE_STATUSES = {"damaged", "beyond_repair", "for_parts", "disposal_pending", "missing"}
TERMINAL_LIFECYCLE_STATUSES = {"replaced", "retired", "disposed"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def canonical_device_type(value: Any) -> str:
    """Return the canonical reporting category for an existing device value.

    Unknown legacy values are deliberately grouped under Other instead of being
    dropped from totals. This makes device-breakdown reconciliation lossless.
    """
    text = _text(value)
    if not text:
        return "Other"
    canonical = DEVICE_TYPE_ALIASES.get(text.casefold())
    if canonical:
        return canonical
    for known in CANONICAL_DEVICE_TYPES:
        if text.casefold() == known.casefold():
            return known
    return "Other"


def is_supported_device_type(value: Any) -> bool:
    """Whether a new/edited asset value is an accepted canonical type or alias."""
    text = _text(value)
    if not text:
        return False
    normalized = text.casefold()
    return normalized in DEVICE_TYPE_ALIASES or any(normalized == item.casefold() for item in CANONICAL_DEVICE_TYPES)


def is_primary_device_type(value: Any) -> bool:
    return canonical_device_type(value) not in PRIMARY_EXCLUDED_DEVICE_TYPES


def normalized_status(value: Any) -> str:
    return _text(value).lower().replace("-", "_").replace(" ", "_") or "unknown"


def lifecycle_bucket(value: Any) -> str:
    status = normalized_status(value)
    if status in ASSIGNED_LIFECYCLE_STATUSES:
        return "assigned"
    if status == "available":
        return "available"
    if status in REPAIR_LIFECYCLE_STATUSES:
        return "repair"
    if status in REPLACEMENT_LIFECYCLE_STATUSES:
        return "replacement_pending"
    if status == "returned":
        return "returned"
    if status in DAMAGED_LIFECYCLE_STATUSES:
        return "damaged"
    if status in TERMINAL_LIFECYCLE_STATUSES:
        return "terminal"
    return "other"


def status_matches(asset_status: Any, requested: str | None) -> bool:
    if not requested:
        return True
    requested_status = normalized_status(requested)
    current = normalized_status(asset_status)
    if requested_status in {"assigned", "assigned_in_use", "assigned_/_in_use"}:
        return current in ASSIGNED_LIFECYCLE_STATUSES
    if requested_status in {"repair", "under_repair"}:
        return current in REPAIR_LIFECYCLE_STATUSES
    if requested_status in {"damaged", "at_risk"}:
        return current in DAMAGED_LIFECYCLE_STATUSES
    if requested_status in {"terminal", "retired_finalized"}:
        return current in TERMINAL_LIFECYCLE_STATUSES
    return current == requested_status


def inventory_summary(assets: Iterable[Any]) -> dict[str, int]:
    rows = list(assets)
    devices = Counter(canonical_device_type(getattr(asset, "device_type", None)) for asset in rows)
    raw_statuses = Counter(normalized_status(getattr(asset, "status", None)) for asset in rows)
    lifecycle = Counter(lifecycle_bucket(getattr(asset, "status", None)) for asset in rows)
    return {
        "total": len(rows),
        "computers": devices.get("Computer", 0),
        "laptops": devices.get("Laptop", 0),
        "smartphones": devices.get("Smartphone", 0),
        "printers": devices.get("Printer", 0),
        "external_hdds": devices.get("External HDD", 0),
        "servers": devices.get("Server", 0),
        "network_devices": devices.get("Network Device", 0),
        "other": devices.get("Other", 0),
        "assigned": lifecycle.get("assigned", 0),
        "available": lifecycle.get("available", 0),
        "repair": lifecycle.get("repair", 0),
        "replacement_pending": lifecycle.get("replacement_pending", 0),
        "returned": lifecycle.get("returned", 0),
        "damaged": lifecycle.get("damaged", 0),
        "terminal": lifecycle.get("terminal", 0),
        "other_lifecycle": lifecycle.get("other", 0),
        "wfh": raw_statuses.get("wfh", 0),
        "field": raw_statuses.get("field_deployment", 0),
        "issued": raw_statuses.get("issued", 0),
        "permanently_issued": raw_statuses.get("permanently_issued", 0),
    }


def device_distribution(assets: Iterable[Any]) -> list[dict[str, int | str]]:
    counts = Counter(canonical_device_type(getattr(asset, "device_type", None)) for asset in assets)
    return [
        {"name": name, "value": value, "key": name}
        for name, value in sorted(counts.items(), key=lambda item: (-item[1], item[0].casefold()))
        if value > 0
    ]


def lifecycle_status_distribution(assets: Iterable[Any]) -> list[dict[str, int | str]]:
    counts = Counter(lifecycle_bucket(getattr(asset, "status", None)) for asset in assets)
    order = [
        ("assigned", "Assigned / In Use"),
        ("available", "Available"),
        ("repair", "Under Repair"),
        ("replacement_pending", "Replacement Pending"),
        ("returned", "Returned"),
        ("damaged", "Damaged / At Risk"),
        ("terminal", "Retired / Finalized"),
        ("other", "Other / Legacy"),
    ]
    return [
        {"name": label, "value": counts.get(key, 0), "key": key}
        for key, label in order
        if counts.get(key, 0) > 0
    ]


def inventory_integrity(primary_assets: Iterable[Any], all_assets: Iterable[Any]) -> dict[str, int | bool]:
    primary_rows = list(primary_assets)
    all_rows = list(all_assets)
    primary_summary = inventory_summary(primary_rows)
    all_summary = inventory_summary(all_rows)
    device_total = sum(
        primary_summary[key]
        for key in ("computers", "laptops", "smartphones", "printers", "servers", "network_devices", "other")
    )
    lifecycle_total = sum(
        primary_summary[key]
        for key in ("assigned", "available", "repair", "replacement_pending", "returned", "damaged", "terminal", "other_lifecycle")
    )
    return {
        "tracked_records": len(all_rows),
        "primary_records": len(primary_rows),
        "external_hdd_records": all_summary["external_hdds"],
        "device_breakdown_total": device_total,
        "lifecycle_breakdown_total": lifecycle_total,
        "device_reconciled": device_total == len(primary_rows),
        "lifecycle_reconciled": lifecycle_total == len(primary_rows),
    }


# Batch 3B: one custody-state transition layer shared by Asset Register and
# Handover & Return. These helpers mutate only live assignment/lifecycle fields;
# callers remain responsible for audit history and transaction commit.
RETURN_FINAL_STATUSES = {"available", "repair", "damaged", "returned"}
ASSIGNMENT_BLOCKED_BUCKETS = {"repair", "replacement_pending", "damaged", "terminal"}


class AssetLifecycleTransitionError(ValueError):
    """Raised when a custody/lifecycle transition would create an invalid state."""


def assignment_status_for_work_mode(work_mode: Any) -> tuple[str, str]:
    mode = normalized_status(work_mode or "office")
    if mode == "field_deployment":
        mode = "field"
    if mode not in {"office", "wfh", "field"}:
        raise AssetLifecycleTransitionError("Work mode must be office, wfh or field")
    return mode, {"office": "assigned", "wfh": "wfh", "field": "field_deployment"}[mode]


def custody_state(asset: Any) -> dict[str, Any]:
    """Snapshot the live fields that define who currently holds an asset."""
    return {
        "used_by": getattr(asset, "used_by", None),
        "department": getattr(asset, "department", None),
        "workstation_no": getattr(asset, "workstation_no", None),
        "location": getattr(asset, "location", None),
        "work_mode": getattr(asset, "work_mode", None),
        "status": getattr(asset, "status", None),
        "asset_date": getattr(asset, "asset_date", None),
    }


def _assignment_block_reason(asset: Any) -> str | None:
    bucket = lifecycle_bucket(getattr(asset, "status", None))
    if bucket == "repair":
        return "Assets under repair or inspection cannot be assigned or handed over"
    if bucket == "replacement_pending":
        return "Assets pending replacement cannot be assigned or handed over"
    if bucket == "damaged":
        return "Damaged, missing or disposal-pending assets cannot be assigned or handed over"
    if bucket == "terminal":
        return "Retired, replaced or disposed assets cannot be assigned or handed over"
    return None


def apply_assignment_transition(
    asset: Any,
    *,
    used_by: str | None,
    department: str | None,
    workstation_no: str | None,
    location: str | None = None,
    work_mode: str | None = "office",
    transition_date: Any = None,
    action: str = "assign",
) -> dict[str, Any]:
    """Apply an authoritative assignment/handover/transfer state transition.

    ``handover`` refuses to overwrite an already-assigned custodian; callers
    must explicitly use ``transfer`` for that operation. ``assign`` retains the
    Asset Register's existing assign/transfer behavior while still blocking
    assets that are not operationally assignable.
    """
    reason = _assignment_block_reason(asset)
    if reason:
        raise AssetLifecycleTransitionError(reason)

    action_key = normalized_status(action)
    current_bucket = lifecycle_bucket(getattr(asset, "status", None))
    current_user = _text(getattr(asset, "used_by", None))
    current_ws = _text(getattr(asset, "workstation_no", None))

    if action_key == "handover":
        if current_bucket == "assigned" and (current_user or current_ws):
            raise AssetLifecycleTransitionError("Asset is already assigned; use Transfer to change the custodian")
        if current_bucket != "available":
            raise AssetLifecycleTransitionError("Only an available asset can be handed over")
        if current_user:
            raise AssetLifecycleTransitionError("Available asset has an employee recorded; correct the Asset Register before handover")
    if action_key == "transfer":
        if current_bucket != "assigned":
            raise AssetLifecycleTransitionError("Only an assigned/in-use asset can be transferred")
        if canonical_device_type(getattr(asset, "device_type", None)) in {"Computer", "Laptop"} and not current_user:
            raise AssetLifecycleTransitionError("Assigned laptop/desktop has no current custodian; correct the Asset Register before transfer")

    mode, target_status = assignment_status_for_work_mode(work_mode)
    next_user = _text(used_by)
    if action_key == "transfer" and current_user and next_user and current_user.casefold() == next_user.casefold():
        raise AssetLifecycleTransitionError("Transfer destination must be different from the current custodian")
    next_department = _text(department) or _text(getattr(asset, "department", None))
    next_workstation = _text(workstation_no)

    # Handover/Transfer must never create an incomplete custody record. The
    # Asset Register's generic assign endpoint retains its existing validation
    # path so its historical 400-level validation semantics stay unchanged.
    if action_key in {"handover", "transfer"} and canonical_device_type(getattr(asset, "device_type", None)) in {"Computer", "Laptop"}:
        missing = []
        if not next_user:
            missing.append("Employee / Custodian")
        if not next_department:
            missing.append("Department")
        if not next_workstation:
            missing.append("Workstation / DC Number")
        if missing:
            raise AssetLifecycleTransitionError(
                "Assigned laptops/desktops require: " + ", ".join(missing)
            )

    asset.used_by = next_user or None
    asset.department = next_department or None
    asset.workstation_no = next_workstation or None
    if _text(location):
        asset.location = _text(location)
    asset.work_mode = mode
    asset.status = target_status
    if transition_date is not None:
        asset.asset_date = transition_date
    return custody_state(asset)


def apply_return_transition(
    asset: Any,
    *,
    final_status: str = "available",
    transition_date: Any = None,
    require_active_custodian: bool = False,
) -> dict[str, Any]:
    """Apply the shared Asset Register / Handover return cleanup.

    Department and physical location are intentionally preserved. The former
    custodian, workstation and work-mode assignment are cleared consistently.
    """
    status = normalized_status(final_status)
    if status not in RETURN_FINAL_STATUSES:
        raise AssetLifecycleTransitionError(
            "Return status must be available, repair, damaged or returned"
        )

    if lifecycle_bucket(getattr(asset, "status", None)) == "terminal":
        raise AssetLifecycleTransitionError("Retired, replaced or disposed assets cannot be returned")

    current_user = _text(getattr(asset, "used_by", None))
    current_ws = _text(getattr(asset, "workstation_no", None))
    current_status = normalized_status(getattr(asset, "status", None))
    current_bucket = lifecycle_bucket(getattr(asset, "status", None))
    if require_active_custodian:
        if current_bucket != "assigned":
            raise AssetLifecycleTransitionError("Only an assigned/in-use asset can be returned")
        if canonical_device_type(getattr(asset, "device_type", None)) in {"Computer", "Laptop"} and not current_user:
            raise AssetLifecycleTransitionError("Assigned laptop/desktop has no current custodian; correct the Asset Register before return")
    if not current_user and not current_ws and current_status in {"available", "returned"}:
        raise AssetLifecycleTransitionError("Asset is already returned and has no active custodian")

    asset.used_by = None
    asset.workstation_no = None
    asset.work_mode = "office"
    asset.status = status
    if transition_date is not None:
        asset.asset_date = transition_date
    return custody_state(asset)
