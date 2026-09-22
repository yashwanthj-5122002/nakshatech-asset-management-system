from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User
from app.uat_2026 import (
    TAG,
    cleanup_year_2026,
    existing_counts,
    seed_year_2026,
    validate_year_2026,
)

router = APIRouter(prefix="/uat/2026", tags=["2026 UAT Controls"])


def _assert_uat_controls_enabled() -> None:
    if settings.is_production:
        raise HTTPException(status_code=404, detail="UAT controls are not available in production")
    if not settings.enable_uat_2026_controls:
        raise HTTPException(status_code=404, detail="2026 UAT controls are disabled")


@router.get("/status")
def uat_2026_status(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin")),
) -> dict:
    counts = existing_counts(db)
    enabled = bool(settings.enable_uat_2026_controls and not settings.is_production)
    return {
        "enabled": enabled,
        "tag": TAG,
        "loaded": bool(counts["clients"] or counts["projects"]),
        "counts": counts,
        "validation": validate_year_2026(db) if counts["projects"] else None,
    }


@router.post("/load")
def load_uat_2026_data(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin")),
) -> dict:
    _assert_uat_controls_enabled()
    counts = existing_counts(db)
    if counts["clients"] or counts["projects"]:
        raise HTTPException(
            status_code=409,
            detail=(
                f"{TAG} already exists (clients={counts['clients']}, projects={counts['projects']}). "
                "Remove the existing UAT dataset before loading it again."
            ),
        )
    try:
        summary = seed_year_2026(db)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "message": "2026 testing data loaded successfully",
        "tag": TAG,
        "seeded": {
            "clients": summary.clients,
            "projects": summary.projects,
            "commercial_revisions": summary.commercial_revisions,
            "work_packages": summary.work_packages,
            "invoices": summary.invoices,
            "payments": summary.payments,
            "closed_invoices": summary.closed_invoices,
            "realized_revenue_inr": float(summary.revenue_inr),
            "expenses": summary.expenses,
            "vendor_invoices": summary.vendor_invoices,
            "expense_claims": summary.expense_claims,
            "feedback_requests": summary.feedback_requests,
            "rework_cycles": summary.rework_cycles,
            "change_requests": summary.change_requests,
            "travel_km_claims": summary.travel_km_claims,
            "assets": summary.assets,
            "work_records": summary.work_records,
            "drones": summary.drones,
        },
        "validation": validate_year_2026(db),
    }


@router.post("/remove")
def remove_uat_2026_data(
    confirmation: str,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("admin")),
) -> dict:
    _assert_uat_controls_enabled()
    if confirmation != TAG:
        raise HTTPException(status_code=422, detail=f"Confirmation must exactly equal {TAG}")
    before = existing_counts(db)
    try:
        deleted = cleanup_year_2026(db)
    except Exception:
        db.rollback()
        raise
    after = validate_year_2026(db)
    if after["projects"] != 0 or after["clients"] != 0:
        raise HTTPException(status_code=500, detail="UAT cleanup validation failed; tagged records still remain")
    return {
        "message": "2026 testing data removed successfully",
        "tag": TAG,
        "before": before,
        "deleted": deleted,
        "after": after,
    }
