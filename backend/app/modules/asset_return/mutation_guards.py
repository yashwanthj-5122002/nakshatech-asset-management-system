from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.api.router import (
    archive_asset as base_archive_asset,
    assign_asset as base_assign_asset,
    create_component_replacement as base_create_component_replacement,
    create_work_record as base_create_work_record,
    delete_test_asset as base_delete_test_asset,
    return_asset as base_return_asset,
    update_asset as base_update_asset,
    update_asset_status as base_update_asset_status,
)
from app.core.database import get_db
from app.models.entities import Asset, User
from app.schemas.asset import AssetAssignment, AssetResponse, AssetReturn, AssetStatusUpdate, AssetUpdate
from app.schemas.component_replacement import ComponentReplacementCreate
from app.schemas.work import WorkRecordCreate


router = APIRouter(tags=["Rental Asset Return Guards"])
RETURNED_TO_VENDOR_STATUS = "returned_to_vendor"


def _assert_active_asset(db: Session, asset_id: int) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    if str(asset.status or "").strip().lower() == RETURNED_TO_VENDOR_STATUS:
        raise HTTPException(
            status_code=409,
            detail=(
                "This asset has been returned to the vendor and is locked from operational changes. "
                "Use Rental Returns & Spares for its audit record."
            ),
        )
    return asset


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
def update_active_asset(
    asset_id: int,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_update_asset(asset_id=asset_id, payload=payload, db=db, user=user)


@router.patch("/assets/{asset_id}/status", response_model=AssetResponse)
def update_active_asset_status(
    asset_id: int,
    payload: AssetStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_update_asset_status(asset_id=asset_id, payload=payload, db=db, user=user)


@router.post("/assets/{asset_id}/assign", response_model=AssetResponse)
def assign_active_asset(
    asset_id: int,
    payload: AssetAssignment,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_assign_asset(asset_id=asset_id, payload=payload, db=db, user=user)


@router.post("/assets/{asset_id}/return", response_model=AssetResponse)
def return_active_asset(
    asset_id: int,
    payload: AssetReturn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_return_asset(asset_id=asset_id, payload=payload, db=db, user=user)


@router.patch("/assets/{asset_id}/archive", response_model=AssetResponse)
def archive_active_asset(
    asset_id: int,
    reporting_month: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_archive_asset(asset_id=asset_id, reporting_month=reporting_month, db=db, user=user)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_active_test_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
):
    _assert_active_asset(db, asset_id)
    return base_delete_test_asset(asset_id=asset_id, db=db, user=user)


@router.post("/component-replacements")
def create_component_replacement_on_active_asset(
    payload: ComponentReplacementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    _assert_active_asset(db, payload.asset_id)
    return base_create_component_replacement(payload=payload, db=db, user=user)


@router.post("/work-records")
def create_work_for_active_asset(
    payload: WorkRecordCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it", "drone")),
) -> dict:
    if payload.asset_id is not None:
        _assert_active_asset(db, payload.asset_id)
    return base_create_work_record(payload=payload, db=db, user=user)
