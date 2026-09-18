from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.handover_schemas import (
    ProjectDataHandoverCreate,
    ProjectDataHandoverDecision,
    ProjectDataHandoverSubmit,
)
from app.modules.operations.handover_service import (
    create_project_handover,
    create_receiver_handover_notification,
    create_sender_decision_notification,
    deactivate_project_handover,
    decide_project_handover,
    deliver_receiver_handover_email,
    deliver_sender_decision_email,
    handover_dashboard_payload,
    handover_payload,
    submit_project_handover,
)

from app.modules.operations.technical_routing_service import current_routing_mode, live_routing_enabled

router = APIRouter(tags=["Connected Project Data Handovers"])
TECHNICAL_ROLES = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this Data Handover action")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(
    request: Request,
    db: Session,
    auth: CurrentAuth,
    event_type: str,
    target_id: int | None = None,
    details: dict | None = None,
) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations_project_data_handover",
        target_type="project_data_handover",
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/project-handovers/dashboard")
def project_handover_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd", *sorted(TECHNICAL_ROLES), "management", "admin")
    try:
        return handover_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        raise _write_error(exc) from exc


@router.post("/bd/project-handovers")
def bd_create_project_handover_connection(
    payload: ProjectDataHandoverCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    try:
        row = create_project_handover(db, actor=auth.user, payload=payload)
        _audit(
            request,
            db,
            auth,
            "BD_PROJECT_HANDOVER_CONNECTION_CREATED",
            row.id,
            {
                "project_id": row.project_id,
                "from_workstream_id": row.from_workstream_id,
                "to_workstream_id": row.to_workstream_id,
            },
        )
        db.commit()
        saved = db.get(ProjectDataHandover, row.id)
        return handover_payload(db, saved, actor=auth.user, effective_role=_role(auth)) if saved else {"id": row.id}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.delete("/bd/project-handovers/{handover_id}")
def bd_remove_project_handover_connection(
    handover_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    row = db.get(ProjectDataHandover, handover_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Data handover connection not found")
    try:
        row = deactivate_project_handover(db, actor=auth.user, handover=row)
        _audit(request, db, auth, "BD_PROJECT_HANDOVER_CONNECTION_REMOVED", row.id, {"project_id": row.project_id})
        db.commit()
        return {"id": row.id, "is_active": False}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/project-handovers/{handover_id}/submit")
def technical_sender_submit_handover(
    handover_id: int,
    payload: ProjectDataHandoverSubmit,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    row = db.get(ProjectDataHandover, handover_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Data handover connection not found")
    try:
        attempt = submit_project_handover(
            db,
            handover=row,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "PROJECT_DATA_HANDOVER_SUBMITTED",
            row.id,
            {"attempt_no": attempt.attempt_no, "project_id": row.project_id},
        )
        handover_id_saved = row.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    # Handover business state commits first. Notification/email can fail without
    # rolling back the transfer reference or sender submission history.
    notifications_created = 0
    try:
        notifications_created = create_receiver_handover_notification(db, handover_id=handover_id_saved)
        db.commit()
    except Exception:
        db.rollback()
    try:
        email_sent, email_failed = deliver_receiver_handover_email(db, handover_id=handover_id_saved)
    except Exception:
        email_sent, email_failed = 0, 0
    saved = db.get(ProjectDataHandover, handover_id_saved)
    return {
        "handover": handover_payload(db, saved, actor=auth.user, effective_role=_role(auth)) if saved else None,
        "receiver_notifications_created": notifications_created,
        "technical_email_sent": email_sent,
        "technical_email_failed": email_failed,
        "routing_mode": current_routing_mode(db),
        "demo_email_sent": email_sent if not live_routing_enabled(db) else 0,
        "demo_email_failed": email_failed if not live_routing_enabled(db) else 0,
    }


@router.post("/project-handovers/{handover_id}/decision")
def technical_receiver_decide_handover(
    handover_id: int,
    payload: ProjectDataHandoverDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    row = db.get(ProjectDataHandover, handover_id)
    if row is None or not row.is_active:
        raise HTTPException(status_code=404, detail="Data handover connection not found")
    try:
        row = decide_project_handover(
            db,
            handover=row,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "PROJECT_DATA_HANDOVER_DECIDED",
            row.id,
            {"decision": payload.decision, "project_id": row.project_id},
        )
        handover_id_saved = row.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    notifications_created = 0
    try:
        notifications_created = create_sender_decision_notification(db, handover_id=handover_id_saved)
        db.commit()
    except Exception:
        db.rollback()
    try:
        email_sent, email_failed = deliver_sender_decision_email(db, handover_id=handover_id_saved)
    except Exception:
        email_sent, email_failed = 0, 0
    saved = db.get(ProjectDataHandover, handover_id_saved)
    return {
        "handover": handover_payload(db, saved, actor=auth.user, effective_role=_role(auth)) if saved else None,
        "sender_notifications_created": notifications_created,
        "technical_email_sent": email_sent,
        "technical_email_failed": email_failed,
        "routing_mode": current_routing_mode(db),
        "demo_email_sent": email_sent if not live_routing_enabled(db) else 0,
        "demo_email_failed": email_failed if not live_routing_enabled(db) else 0,
    }
