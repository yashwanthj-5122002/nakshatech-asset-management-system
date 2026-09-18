from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.technical_directory_models import TechnicalDepartmentMember
from app.modules.operations.technical_directory_schemas import (
    TechnicalDirectoryMemberCreate,
    TechnicalDirectoryMemberUpdate,
)
from app.modules.operations.technical_directory_service import (
    TECHNICAL_ROLES,
    add_directory_member,
    deactivate_directory_member,
    directory_dashboard_payload,
    update_directory_member,
)
from app.modules.operations.technical_routing_service import live_routing_enabled

router = APIRouter(tags=["Technical Team Directory & Go-Live Readiness"])


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for Technical Team Directory")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(request: Request, db: Session, auth: CurrentAuth, event_type: str, target_id: int | None, details: dict) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations_technical_team_directory",
        target_type="technical_department_member",
        target_id=str(target_id) if target_id is not None else None,
        details=details,
    )


@router.get("/technical-team-directory/dashboard")
def technical_team_directory_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin", "management", "bd", *sorted(TECHNICAL_ROLES))
    try:
        return directory_dashboard_payload(db, effective_role=_role(auth))
    except Exception as exc:
        raise _write_error(exc) from exc


@router.post("/technical-team-directory/departments/{department_code}/members")
def add_technical_team_member(
    department_code: str,
    payload: TechnicalDirectoryMemberCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin")
    try:
        row = add_directory_member(db, department_code=department_code, actor=auth.user, payload=payload)
        _audit(request, db, auth, "TECHNICAL_DIRECTORY_MEMBER_ADDED", row.id, {
            "department_code": row.department_code,
            "user_id": row.user_id,
            "live_routing_enabled": live_routing_enabled(db),
        })
        db.commit()
        return directory_dashboard_payload(db, effective_role=_role(auth))
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.patch("/technical-team-directory/members/{member_id}")
def update_technical_team_member(
    member_id: int,
    payload: TechnicalDirectoryMemberUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin")
    row = db.get(TechnicalDepartmentMember, member_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Technical directory member not found")
    try:
        row = update_directory_member(db, row=row, actor=auth.user, payload=payload)
        _audit(request, db, auth, "TECHNICAL_DIRECTORY_MEMBER_UPDATED", row.id, {
            "department_code": row.department_code,
            "user_id": row.user_id,
            "live_routing_enabled": live_routing_enabled(db),
        })
        db.commit()
        return directory_dashboard_payload(db, effective_role=_role(auth))
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.delete("/technical-team-directory/members/{member_id}")
def remove_technical_team_member(
    member_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin")
    row = db.get(TechnicalDepartmentMember, member_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Technical directory member not found")
    try:
        row = deactivate_directory_member(db, row=row, actor=auth.user)
        _audit(request, db, auth, "TECHNICAL_DIRECTORY_MEMBER_DEACTIVATED", row.id, {
            "department_code": row.department_code,
            "user_id": row.user_id,
            "live_routing_enabled": live_routing_enabled(db),
        })
        db.commit()
        return directory_dashboard_payload(db, effective_role=_role(auth))
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc
