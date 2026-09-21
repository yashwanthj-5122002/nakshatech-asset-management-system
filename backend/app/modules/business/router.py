from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.business.schemas import (
    BusinessHistoryEntry,
    BusinessOverview,
    BusinessRecordRow,
    BusinessRecordUpsertRequest,
    BusinessVerifyRequest,
)
from app.modules.business.service import (
    business_overview,
    record_history,
    record_row,
    set_month_verified,
    upsert_business_record,
)
from app.modules.employee_portal.service import record_audit

router = APIRouter(prefix="/business", tags=["Business Tracking"])


def _role(auth: CurrentAuth) -> str:
    return auth.effective_role.strip().lower()


@router.get("/overview", response_model=BusinessOverview)
def get_overview(
    month: str | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> BusinessOverview:
    return business_overview(db, actor=auth.user, role=_role(auth), month=month)


@router.post("/records", response_model=BusinessRecordRow)
def save_record(
    payload: BusinessRecordUpsertRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> BusinessRecordRow:
    record = upsert_business_record(db, actor=auth.user, role=_role(auth), payload=payload)
    record_audit(
        db,
        event_type="BUSINESS_RECORD_SAVED",
        request=request,
        user=auth.user,
        module="business",
        target_type="business_record",
        target_id=record.id,
        details={
            "project_id": record.project_id,
            "reporting_month": record.reporting_month,
            "amount_total": float(record.amount_total),
            "amount_released": float(record.amount_released),
            "amount_pending": float(record.amount_pending),
            "department_code": record.department_code,
        },
    )
    db.commit()
    return record_row(db, record)


@router.post("/verify", response_model=dict)
def verify_month(
    payload: BusinessVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> dict:
    updated = set_month_verified(
        db,
        actor=auth.user,
        role=_role(auth),
        month=payload.reporting_month,
        verified=payload.verified,
    )
    record_audit(
        db,
        event_type="BUSINESS_MONTH_VERIFIED" if payload.verified else "BUSINESS_MONTH_UNVERIFIED",
        request=request,
        user=auth.user,
        module="business",
        target_type="business_month",
        target_id=payload.reporting_month,
        details={"reporting_month": payload.reporting_month, "records_updated": updated},
    )
    db.commit()
    return {"reporting_month": payload.reporting_month, "records_updated": updated}


@router.get("/records/{record_id}/history", response_model=list[BusinessHistoryEntry])
def get_history(
    record_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
) -> list[BusinessHistoryEntry]:
    return record_history(db, record_id=record_id)
