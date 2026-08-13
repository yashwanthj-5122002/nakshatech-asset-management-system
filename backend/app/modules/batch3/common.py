from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.entities import Asset, AssetHistory, User

ASSET_CODE_LOCK_KEY = 620260813
IMPORT_AUDIT_FIELDS = (
    "used_by", "workstation_no", "department", "cpu_asset_tag", "monitor_asset_tags",
    "mouse_asset_tag", "keyboard_asset_tag", "system_name", "brand", "model",
    "serial_number", "connection_type", "capacity", "ownership", "client_name",
    "project_id", "current_holder", "device_type", "processor", "memory_gb", "ssd",
    "hdd", "ip_address", "mac_address", "graphics_card", "operating_system",
    "antivirus", "network_type", "approved_by", "price", "remarks", "asset_date",
    "location", "work_mode", "status",
)

def acquire_asset_code_lock(db: Session) -> None:
    """Serialize code allocation/import numbering on PostgreSQL.

    The unique database indexes remain the final safety net. SQLite test runs do
    not support advisory locks, so they keep normal transaction behavior.
    """

    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": ASSET_CODE_LOCK_KEY})


def snapshot_assets(db: Session) -> dict[int, dict[str, Any]]:
    rows = db.scalars(select(Asset)).all()
    return {
        asset.id: {field: getattr(asset, field, None) for field in IMPORT_AUDIT_FIELDS}
        for asset in rows
    }


def _reporting_month_for_asset(asset: Asset) -> str:
    if asset.asset_date:
        return asset.asset_date.strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")


def record_import_audit(
    db: Session,
    *,
    before: dict[int, dict[str, Any]],
    user: User,
    source_label: str,
    update_change_type: str,
    source_sheet: str | None = None,
) -> dict[str, int]:
    """Record created/updated assets after an existing Excel import completes."""

    query = select(Asset)
    if source_sheet:
        query = query.where(Asset.source_sheet == source_sheet)
    assets = list(db.scalars(query).all())
    created = 0
    updated = 0
    for asset in assets:
        after = {field: getattr(asset, field, None) for field in IMPORT_AUDIT_FIELDS}
        old = before.get(asset.id)
        if old is None:
            db.add(AssetHistory(
                asset_id=asset.id,
                action=f"Asset created from {source_label}",
                change_type="asset_created",
                batch_code=f"IMPORT-{asset.id}-{int(datetime.now(timezone.utc).timestamp())}",
                old_value=None,
                new_value=json.dumps({"asset_code": asset.asset_code, **after}, default=str, ensure_ascii=False),
                remarks=f"Created through {source_label}",
                reason=f"{source_label} import",
                changed_by=user.email,
                changed_by_name=user.full_name,
                changed_by_role=user.role,
                field_count=len(after),
                reporting_month=_reporting_month_for_asset(asset),
            ))
            created += 1
            continue

        changed = {
            field: {"from": old.get(field), "to": after.get(field)}
            for field in IMPORT_AUDIT_FIELDS
            if old.get(field) != after.get(field)
        }
        if not changed:
            continue
        db.add(AssetHistory(
            asset_id=asset.id,
            action=f"Asset updated from {source_label}",
            change_type=update_change_type,
            batch_code=f"IMPORT-{asset.id}-{int(datetime.now(timezone.utc).timestamp())}",
            old_value=json.dumps({key: value["from"] for key, value in changed.items()}, default=str, ensure_ascii=False),
            new_value=json.dumps({key: value["to"] for key, value in changed.items()}, default=str, ensure_ascii=False),
            remarks=f"Updated through {source_label}",
            reason=f"{source_label} import",
            changed_by=user.email,
            changed_by_name=user.full_name,
            changed_by_role=user.role,
            field_count=len(changed),
            reporting_month=_reporting_month_for_asset(asset),
        ))
        updated += 1
    db.commit()
    return {"audit_created": created, "audit_updated": updated}


def enrich_external_hdd_import_actor(
    db: Session,
    *,
    user: User,
    source_sheet: str | None,
) -> int:
    if not source_sheet:
        return 0
    asset_ids = list(db.scalars(select(Asset.id).where(Asset.source_sheet == source_sheet)).all())
    if not asset_ids:
        return 0
    histories = list(db.scalars(select(AssetHistory).where(
        AssetHistory.asset_id.in_(asset_ids),
        AssetHistory.reason == "External HDD Excel import",
        AssetHistory.changed_by.is_(None),
    )).all())
    for history in histories:
        history.changed_by = user.email
        history.changed_by_name = user.full_name
        history.changed_by_role = user.role
        if not history.reporting_month:
            asset = db.get(Asset, history.asset_id)
            if asset is not None:
                history.reporting_month = _reporting_month_for_asset(asset)
    if histories:
        db.commit()
    return len(histories)
