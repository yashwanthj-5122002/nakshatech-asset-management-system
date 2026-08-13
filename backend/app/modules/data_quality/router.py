from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import User
from app.modules.data_quality.schemas import DataQualitySummaryResponse
from app.modules.data_quality.service import build_data_quality_summary
from app.services.monthly_snapshot_service import month_start

router = APIRouter(prefix="/data-quality", tags=["Data Quality Centre"])


@router.get("/summary", response_model=DataQualitySummaryResponse)
def data_quality_summary(
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("it", "management", "software_team")),
) -> DataQualitySummaryResponse:
    """Return read-only findings. This endpoint never creates, updates or deletes records."""
    try:
        return build_data_quality_summary(db, month or month_start().strftime("%Y-%m"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
