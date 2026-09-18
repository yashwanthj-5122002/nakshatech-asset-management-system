from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.completion_models import MasterProjectCompletion
from app.modules.operations.completion_schemas import (
    DepartmentCompletionRequest,
    FinanceClosureUpdate,
    MasterProjectDeliveryRequest,
)
from app.modules.operations.completion_service import (
    TECHNICAL_ROLES,
    complete_department_workstream,
    completion_dashboard_payload,
    create_bd_financial_closure_notification,
    create_bd_project_ready_notification,
    create_department_completion_notifications,
    create_finance_master_completion_notifications,
    deliver_department_completion_emails,
    deliver_finance_master_completion_emails,
    record_master_project_delivery,
    update_finance_closure,
)
from app.modules.operations.models import ProjectWorkstream

router = APIRouter(tags=["Master Project Completion & Finance Handoff"])


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this Project Completion action")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(request: Request, db: Session, auth: CurrentAuth, event_type: str, target_type: str, target_id: int | None, details: dict | None = None) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations_project_completion",
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/project-completion/dashboard")
def project_completion_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd", *sorted(TECHNICAL_ROLES), "finance", "management", "admin")
    try:
        return completion_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        raise _write_error(exc) from exc


@router.post("/project-completion/workstreams/{workstream_id}/complete")
def technical_pm_complete_department(
    workstream_id: int,
    payload: DepartmentCompletionRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    row = db.get(ProjectWorkstream, workstream_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Project workstream not found")
    try:
        row = complete_department_workstream(
            db,
            workstream=row,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "PROJECT_WORKSTREAM_COMPLETED",
            "project_workstream",
            row.id,
            {"project_id": row.project_id, "department_code": row.department_code},
        )
        project_id = row.project_id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    # Department completion is saved first. Phase 7 technical notifications and
    # email are post-commit, so SMTP/notification failures can never undo completion.
    technical_notifications = 0
    try:
        technical_notifications = create_department_completion_notifications(db, workstream_id=workstream_id)
        db.commit()
    except Exception:
        db.rollback()
    try:
        technical_email_sent, technical_email_failed = deliver_department_completion_emails(db, workstream_id=workstream_id)
    except Exception:
        technical_email_sent, technical_email_failed = 0, 0

    # When this was the final technical gate, notify BD afterwards as before.
    bd_ready_notifications = 0
    try:
        bd_ready_notifications = len(create_bd_project_ready_notification(db, project_id=project_id))
        db.commit()
    except Exception:
        db.rollback()
    result = completion_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    result["technical_notifications_created"] = technical_notifications
    result["technical_email_sent"] = technical_email_sent
    result["technical_email_failed"] = technical_email_failed
    result["bd_ready_notifications_created"] = bd_ready_notifications
    return result


@router.post("/bd/project-completion/projects/{project_id}/deliver")
def bd_record_master_project_delivery(
    project_id: int,
    payload: MasterProjectDeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    try:
        completion = record_master_project_delivery(
            db,
            project_id=project_id,
            actor=auth.user,
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "MASTER_PROJECT_FINAL_DELIVERY",
            "master_project_completion",
            completion.id,
            {"project_id": project_id, "finance_status": completion.finance_status},
        )
        completion_id = completion.id
        delivered_at = completion.delivered_at.isoformat()
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    # Persist the business delivery FIRST. Finance notification/email happens only
    # after commit and can never roll back Master Project Final Delivery.
    finance_notifications = 0
    try:
        finance_notifications = len(create_finance_master_completion_notifications(db, completion_id=completion_id))
        db.commit()
    except Exception:
        db.rollback()

    try:
        email_sent, email_failed = deliver_finance_master_completion_emails(db, completion_id=completion_id)
    except Exception:
        email_sent, email_failed = 0, 0

    return {
        "project_id": project_id,
        "completion_id": completion_id,
        "delivered_at": delivered_at,
        "finance_notifications_created": finance_notifications,
        "finance_email_sent": email_sent,
        "finance_email_failed": email_failed,
    }


@router.patch("/finance/project-completion/projects/{project_id}/status")
def finance_update_master_project_closure(
    project_id: int,
    payload: FinanceClosureUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "finance")
    completion = db.scalar(select(MasterProjectCompletion).where(MasterProjectCompletion.project_id == project_id))
    if completion is None:
        raise HTTPException(status_code=404, detail="Master Project final delivery has not been recorded")
    try:
        completion = update_finance_closure(
            db,
            completion=completion,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        _audit(
            request,
            db,
            auth,
            "MASTER_PROJECT_FINANCE_STATUS_UPDATED",
            "master_project_completion",
            completion.id,
            {"project_id": project_id, "finance_status": completion.finance_status},
        )
        completion_id = completion.id
        final_status = completion.finance_status
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    bd_notifications = 0
    if final_status == "financially_closed":
        try:
            bd_notifications = len(create_bd_financial_closure_notification(db, completion_id=completion_id))
            db.commit()
        except Exception:
            db.rollback()

    result = completion_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    result["bd_notifications_created"] = bd_notifications
    return result
