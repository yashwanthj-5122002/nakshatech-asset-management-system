from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import TECHNICAL_PM_ROLES
from app.modules.commercial.fx_service import FxUnavailableError
from app.modules.commercial.service import commercial_summary
from app.modules.employee_portal.service import record_audit
from app.modules.finance.schemas import FinanceClientCreateRequest
from app.modules.finance.service import client_payload
from app.modules.operations.schemas import (
    WorkflowDailyActivity,
    WorkflowDeliveryRequest,
    WorkflowFinanceClosure,
    WorkflowFinanceReview,
    WorkflowOperationalCompletion,
    WorkflowPMAssignment,
    WorkflowProjectCreate,
    WorkflowReviewRequest,
    WorkflowReworkAllocation,
    WorkflowReworkTeamConfirm,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)
from app.modules.operations.workflow_service import (
    ADMIN_ROLE,
    BD_ROLE,
    EMPLOYEE_ROLE,
    FINANCE_ROLE,
    MANAGEMENT_ROLE,
    ORTHO_ROLE,
    allocate_rework_work,
    allocate_work,
    assign_project_manager,
    bd_dashboard,
    complete_production,
    configure_team,
    confirm_rework_team,
    create_bd_client,
    create_bd_project,
    update_bd_project,
    email_bd_finance_review,
    email_finance_submission,
    email_finance_closure,
    email_operational_completion,
    email_project_manager_assignment,
    email_production_completion,
    email_review_transition,
    email_delivery_completion,
    email_team_assignments,
    email_work_allocation,
    finance_close_project,
    finance_dashboard,
    finance_review_project,
    mark_delivered,
    operational_complete,
    ortho_dashboard,
    record_daily_activity,
    review_work,
    submit_project_to_finance,
)
from app.modules.operations.workflow_reporting import build_project_operations_workbook

router = APIRouter(prefix="/workflow", tags=["Authoritative Project Workflow"])


def _role(auth: CurrentAuth) -> str:
    return (auth.effective_role or "").strip().lower()


def _roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this workflow action")


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, FxUnavailableError):
        # Same structured shape as the commercial router so the UI can offer Retry / Enter rate manually.
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": str(exc), "attempts": exc.attempts},
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(request: Request, db: Session, auth: CurrentAuth, event: str, target: str, target_id: int | None = None, details: dict | None = None) -> None:
    record_audit(
        db,
        event_type=event,
        request=request,
        user=auth.user,
        module="operations",
        target_type=target,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/bd/dashboard")
def workflow_bd_dashboard(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _roles(auth, BD_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return bd_dashboard(db, actor=auth.user, role=_role(auth))

@router.get("/bd/project-register")
def workflow_bd_project_register(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return bd_dashboard(db, actor=auth.user, role=_role(auth))


@router.get("/bd/client-register")
def workflow_bd_client_register(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return bd_dashboard(db, actor=auth.user, role=_role(auth))


@router.post("/bd/clients", status_code=status.HTTP_201_CREATED)
def workflow_create_client(
    payload: FinanceClientCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE)
    try:
        client = create_bd_client(db, actor=auth.user, payload=payload)
        _audit(request, db, auth, "WORKFLOW_BD_CLIENT_CREATED", "finance_client", client.id, {"client_code": client.client_code})
        db.commit()
        db.refresh(client)
        return client_payload(client)
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/bd/projects", status_code=status.HTTP_201_CREATED)
def workflow_create_project(
    payload: WorkflowProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE)
    try:
        project, workflow = create_bd_project(db, actor=auth.user, payload=payload)
        _audit(request, db, auth, "WORKFLOW_BD_PROJECT_CREATED", "finance_project", project.id, {"project_code": project.project_code, "workflow_status": workflow.status, "performing_department_code": workflow.performing_department_code, "commercial_revision1": payload.commercial is not None})
        db.commit()
        return {"project_id": project.id, "project_code": project.project_code, "workflow_status": workflow.status, "commercial": commercial_summary(db, project_id=project.id)}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.put("/bd/projects/{project_id}")
def workflow_update_project(
    project_id: int,
    payload: WorkflowProjectCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE)
    try:
        project, workflow = update_bd_project(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_BD_PROJECT_CORRECTED", "finance_project", project.id, {"project_code": project.project_code, "workflow_status": workflow.status, "performing_department_code": workflow.performing_department_code, "commercial_revision1": payload.commercial is not None})
        db.commit()
        return {"project_id": project.id, "project_code": project.project_code, "workflow_status": workflow.status, "commercial": commercial_summary(db, project_id=project.id)}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/bd/projects/{project_id}/submit-finance")
def workflow_submit_finance(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE)
    try:
        workflow = submit_project_to_finance(db, actor=auth.user, project_id=project_id)
        _audit(request, db, auth, "WORKFLOW_SUBMITTED_TO_FINANCE", "finance_project", project_id, {"workflow_status": workflow.status})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_finance_submission(db, project_id=project_id)
    return {"project_id": project_id, "workflow_status": workflow.status}


@router.post("/bd/projects/{project_id}/assign-pm")
def workflow_assign_pm(
    project_id: int,
    payload: WorkflowPMAssignment,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, BD_ROLE)
    try:
        workflow, pm = assign_project_manager(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_BD_ASSIGNED_PM", "finance_project", project_id, {"project_manager_id": pm.id, "workflow_status": workflow.status})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_project_manager_assignment(db, project_id=project_id, pm_id=pm.id)
    return {"project_id": project_id, "project_manager_id": pm.id, "workflow_status": workflow.status}


@router.get("/finance/dashboard")
def workflow_finance_dashboard(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _roles(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return finance_dashboard(db)


@router.get("/finance/reports/export.xlsx")
def workflow_finance_report_export(
    request: Request,
    report_type: str,
    period: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, FINANCE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    try:
        data, filename = build_project_operations_workbook(
            db, report_type=report_type, period=period, start_date=start_date, end_date=end_date
        )
    except ValueError as exc:
        raise _error(exc) from exc
    _audit(request, db, auth, "WORKFLOW_PROJECT_OPERATIONS_EXCEL_EXPORTED", "project_operations_report", details={
        "report_type": report_type,
        "period": period,
        "start_date": start_date.isoformat() if start_date else None,
        "end_date": end_date.isoformat() if end_date else None,
    })
    db.commit()
    return StreamingResponse(
        BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/finance/projects/{project_id}/review")
def workflow_finance_review(
    project_id: int,
    payload: WorkflowFinanceReview,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, FINANCE_ROLE)
    try:
        workflow = finance_review_project(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_FINANCE_REVIEW", "finance_project", project_id, {"decision": payload.decision, "workflow_status": workflow.status, "feedback": payload.feedback})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_bd_finance_review(db, project_id=project_id, decision=payload.decision)
    return {"project_id": project_id, "workflow_status": workflow.status}


@router.post("/finance/projects/{project_id}/close")
def workflow_finance_close(
    project_id: int,
    payload: WorkflowFinanceClosure,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, FINANCE_ROLE)
    try:
        workflow = finance_close_project(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_FINANCE_CLOSED_PROJECT", "finance_project", project_id, {"workflow_status": workflow.status, "remarks": payload.remarks})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_finance_closure(db, project_id=project_id)
    return {"project_id": project_id, "workflow_status": workflow.status, "finance_closed_at": workflow.finance_closed_at.isoformat() if workflow.finance_closed_at else None}


@router.get("/ortho/dashboard")
def workflow_ortho_dashboard(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return ortho_dashboard(db, actor=auth.user, role=_role(auth))


@router.post("/ortho/projects/{project_id}/team")
def workflow_team_setup(
    project_id: int,
    payload: WorkflowTeamSetup,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES)
    try:
        workflow, roles_by_user = configure_team(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_PM_TEAM_ASSIGNED", "finance_project", project_id, {"team_leader_user_id": payload.team_leader_user_id, "production_user_ids": payload.production_user_ids, "qc_user_ids": payload.qc_user_ids, "qa_user_ids": payload.qa_user_ids, "workflow_status": workflow.status})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_team_assignments(db, project_id=project_id, roles_by_user=roles_by_user)
    return {"project_id": project_id, "workflow_status": workflow.status, "roles_by_user": roles_by_user}


@router.post("/ortho/rework-cycles/{cycle_id}/team")
def workflow_rework_team(
    cycle_id: int,
    payload: WorkflowReworkTeamConfirm,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES)
    try:
        cycle, roles_by_user = confirm_rework_team(db, actor=auth.user, cycle_id=cycle_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_PM_REWORK_TEAM_CONFIRMED", "finance_project", cycle.project_id, {"rework_cycle_id": cycle.id, "cycle_number": cycle.cycle_number, "mode": payload.mode, "team_leader_user_id": cycle.team_leader_user_id, "workflow_status": cycle.status})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"rework_cycle_id": cycle_id, "status": cycle.status, "project_id": cycle.project_id, "roles_by_user": roles_by_user}


@router.post("/ortho/rework-cycles/{cycle_id}/work-packages", status_code=status.HTTP_201_CREATED)
def workflow_allocate_rework(
    cycle_id: int,
    payload: WorkflowReworkAllocation,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        package = allocate_rework_work(db, actor=auth.user, cycle_id=cycle_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_TL_REWORK_WORK_ALLOCATED", "finance_project", package.project_id, {"rework_cycle_id": cycle_id, "package_code": package.package_code, "rework_of_package_id": package.rework_of_package_id})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"id": package.id, "package_code": package.package_code, "rework_cycle_id": package.rework_cycle_id, "rework_of_package_id": package.rework_of_package_id}


@router.post("/ortho/projects/{project_id}/work-packages", status_code=status.HTTP_201_CREATED)
def workflow_allocate_work(
    project_id: int,
    payload: WorkflowWorkAllocation,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        package = allocate_work(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_TEAM_LEAD_ALLOCATED_WORK", "ortho_work_package", package.id, {"project_id": project_id, "package_code": package.package_code})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_work_allocation(db, work_package_id=package.id)
    return {"id": package.id, "project_id": project_id, "package_code": package.package_code}


@router.post("/ortho/work-packages/{work_package_id}/daily-activity", status_code=status.HTTP_201_CREATED)
def workflow_daily_activity(
    work_package_id: int,
    payload: WorkflowDailyActivity,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        row = record_daily_activity(db, actor=auth.user, work_package_id=work_package_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_DAILY_ACTIVITY", "ortho_work_package", work_package_id, {"daily_activity_id": row.id, "quantity_completed": str(row.achieved_area or 0), "files_completed": row.files_completed})
        db.commit()
        return {"id": row.id, "work_package_id": work_package_id, "progress_percent": float(row.progress_percent or 0)}
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/production-complete")
def workflow_production_complete(
    work_package_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        package = complete_production(db, actor=auth.user, work_package_id=work_package_id)
        _audit(request, db, auth, "WORKFLOW_PRODUCTION_COMPLETED", "ortho_work_package", work_package_id, {"current_stage": package.current_stage})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_production_completion(db, work_package_id=work_package_id)
    return {"id": package.id, "current_stage": package.current_stage, "production_state": package.production_state, "qc_state": package.qc_state}


@router.post("/ortho/work-packages/{work_package_id}/qc")
def workflow_qc_review(
    work_package_id: int,
    payload: WorkflowReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        package = review_work(db, actor=auth.user, work_package_id=work_package_id, kind="qc", payload=payload)
        _audit(request, db, auth, f"WORKFLOW_QC_{payload.decision.upper()}", "ortho_work_package", work_package_id, {"comments": payload.comments})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_review_transition(db, work_package_id=work_package_id, kind="qc", decision=payload.decision)
    return {"id": package.id, "current_stage": package.current_stage, "qc_state": package.qc_state, "qa_state": package.qa_state}


@router.post("/ortho/work-packages/{work_package_id}/qa")
def workflow_qa_review(
    work_package_id: int,
    payload: WorkflowReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, EMPLOYEE_ROLE)
    try:
        package = review_work(db, actor=auth.user, work_package_id=work_package_id, kind="qa", payload=payload)
        _audit(request, db, auth, f"WORKFLOW_QA_{payload.decision.upper()}", "ortho_work_package", work_package_id, {"comments": payload.comments})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_review_transition(db, work_package_id=work_package_id, kind="qa", decision=payload.decision)
    return {"id": package.id, "current_stage": package.current_stage, "qa_state": package.qa_state}


@router.post("/ortho/work-packages/{work_package_id}/deliver")
def workflow_deliver(
    work_package_id: int,
    payload: WorkflowDeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    try:
        package = mark_delivered(db, actor=auth.user, work_package_id=work_package_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_DELIVERED", "ortho_work_package", work_package_id, {"remarks": payload.remarks})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_delivery_completion(db, work_package_id=work_package_id)
    return {"id": package.id, "current_stage": package.current_stage, "delivered_at": package.delivered_at.isoformat() if package.delivered_at else None}


@router.post("/ortho/projects/{project_id}/complete")
def workflow_operational_complete(
    project_id: int,
    payload: WorkflowOperationalCompletion,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES)
    try:
        workflow = operational_complete(db, actor=auth.user, project_id=project_id, payload=payload)
        _audit(request, db, auth, "WORKFLOW_OPERATIONAL_COMPLETION", "finance_project", project_id, {"completion_date": payload.completion_date.isoformat(), "delivery_reference": payload.final_delivery_reference, "workflow_status": workflow.status})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    email_operational_completion(db, project_id=project_id)
    return {"project_id": project_id, "workflow_status": workflow.status, "completion_date": workflow.completion_date.isoformat() if workflow.completion_date else None}
