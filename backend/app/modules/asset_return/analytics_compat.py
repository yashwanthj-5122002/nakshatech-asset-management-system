from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import Asset, MonthlyAssetSnapshot, MonthlySnapshotRun, ReplacementRecord
from app.modules.asset_return.service import active_inventory_assets


_installed = False


def install_asset_return_compatibility() -> None:
    """Install small runtime compatibility hooks for the additive return feature.

    Existing analytics import ``assets_for_month`` directly, so changing their
    source module later would not update those already-bound references. Replace
    only those read functions with an active-inventory view while leaving the
    canonical monthly snapshot source untouched for audit/history access.

    Month-end snapshot creation is also switched to active inventory so snapshot
    row count and closing_count remain exactly reconciled after vendor returns.
    """

    global _installed
    if _installed:
        return

    import app.api.router as base_api
    import app.modules.asset_return.router as return_router
    import app.modules.data_quality.service as data_quality_service
    import app.modules.naksha_copilot.service as copilot_service
    import app.services.asset_lifecycle_service as lifecycle_service
    import app.services.monthly_snapshot_service as snapshot_service

    original_assets_for_month = snapshot_service.assets_for_month
    original_get_snapshot_run = snapshot_service.get_snapshot_run
    original_previous_month = snapshot_service.previous_month
    original_serialise_asset = snapshot_service._serialise_asset
    original_vendor_return = return_router.perform_vendor_return

    def active_assets_for_month(db: Session, start):
        assets, source = original_assets_for_month(db, start)
        return active_inventory_assets(list(assets)), source

    def active_finalize_month_snapshot(
        db: Session,
        start,
        finalized_by: str,
        source: str = "manual",
        replace_existing: bool = False,
    ) -> MonthlySnapshotRun:
        start = start.replace(day=1)
        current = snapshot_service.month_start()
        if start > current:
            raise ValueError("A future month cannot be finalized")

        existing = original_get_snapshot_run(db, start)
        if existing and not replace_existing:
            return existing
        if existing and replace_existing:
            db.delete(existing)
            db.flush()

        assets = active_inventory_assets(list(db.scalars(select(Asset).order_by(Asset.id)).all()))
        previous = original_get_snapshot_run(db, original_previous_month(start))
        opening_count = previous.closing_count if previous else len([asset for asset in assets if asset.source_sheet])
        run = MonthlySnapshotRun(
            month_start=start,
            status="finalized",
            source=source,
            opening_count=opening_count,
            closing_count=len(assets),
            finalized_by=finalized_by,
            finalized_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.add(run)
        db.flush()
        for asset in assets:
            db.add(MonthlyAssetSnapshot(
                run_id=run.id,
                asset_code=asset.asset_code,
                payload=original_serialise_asset(asset),
            ))
        db.commit()
        db.refresh(run)
        return run

    def guarded_vendor_return(db: Session, asset_id: int, payload, user):
        asset = db.get(Asset, asset_id)
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        status = str(asset.status or "").strip().lower()
        if status in {"replaced", "retired", "disposed", "missing", "returned_to_vendor"}:
            raise HTTPException(
                status_code=409,
                detail="A finalized, missing, or already vendor-returned asset cannot be returned to a rental vendor",
            )
        active_replacement = db.scalar(
            select(ReplacementRecord.id)
            .where(
                or_(ReplacementRecord.old_asset_id == asset_id, ReplacementRecord.new_asset_id == asset_id),
                or_(
                    ReplacementRecord.approval_status.in_(["pending", "returned"]),
                    ReplacementRecord.final_action.in_(["replacement_pending", "procurement_required"]),
                ),
            )
            .limit(1)
        )
        if active_replacement is not None:
            raise HTTPException(
                status_code=409,
                detail="Resolve the active complete-asset replacement/procurement workflow before vendor return",
            )
        return original_vendor_return(db, asset_id, payload, user)

    # Vendor-returned assets are terminal for every existing custody helper. This
    # also protects the separate Handover & Return endpoint from direct/stale API
    # calls that bypass the new workspace.
    lifecycle_service.TERMINAL_LIFECYCLE_STATUSES.add("returned_to_vendor")

    # The public vendor-return route resolves this module global at request time,
    # so replace only its service binding instead of registering a duplicate route.
    return_router.perform_vendor_return = guarded_vendor_return

    # Read-only analytics must describe the active fleet, not inactive vendor
    # return evidence. Historical months before a return remain unchanged because
    # their snapshots/workbook rows still carry their then-current status.
    data_quality_service.assets_for_month = active_assets_for_month
    copilot_service.assets_for_month = active_assets_for_month

    # Keep future snapshot rows and metadata consistent. api.router imported the
    # function by name, while ensure_previous_month_snapshot resolves the module
    # global at runtime, so update both bindings once at startup.
    snapshot_service.finalize_month_snapshot = active_finalize_month_snapshot
    base_api.finalize_month_snapshot = active_finalize_month_snapshot

    _installed = True
