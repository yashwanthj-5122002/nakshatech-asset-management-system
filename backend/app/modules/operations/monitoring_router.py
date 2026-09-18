from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.models import ProjectWorkstream
from app.modules.operations.monitoring_schemas import ProjectHandoverScheduleUpdate, ProjectWorkstreamProgressUpdate
from app.modules.operations.monitoring_service import (
    TECHNICAL_ROLES,
    monitoring_dashboard_payload,
    update_handover_schedule,
    update_workstream_progress,
)

router = APIRouter(tags=["Master Project Progress Monitoring"])


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this Project Monitoring action")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(
    request: Request,
    db: Session,
    auth: CurrentAuth,
    event_type: str,
    target_type: str,
    target_id: int | None,
    details: dict | None = None,
) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations_project_monitoring",
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/project-monitoring/dashboard")
def project_monitoring_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd", *sorted(TECHNICAL_ROLES), "management", "admin")
    try:
        return monitoring_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        raise _write_error(exc) from exc


@router.patch("/project-monitoring/workstreams/{workstream_id}/progress")
def technical_pm_update_project_progress(
    workstream_id: int,
    payload: ProjectWorkstreamProgressUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    workstream = db.get(ProjectWorkstream, workstream_id)
    if workstream is None:
        raise HTTPException(status_code=404, detail="Project workstream not found")
    try:
        row = update_workstream_progress(
            db,
            workstream=workstream,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "PROJECT_WORKSTREAM_PROGRESS_REPORTED",
            "project_workstream",
            workstream.id,
            {"project_id": workstream.project_id, "progress_percent": row.progress_percent},
        )
        db.commit()
        return monitoring_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.put("/bd/project-monitoring/handovers/{handover_id}/schedule")
def bd_update_project_handover_schedule(
    handover_id: int,
    payload: ProjectHandoverScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    handover = db.get(ProjectDataHandover, handover_id)
    if handover is None or not handover.is_active:
        raise HTTPException(status_code=404, detail="Data handover connection not found")
    try:
        row = update_handover_schedule(db, handover=handover, actor=auth.user, payload=payload)
        _audit(
            request,
            db,
            auth,
            "BD_PROJECT_HANDOVER_SCHEDULE_UPDATED",
            "project_data_handover",
            handover.id,
            {
                "project_id": handover.project_id,
                "due_at": row.due_at.isoformat() if row.due_at else None,
            },
        )
        db.commit()
        return monitoring_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc
