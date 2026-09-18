from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.technical_routing_schemas import TechnicalRoutingActivateRequest
from app.modules.operations.technical_routing_service import activate_live_routing, routing_status_payload

router = APIRouter(tags=["Phase 7 Real Technical Routing Cutover"])
TECHNICAL_ROLES = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for Phase 7 Technical Routing")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/technical-team-routing/status")
def technical_team_routing_status(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin", "management", "bd", *sorted(TECHNICAL_ROLES))
    return routing_status_payload(db)


@router.post("/technical-team-routing/activate")
def activate_real_technical_routing(
    payload: TechnicalRoutingActivateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "admin")
    try:
        row = activate_live_routing(
            db,
            actor=auth.user,
            confirmation=payload.confirmation,
            note=payload.note,
        )
        record_audit(
            db,
            event_type="TECHNICAL_ROUTING_PRODUCTION_ACTIVATED",
            request=request,
            user=auth.user,
            module="operations_technical_routing",
            target_type="technical_routing_control",
            target_id=str(row.id),
            details={
                "routing_mode": row.routing_mode,
                "live_enabled": bool(row.live_enabled),
                "phase": "V7.0.21",
            },
        )
        db.commit()
        return routing_status_payload(db)
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc
