from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Asset, User
from app.modules.asset_return.models import SpareMonitor


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def stage_spare_monitor_component_change(db: Session, payload, user: User) -> None:
    """Stage retained-spare mutations in the caller's component-change transaction.

    ``app.api.router.create_component_change_batch`` commits the Session only
    after it has validated and written the Asset, WorkRecord, ComponentReplacement
    and AssetHistory rows. Mutating retained spares before calling that function
    makes the spare state part of the same commit. The wrapper rolls back if the
    existing component workflow rejects the request.
    """

    target = db.scalar(select(Asset).where(Asset.id == payload.asset_id).with_for_update())
    if target is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if str(target.status or "").strip().lower() == "returned_to_vendor":
        raise HTTPException(
            status_code=409,
            detail="This asset has been returned to the vendor and cannot receive component changes",
        )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for item in payload.items:
        if item.component_type.strip().lower() != "monitor":
            continue

        new_spare = db.scalar(
            select(SpareMonitor)
            .where(SpareMonitor.monitor_tag.ilike(item.new_value.strip()))
            .with_for_update()
        )
        if new_spare is not None:
            if new_spare.status != "available":
                current = db.get(Asset, new_spare.current_asset_id) if new_spare.current_asset_id else None
                suffix = f" on {current.cpu_asset_tag or current.asset_code}" if current else ""
                raise HTTPException(
                    status_code=409,
                    detail=f"Retained spare monitor {new_spare.monitor_tag} is {new_spare.status}{suffix}",
                )
            new_spare.status = "in_use"
            new_spare.current_asset_id = payload.asset_id
            new_spare.assigned_at = now
            new_spare.assigned_by_name = user.full_name
            new_spare.assigned_by_email = user.email
            new_spare.assigned_by_role = user.role
            new_spare.remarks = f"Assigned through Component Changes to asset ID {payload.asset_id}"

        old_tag = _clean(item.old_value)
        if old_tag and old_tag.casefold() not in {"not previously recorded", "not recorded", "-"}:
            old_spare = db.scalar(
                select(SpareMonitor)
                .where(SpareMonitor.monitor_tag.ilike(old_tag))
                .with_for_update()
            )
            if old_spare is not None and old_spare.current_asset_id == payload.asset_id:
                condition = str(item.old_condition or "").casefold()
                damaged = any(token in condition for token in ("damage", "fault", "not working", "broken", "dead"))
                old_spare.status = "damaged" if damaged else "available"
                old_spare.current_asset_id = None
                old_spare.assigned_at = None
                old_spare.assigned_by_name = user.full_name
                old_spare.assigned_by_email = user.email
                old_spare.assigned_by_role = user.role
                old_spare.remarks = (
                    f"Removed from asset ID {payload.asset_id}; "
                    + ("marked damaged from Component Changes" if damaged else "returned to spare pool")
                )
