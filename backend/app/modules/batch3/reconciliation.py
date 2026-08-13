from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import Asset
from app.services.asset_lifecycle_service import (
    canonical_device_type,
    inventory_integrity,
    inventory_summary,
    is_primary_device_type,
    lifecycle_bucket,
)

def reconciliation_report(db: Session) -> dict[str, Any]:
    assets = list(db.scalars(select(Asset)).all())
    primary = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    primary_summary = inventory_summary(primary)
    all_summary = inventory_summary(assets)
    integrity = inventory_integrity(primary, assets)

    duplicate_codes = list(db.execute(
        select(Asset.asset_code, func.count(Asset.id)).group_by(Asset.asset_code).having(func.count(Asset.id) > 1)
    ).all())
    duplicate_serials = list(db.execute(
        select(func.lower(Asset.serial_number), func.count(Asset.id))
        .where(Asset.serial_number.is_not(None), func.trim(Asset.serial_number) != "")
        .group_by(func.lower(Asset.serial_number))
        .having(func.count(Asset.id) > 1)
    ).all())
    duplicate_tags = list(db.execute(
        select(func.lower(Asset.cpu_asset_tag), func.count(Asset.id))
        .where(Asset.cpu_asset_tag.is_not(None), func.trim(Asset.cpu_asset_tag) != "")
        .group_by(func.lower(Asset.cpu_asset_tag))
        .having(func.count(Asset.id) > 1)
    ).all())
    invalid_available = [asset.asset_code for asset in primary if lifecycle_bucket(asset.status) == "available" and str(asset.used_by or "").strip()]
    incomplete_assigned = [
        asset.asset_code
        for asset in primary
        if lifecycle_bucket(asset.status) == "assigned"
        and canonical_device_type(asset.device_type) in {"Computer", "Laptop"}
        and (not str(asset.used_by or "").strip() or not str(asset.department or "").strip() or not str(asset.workstation_no or "").strip())
    ]
    checks = {
        "device_breakdown_reconciled": bool(integrity["device_reconciled"]),
        "lifecycle_breakdown_reconciled": bool(integrity["lifecycle_reconciled"]),
        "external_hdd_separate": primary_summary["total"] + all_summary["external_hdds"] == len(assets),
        "asset_codes_unique": not duplicate_codes,
        "serial_numbers_unique": not duplicate_serials,
        "asset_tags_unique": not duplicate_tags,
        "available_assets_have_no_custodian": not invalid_available,
        "assigned_computers_have_complete_custody": not incomplete_assigned,
    }
    return {
        "status": "healthy" if all(checks.values()) else "issues_found",
        "checks": checks,
        "counts": {
            "tracked_records": len(assets),
            "primary_it_assets": primary_summary["total"],
            "external_hdds": all_summary["external_hdds"],
            "computers": primary_summary["computers"],
            "laptops": primary_summary["laptops"],
            "smartphones": primary_summary["smartphones"],
            "printers": primary_summary["printers"],
            "assigned": primary_summary["assigned"],
            "available": primary_summary["available"],
            "repair": primary_summary["repair"],
            "replacement_pending": primary_summary["replacement_pending"],
            "returned": primary_summary["returned"],
            "damaged": primary_summary["damaged"],
            "terminal": primary_summary["terminal"],
        },
        "issues": {
            "duplicate_asset_codes": [row[0] for row in duplicate_codes],
            "duplicate_serial_numbers": [row[0] for row in duplicate_serials],
            "duplicate_asset_tags": [row[0] for row in duplicate_tags],
            "available_with_custodian": invalid_available,
            "incomplete_assigned_computers": incomplete_assigned,
        },
    }
