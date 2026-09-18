from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.hardening_service import (
    HARDENING_ROLES,
    HARDENING_WRITE_DIAGNOSTIC_ROLES,
    audit_snapshot,
    hardening_overview_payload,
    notification_snapshot,
    smtp_auth_probe,
)
from app.modules.operations.service import normalize_role

router = APIRouter(prefix="/hardening", tags=["Phase 9 Production Hardening"])


def _role(auth: CurrentAuth) -> str:
    return normalize_role(auth.effective_role)


def _allow(auth: CurrentAuth) -> str:
    role = _role(auth)
    if role not in HARDENING_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Production hardening dashboard is restricted to Admin, Management and Software Team")
    return role


@router.get("/overview")
def hardening_overview(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow(auth)
    return hardening_overview_payload(db, actor=auth.user, effective_role=role)


@router.get("/audit")
def hardening_audit(
    limit: int = 50,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _allow(auth)
    return audit_snapshot(db, limit=max(1, min(limit, 100)))


@router.get("/notifications")
def hardening_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _allow(auth)
    return notification_snapshot(db, limit=max(1, min(limit, 100)))


@router.post("/smtp-check")
def hardening_smtp_check(
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    role = _allow(auth)
    if role not in HARDENING_WRITE_DIAGNOSTIC_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Admin or Software Team may run the SMTP authentication diagnostic")
    result = smtp_auth_probe()
    try:
        record_audit(
            db,
            event_type="PHASE9_SMTP_AUTH_DIAGNOSTIC",
            request=request,
            user=auth.user,
            module="operations_hardening",
            target_type="smtp_configuration",
            target_id=None,
            details={"ok": bool(result.get("ok")), "host": result.get("host"), "port": result.get("port")},
        )
        db.commit()
    except Exception:
        db.rollback()
    return result
