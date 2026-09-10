from __future__ import annotations

from datetime import date, datetime, timezone
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import Asset, AssetHistory, ReplacementRecord, User, WorkRecord
from app.modules.asset_return.models import AssetVendorReturn, SpareMonitor
from app.modules.asset_return.schemas import AssetVendorReturnCreate
from app.services.asset_lifecycle_service import canonical_device_type


RETURNED_TO_VENDOR_STATUS = "returned_to_vendor"
RETURN_REMOVE_DEVICE_TYPES = {"Computer", "Laptop", "Smartphone", "Printer", "External HDD"}
ACTIVE_WORK_STATUSES = {"open", "pending", "in_progress"}
OPEN_REPLACEMENT_STATUSES = {"pending", "returned"}


def is_active_inventory_asset(asset: Any) -> bool:
    return str(getattr(asset, "status", "") or "").strip().lower() != RETURNED_TO_VENDOR_STATUS


def active_inventory_assets(assets: list[Any]) -> list[Any]:
    return [asset for asset in assets if is_active_inventory_asset(asset)]


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def split_monitor_tags(raw: str | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").split(","):
        tag = part.strip()
        key = tag.casefold()
        if not tag or key in seen or key in {"-", "na", "n/a", "own", "not recorded"}:
            continue
        seen.add(key)
        result.append(tag)
    return result


def _json_safe(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def asset_snapshot(asset: Asset) -> dict[str, Any]:
    return {
        column.name: _json_safe(getattr(asset, column.name, None))
        for column in Asset.__table__.columns
    }


def _return_code() -> str:
    return f"VRET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"


def _record_vendor_return_history(
    db: Session,
    *,
    asset: Asset,
    record: AssetVendorReturn,
    before: dict[str, Any],
    user: User,
) -> None:
    after = {
        "status": asset.status,
        "used_by": asset.used_by,
        "workstation_no": asset.workstation_no,
        "current_holder": asset.current_holder,
        "monitor_asset_tags": asset.monitor_asset_tags,
    }
    db.add(AssetHistory(
        asset_id=asset.id,
        action="Rental / vendor asset returned",
        change_type="asset_vendor_return",
        batch_code=record.return_code,
        old_value=json.dumps(before, ensure_ascii=False, default=str),
        new_value=json.dumps(after, ensure_ascii=False, default=str),
        remarks=record.remarks,
        reason=record.reason,
        changed_by=user.email,
        changed_by_name=user.full_name,
        changed_by_role=user.role,
        field_count=sum(str(before.get(key) or "") != str(after.get(key) or "") for key in after),
        reporting_month=record.reporting_month,
    ))


def _active_monitor_owner(db: Session, monitor_tag: str, *, exclude_asset_id: int | None = None) -> Asset | None:
    key = monitor_tag.strip().casefold()
    if not key:
        return None
    for asset in db.scalars(select(Asset)).all():
        if not is_active_inventory_asset(asset):
            continue
        if exclude_asset_id is not None and asset.id == exclude_asset_id:
            continue
        if any(tag.casefold() == key for tag in split_monitor_tags(asset.monitor_asset_tags)):
            return asset
    return None


def perform_vendor_return(
    db: Session,
    asset_id: int,
    payload: AssetVendorReturnCreate,
    user: User,
) -> dict[str, Any]:
    asset = db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update())
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    device_type = canonical_device_type(asset.device_type)
    if device_type not in RETURN_REMOVE_DEVICE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Return / Remove is available only for Computer, Laptop, Smartphone, Printer and External HDD assets",
        )
    if payload.return_mode == "return_without_monitor" and device_type != "Computer":
        raise HTTPException(status_code=400, detail="Keep Monitor is available only for Desktop / Computer assets")
    if not is_active_inventory_asset(asset):
        raise HTTPException(status_code=409, detail="This asset has already been returned / removed from active inventory")
    if db.scalar(select(AssetVendorReturn.id).where(AssetVendorReturn.asset_id == asset.id).limit(1)) is not None:
        raise HTTPException(status_code=409, detail="This asset already has a return record")

    # Asset Register -> Return / Remove is the terminal rental/vendor return.
    # It may be performed directly even when the desktop is still assigned;
    # the previous custodian is snapshotted below and the live custody is cleared
    # in the same transaction. Normal employee-only custody returns remain in
    # the Handover & Return workflow and are not changed here.
    open_work = db.scalar(
        select(WorkRecord.id)
        .where(WorkRecord.asset_id == asset.id, WorkRecord.status.in_(ACTIVE_WORK_STATUSES))
        .limit(1)
    )
    if open_work is not None:
        raise HTTPException(status_code=409, detail="Close the active IT Work Record before returning / removing this asset")
    open_replacement = db.scalar(
        select(ReplacementRecord.id)
        .where(
            or_(ReplacementRecord.old_asset_id == asset.id, ReplacementRecord.new_asset_id == asset.id),
            ReplacementRecord.approval_status.in_(OPEN_REPLACEMENT_STATUSES),
        )
        .limit(1)
    )
    if open_replacement is not None:
        raise HTTPException(status_code=409, detail="Resolve the open complete-asset replacement workflow before returning / removing this asset")

    monitors = split_monitor_tags(asset.monitor_asset_tags)
    if payload.return_mode == "return_without_monitor" and not monitors:
        raise HTTPException(
            status_code=400,
            detail="Keep Monitor requires at least one Monitor Asset Tag on the selected desktop",
        )

    if payload.return_mode == "return_without_monitor":
        for monitor_tag in monitors:
            existing_spare = db.scalar(
                select(SpareMonitor).where(SpareMonitor.monitor_tag.ilike(monitor_tag)).limit(1)
            )
            if existing_spare is not None:
                raise HTTPException(status_code=409, detail=f"Monitor {monitor_tag} already exists in the Spare Monitor Register")
            owner = _active_monitor_owner(db, monitor_tag, exclude_asset_id=asset.id)
            if owner is not None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Monitor {monitor_tag} is also active on {owner.cpu_asset_tag or owner.asset_code}. Correct the duplicate before return / remove.",
                )

    snapshot = asset_snapshot(asset)
    reporting_month = normalize_reporting_month(payload.reporting_month)
    record = AssetVendorReturn(
        return_code=_return_code(),
        asset_id=asset.id,
        asset_code_snapshot=asset.asset_code,
        cpu_asset_tag_snapshot=asset.cpu_asset_tag,
        device_type_snapshot=asset.device_type,
        return_mode=payload.return_mode,
        return_date=payload.return_date,
        vendor_name=payload.vendor_name,
        return_reference=payload.return_reference,
        condition=payload.condition,
        reason=payload.reason,
        remarks=payload.remarks,
        reporting_month=reporting_month,
        previous_status=asset.status,
        previous_used_by=asset.used_by,
        previous_department=asset.department,
        previous_workstation_no=asset.workstation_no,
        monitor_tags_snapshot=", ".join(monitors) or None,
        retained_monitor_tags=", ".join(monitors) if payload.return_mode == "return_without_monitor" else None,
        asset_snapshot_json=json.dumps(snapshot, ensure_ascii=False, default=str),
        performed_by_user_id=user.id,
        performed_by_name=user.full_name,
        performed_by_email=user.email,
        performed_by_role=user.role,
    )
    db.add(record)
    db.flush()

    if payload.return_mode == "return_without_monitor":
        for monitor_tag in monitors:
            db.add(SpareMonitor(
                monitor_tag=monitor_tag,
                source_return_id=record.id,
                source_asset_id=asset.id,
                source_asset_code=asset.asset_code,
                status="available",
                current_asset_id=None,
                location=payload.spare_location or "IT Store",
                retained_date=payload.return_date,
                remarks=f"Retained when desktop {asset.cpu_asset_tag or asset.asset_code} was returned / removed",
            ))

    history_before = {
        "status": asset.status,
        "used_by": asset.used_by,
        "workstation_no": asset.workstation_no,
        "current_holder": asset.current_holder,
        "monitor_asset_tags": asset.monitor_asset_tags,
    }
    asset.status = RETURNED_TO_VENDOR_STATUS
    asset.used_by = None
    asset.workstation_no = None
    asset.current_holder = None
    if payload.return_mode == "return_without_monitor":
        # The retained tags now belong to the spare-component pool and must not
        # remain active on the returned desktop.
        asset.monitor_asset_tags = None
    asset.performed_by = user.full_name
    asset.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _record_vendor_return_history(db, asset=asset, record=record, before=history_before, user=user)
    db.commit()
    db.refresh(record)
    db.refresh(asset)
    return vendor_return_payload(db, record)


def vendor_return_payload(db: Session, record: AssetVendorReturn) -> dict[str, Any]:
    spares = list(db.scalars(
        select(SpareMonitor)
        .where(SpareMonitor.source_return_id == record.id)
        .order_by(SpareMonitor.id)
    ).all())
    return {
        "id": record.id,
        "return_code": record.return_code,
        "asset_id": record.asset_id,
        "asset_code": record.asset_code_snapshot,
        "cpu_asset_tag": record.cpu_asset_tag_snapshot,
        "device_type": record.device_type_snapshot,
        "return_mode": record.return_mode,
        "return_date": record.return_date.isoformat(),
        "vendor_name": record.vendor_name,
        "return_reference": record.return_reference,
        "condition": record.condition,
        "reason": record.reason,
        "remarks": record.remarks,
        "reporting_month": record.reporting_month,
        "previous_status": record.previous_status,
        "previous_used_by": record.previous_used_by,
        "previous_department": record.previous_department,
        "previous_workstation_no": record.previous_workstation_no,
        "monitor_tags": record.monitor_tags_snapshot,
        "retained_monitor_tags": record.retained_monitor_tags,
        "performed_by": record.performed_by_name,
        "performed_by_email": record.performed_by_email,
        "performed_by_role": record.performed_by_role,
        "created_at": record.created_at.isoformat(),
        "spare_monitors": [spare_monitor_payload(db, spare) for spare in spares],
    }


def spare_monitor_payload(db: Session, spare: SpareMonitor) -> dict[str, Any]:
    current = db.get(Asset, spare.current_asset_id) if spare.current_asset_id else None
    return {
        "id": spare.id,
        "monitor_tag": spare.monitor_tag,
        "source_return_id": spare.source_return_id,
        "source_asset_id": spare.source_asset_id,
        "source_asset_code": spare.source_asset_code,
        "status": spare.status,
        "current_asset_id": spare.current_asset_id,
        "current_asset_code": current.asset_code if current else None,
        "current_cpu_asset_tag": current.cpu_asset_tag if current else None,
        "location": spare.location,
        "retained_date": spare.retained_date.isoformat(),
        "assigned_at": spare.assigned_at.isoformat() if spare.assigned_at else None,
        "assigned_by_name": spare.assigned_by_name,
        "assigned_by_email": spare.assigned_by_email,
        "assigned_by_role": spare.assigned_by_role,
        "remarks": spare.remarks,
        "created_at": spare.created_at.isoformat(),
        "updated_at": spare.updated_at.isoformat(),
    }


def list_vendor_returns(db: Session) -> list[dict[str, Any]]:
    rows = list(db.scalars(select(AssetVendorReturn).order_by(AssetVendorReturn.created_at.desc())).all())
    return [vendor_return_payload(db, row) for row in rows]


def list_spares(db: Session, status: str | None = None) -> list[dict[str, Any]]:
    query = select(SpareMonitor)
    if status:
        query = query.where(SpareMonitor.status == status.strip().lower())
    rows = list(db.scalars(query.order_by(SpareMonitor.status, SpareMonitor.monitor_tag)).all())
    return [spare_monitor_payload(db, row) for row in rows]


def validate_spare_monitor_component_change(db: Session, payload) -> None:
    """Reject attempts to reuse a retained spare that is no longer available."""
    for item in payload.items:
        if item.component_type.strip().lower() != "monitor":
            continue
        spare = db.scalar(
            select(SpareMonitor).where(SpareMonitor.monitor_tag.ilike(item.new_value.strip())).limit(1)
        )
        if spare is not None and spare.status != "available":
            current = db.get(Asset, spare.current_asset_id) if spare.current_asset_id else None
            owner = current.cpu_asset_tag if current else None
            suffix = f" on {owner}" if owner else ""
            raise HTTPException(status_code=409, detail=f"Retained spare monitor {spare.monitor_tag} is {spare.status}{suffix}")


def apply_spare_monitor_component_change(db: Session, payload, user: User) -> None:
    """Synchronize spare-monitor state after the existing Component Change saves.

    The existing component-change service remains authoritative for Asset,
    WorkRecord and ComponentReplacement creation. This additive synchronization
    only updates retained-spare availability.
    """
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
                raise HTTPException(status_code=409, detail=f"Retained spare monitor {new_spare.monitor_tag} is no longer available")
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
    db.commit()
