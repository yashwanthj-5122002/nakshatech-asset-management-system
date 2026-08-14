from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

# Import cumulative runtime so return models are registered and compatibility
# hooks are installed before the isolated test schema is created.
from app.batch4_main import app  # noqa: F401
from app.api import router as base_api
from app.core.database import SessionLocal
from app.models.entities import Asset, MonthlyAssetSnapshot, ReplacementRecord, User
from app.modules.asset_return.mutation_guards import update_active_asset_status
from app.modules.asset_return.router import return_rental_asset_to_vendor
from app.modules.asset_return.schemas import AssetVendorReturnCreate
from app.modules.asset_return.service import perform_vendor_return
from app.modules.batch4.router import _active_management_control_center
from app.modules.data_quality.service import build_data_quality_summary
from app.modules.naksha_copilot.service import build_sanitized_context
from app.schemas.asset import AssetStatusUpdate
from app.services.monthly_snapshot_service import month_start


def _user(db) -> User:
    user = User(
        email="return-guard-it@nakshatech.com",
        full_name="Return Guard IT",
        password_hash="pytest-only-password-hash",
        role="it",
        branch="Head Office",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _asset(db, code: str, cpu: str, monitor: str) -> Asset:
    asset = Asset(
        asset_code=code,
        cpu_asset_tag=cpu,
        monitor_asset_tags=monitor,
        device_type="Computer",
        status="available",
        work_mode="office",
        department="IT",
        location="Head Office",
        asset_date=date.today(),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _return_payload() -> AssetVendorReturnCreate:
    return AssetVendorReturnCreate(
        return_mode="complete_return",
        return_date=date.today(),
        vendor_name="Regression Rental Vendor",
        return_reference="RET-GUARD-001",
        condition="Good / working",
        reason="Rental period completed",
        reporting_month=month_start().strftime("%Y-%m"),
    )


def test_returned_asset_is_locked_and_excluded_from_analytics_and_snapshot_counts():
    with SessionLocal() as db:
        it_user = _user(db)
        active = _asset(db, "NT-PC-GUARD-ACTIVE", "GUARD-ACTIVE", "MON-ACTIVE")
        returned = _asset(db, "NT-PC-GUARD-RETURN", "GUARD-RETURN", "MON-RETURN")
        perform_vendor_return(db, returned.id, _return_payload(), it_user)

        with pytest.raises(HTTPException) as exc:
            update_active_asset_status(
                asset_id=returned.id,
                payload=AssetStatusUpdate(status="available", reporting_month=month_start().strftime("%Y-%m")),
                db=db,
                user=it_user,
            )
        assert exc.value.status_code == 409
        db.refresh(returned)
        assert returned.status == "returned_to_vendor"

        month_key = month_start().strftime("%Y-%m")
        quality = build_data_quality_summary(db, month_key)
        assert quality.metrics["all_asset_records"] == 1
        assert quality.metrics["primary_it_assets"] == 1

        context, _label, _sources = build_sanitized_context(
            db,
            period_type="month",
            month=month_key,
            months=None,
            year=None,
        )
        assert context["asset_statistics"]["totals"]["primary_it_assets"] == 1
        assert context["asset_statistics"]["totals"]["all_asset_rows"] == 1

        management = _active_management_control_center(db, month_key)
        assert management["executive"]["primary_assets"] == 1
        assert management["executive"]["available_assets"] == 1

        run = base_api.finalize_month_snapshot(
            db,
            month_start(),
            "Pytest Rental Return",
            source="manual",
            replace_existing=True,
        )
        assert run.closing_count == 1
        snapshot_rows = db.scalar(
            select(func.count(MonthlyAssetSnapshot.id)).where(MonthlyAssetSnapshot.run_id == run.id)
        ) or 0
        assert snapshot_rows == 1
        assert db.get(Asset, active.id) is not None
        assert db.get(Asset, returned.id) is not None


def test_vendor_return_route_blocks_open_procurement_replacement():
    with SessionLocal() as db:
        it_user = _user(db)
        asset = _asset(db, "NT-PC-GUARD-RPL", "GUARD-RPL", "MON-RPL")
        replacement = ReplacementRecord(
            replacement_code="RPL-GUARD-001",
            old_asset_id=asset.id,
            new_asset_id=None,
            reason="Replacement requires procurement",
            damage_category="technical_failure",
            inspection_finding="No compatible spare",
            approval_status="not_required",
            final_action="procurement_required",
            requested_by_user_id=it_user.id,
            requested_by=it_user.full_name,
            requested_by_email=it_user.email,
            requested_by_role=it_user.role,
            reporting_month=month_start().strftime("%Y-%m"),
        )
        db.add(replacement)
        db.commit()

        with pytest.raises(HTTPException) as exc:
            return_rental_asset_to_vendor(
                asset_id=asset.id,
                payload=_return_payload(),
                db=db,
                user=it_user,
            )
        assert exc.value.status_code == 409
        assert "replacement/procurement" in str(exc.value.detail)
        db.refresh(asset)
        assert asset.status == "available"
