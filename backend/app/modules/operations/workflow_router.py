from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException,Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import TECHNICAL_PM_ROLES
from app.core.department_access import ensure_project_department_access
from app.modules.commercial.fx_service import FxUnavailableError
from app.modules.commercial.service import commercial_summary
from app.modules.employee_portal.service import record_audit
from app.modules.finance.schemas import FinanceClientCreateRequest
from app.modules.finance.service import client_payload
from app.modules.operations.lifecycle_models import ProjectReworkCycle
from app.modules.operations.models import OrthoWorkPackage
from app.modules.operations.schemas import (
    WorkflowDailyActivity,
    WorkflowDeliveryRequest,
    WorkflowFileAllocation,
    WorkflowFinanceClosure,
    WorkflowFinanceReview,
    WorkflowItemActivityStart,
    WorkflowItemActivityStop,
    WorkflowItemDelivery,
    WorkflowItemsAssign,
    WorkflowItemsCreate,
    WorkflowItemsGenerate,
    WorkflowItemUpdate,
    WorkflowOperationalCompletion,
    WorkflowPMAssignment,
    WorkflowPackageGeneralUpdate,
    WorkflowPackageTimelineUpdate,
    WorkflowProjectCreate,
    WorkflowReviewRequest,
    WorkflowReworkAllocation,
    WorkflowReworkTeamConfirm,
    WorkflowStageUpdate,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)
from app.modules.operations import production_allocation, production_items
from app.modules.operations.models import WorkPackageItem
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
from app.modules.operations.production_service import (
    package_stage_history,
    tracking_summary,
    update_package_general,
    update_trackable_stage,
)
from app.modules.operations.production_reporting import build_production_workbook
from fastapi.responses import Response

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


def _ensure_project_department(db: Session, auth: CurrentAuth, project_id: int) -> None:
    """Department isolation for normal employees on project-scoped workflow actions."""
    ensure_project_department_access(db, auth.user, _role(auth), project_id)


def _ensure_package_project(db: Session, auth: CurrentAuth, work_package_id: int) -> int:
    package = db.get(OrthoWorkPackage, work_package_id)
    if package is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work package not found")
    _ensure_project_department(db, auth, package.project_id)
    return package.project_id


def _ensure_cycle_project(db: Session, auth: CurrentAuth, cycle_id: int) -> int:
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rework cycle not found")
    _ensure_project_department(db, auth, cycle.project_id)
    return cycle.project_id


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
    _ensure_cycle_project(db, auth, cycle_id)
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
    _ensure_project_department(db, auth, project_id)
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
    _ensure_package_project(db, auth, work_package_id)
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
    _ensure_package_project(db, auth, work_package_id)
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
    _ensure_package_project(db, auth, work_package_id)
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
    _ensure_package_project(db, auth, work_package_id)
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
    _ensure_package_project(db, auth, work_package_id)
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


# ===========================================================================================
# V8.1 shared production tracking (ADDITIVE). None of the endpoints above are modified;
# these expose the optional additional stages (Import / DXF / Inspection / Upload), the
# general package context, the merged audit history, and server-side tracking summaries
# / exports for Team Lead, PM and read-only Management dashboards.
# ===========================================================================================

@router.post("/ortho/work-packages/{work_package_id}/stage")
def workflow_stage_update(
    work_package_id: int,
    payload: WorkflowStageUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        package = update_trackable_stage(
            db,
            actor=auth.user,
            work_package_id=work_package_id,
            stage=payload.stage,
            status_value=payload.status,
            remarks=payload.remarks,
            dxf_user_id=payload.dxf_user_id,
        )
        _audit(request, db, auth, f"WORKFLOW_STAGE_{payload.stage.upper()}_UPDATED", "ortho_work_package", work_package_id, {"stage": payload.stage, "status": payload.status, "remarks": payload.remarks})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    from app.modules.operations.production_stages import STAGE_STATUS_ATTR as _STATUS_ATTR
    return {
        "id": package.id,
        "stage": payload.stage,
        "status": getattr(package, _STATUS_ATTR[payload.stage], None),
        "current_stage": package.current_stage,
    }


@router.patch("/ortho/work-packages/{work_package_id}/general")
def workflow_package_general_update(
    work_package_id: int,
    payload: WorkflowPackageGeneralUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        package = update_package_general(
            db,
            actor=auth.user,
            work_package_id=work_package_id,
            lot_batch=payload.lot_batch,
            supply_date=payload.supply_date,
            remarks=payload.remarks,
        )
        _audit(request, db, auth, "WORKFLOW_PACKAGE_GENERAL_UPDATED", "ortho_work_package", work_package_id, {
            "lot_batch": package.lot_batch, "supply_date": package.supply_date.isoformat() if package.supply_date else None,
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {
        "id": package.id,
        "lot_batch": package.lot_batch,
        "supply_date": package.supply_date.isoformat() if package.supply_date else None,
        "remarks": package.remarks,
    }


@router.get("/ortho/work-packages/{work_package_id}/history")
def workflow_package_history(
    work_package_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        rows = package_stage_history(db, actor=auth.user, role=_role(auth), work_package_id=work_package_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"work_package_id": work_package_id, "events": rows}


@router.get("/production-tracking")
def workflow_production_tracking(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    return tracking_summary(db, actor=auth.user, role=_role(auth), project_id=project_id)


@router.get("/production-tracking/export.xlsx")
def workflow_production_tracking_export(
    report: str = Query(default="production_detail"),
    project_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE, ADMIN_ROLE, MANAGEMENT_ROLE)
    try:
        content, filename = build_production_workbook(
            db, report_type=report, actor=auth.user, role=_role(auth), project_id=project_id, search=search,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ===========================================================================================
# V8.2 optional FILE / TILE / ITEM tracking (ADDITIVE). Area/work-package lifecycle above is
# untouched; these endpoints add per-file management, real Start/Stop timings, delay capture
# and delivery timestamps on top of the shared work-package record.
# ===========================================================================================

_WORKFLOW_ROLES = (ADMIN_ROLE, EMPLOYEE_ROLE, MANAGEMENT_ROLE)


def _ensure_item_scope(db: Session, auth: CurrentAuth, work_package_item_id: int) -> WorkPackageItem:
    item = db.get(WorkPackageItem, work_package_item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    _ensure_package_project(db, auth, item.work_package_id)
    return item


@router.get("/ortho/work-packages/{work_package_id}/items")
def workflow_list_items(
    work_package_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, *_WORKFLOW_ROLES)
    _ensure_package_project(db, auth, work_package_id)
    try:
        return production_items.item_list(db, actor=auth.user, role=_role(auth), work_package_id=work_package_id)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/ortho/work-packages/{work_package_id}/items", status_code=status.HTTP_201_CREATED)
def workflow_create_items(
    work_package_id: int,
    payload: WorkflowItemsCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        created = production_items.add_items(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id,
            entries=[entry.model_dump() for entry in payload.items],
        )
        _audit(request, db, auth, "WORKFLOW_ITEMS_CREATED", "ortho_work_package", work_package_id, {"count": len(created)})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"created": len(created), "item_ids": [item.id for item in created]}


@router.post("/ortho/work-packages/{work_package_id}/items/generate", status_code=status.HTTP_201_CREATED)
def workflow_generate_items(
    work_package_id: int,
    payload: WorkflowItemsGenerate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        created = production_items.generate_sequence(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id,
            prefix=payload.prefix, start=payload.start, count=payload.count,
            padding=payload.padding, extension=payload.extension,
        )
        _audit(request, db, auth, "WORKFLOW_ITEMS_GENERATED", "ortho_work_package", work_package_id,
               {"count": len(created), "prefix": payload.prefix, "start": payload.start})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"created": len(created), "first": created[0].item_number, "last": created[-1].item_number}


@router.post("/ortho/work-packages/{work_package_id}/items/import", status_code=status.HTTP_201_CREATED)
async def workflow_import_items(
    work_package_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        content = await file.read()
        created = production_items.import_items(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id,
            filename=file.filename or "files.csv", content=content,
        )
        _audit(request, db, auth, "WORKFLOW_ITEMS_IMPORTED", "ortho_work_package", work_package_id,
               {"count": len(created), "filename": file.filename})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"created": len(created)}


@router.post("/ortho/work-packages/{work_package_id}/items/assign")
def workflow_assign_items(
    work_package_id: int,
    payload: WorkflowItemsAssign,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        items = production_items.assign_items(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id,
            item_ids=payload.item_ids,
            production_user_id=payload.production_user_id,
            qc_user_id=payload.qc_user_id,
            qa_user_id=payload.qa_user_id,
        )
        _audit(request, db, auth, "WORKFLOW_ITEMS_ASSIGNED", "ortho_work_package", work_package_id,
               {"count": len(items)})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"updated": len(items)}


@router.patch("/ortho/items/{work_package_item_id}")
def workflow_update_item(
    work_package_item_id: int,
    payload: WorkflowItemUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    item = _ensure_item_scope(db, auth, work_package_item_id)
    try:
        updated = production_items.update_item(
            db, actor=auth.user, role=_role(auth), work_package_item_id=work_package_item_id,
            changes=payload.model_dump(), provided=set(payload.model_fields_set),
        )
        _audit(request, db, auth, "WORKFLOW_ITEM_UPDATED", "ortho_work_package", item.work_package_id,
               {"item_id": updated.id, "item_number": updated.item_number, "is_active": updated.is_active})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"id": updated.id, "item_number": updated.item_number, "is_active": updated.is_active,
            "production_user_id": updated.production_user_id, "qc_user_id": updated.qc_user_id,
            "qa_user_id": updated.qa_user_id}


@router.post("/ortho/items/{work_package_item_id}/activity/start", status_code=status.HTTP_201_CREATED)
def workflow_start_item_activity(
    work_package_item_id: int,
    payload: WorkflowItemActivityStart,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    item = _ensure_item_scope(db, auth, work_package_item_id)
    try:
        activity = production_items.start_activity(
            db, actor=auth.user, role=_role(auth),
            work_package_item_id=work_package_item_id, stage=payload.stage,
        )
        _audit(request, db, auth, f"WORKFLOW_ITEM_{payload.stage.upper()}_STARTED", "ortho_work_package",
               item.work_package_id, {"item_id": item.id, "activity_id": activity.id})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"activity_id": activity.id, "stage": activity.stage,
            "started_at": activity.started_at.isoformat() if activity.started_at else None}


@router.post("/ortho/activities/{activity_id}/stop")
def workflow_stop_item_activity(
    activity_id: int,
    payload: WorkflowItemActivityStop,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    activity = db.get(production_items.WorkPackageItemActivity, activity_id)
    if activity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Activity not found")
    _ensure_package_project(db, auth, activity.work_package_id)
    try:
        done = production_items.stop_activity(
            db, actor=auth.user, activity_id=activity_id,
            status=payload.status,
            quantity_completed=payload.quantity_completed,
            unit=payload.unit,
            files_completed=payload.files_completed,
            remarks=payload.remarks,
            delay_category=payload.delay_category,
            affected_item_id=payload.affected_item_id,
            delay_reason=payload.delay_reason,
            system_malfunction=payload.system_malfunction,
            delay_remarks=payload.delay_remarks,
            finalize=payload.finalize,
        )
        _audit(request, db, auth, f"WORKFLOW_ITEM_{done.stage.upper()}_{'FINALIZED' if payload.finalize else 'PROGRESS_SAVED'}", "ortho_work_package",
               done.work_package_id, {
                   "item_id": done.work_package_item_id, "activity_id": done.id,
                   "status": done.status, "files_completed": done.files_completed,
                   "finalized": payload.finalize,
                   "duration_seconds": done.duration_seconds, "delay_category": done.delay_category,
                   "system_malfunction": done.system_malfunction,
               })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"activity_id": done.id, "stage": done.stage, "status": done.status,
            "started_at": done.started_at.isoformat() if done.started_at else None,
            "ended_at": done.ended_at.isoformat() if done.ended_at else None,
            "duration_seconds": done.duration_seconds}


@router.post("/ortho/items/{work_package_item_id}/delivery")
def workflow_deliver_item(
    work_package_item_id: int,
    payload: WorkflowItemDelivery,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    item = _ensure_item_scope(db, auth, work_package_item_id)
    try:
        activity = production_items.deliver_item(
            db, actor=auth.user, role=_role(auth), work_package_item_id=work_package_item_id,
            remarks=payload.remarks, reference=payload.reference,
        )
        _audit(request, db, auth, "WORKFLOW_ITEM_DELIVERED", "ortho_work_package", item.work_package_id,
               {"item_id": item.id, "activity_id": activity.id, "reference": payload.reference})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return {"activity_id": activity.id, "status": activity.status,
            "delivered_at": activity.ended_at.isoformat() if activity.ended_at else None}


@router.get("/ortho/items/{work_package_item_id}/activities")
def workflow_item_history(
    work_package_item_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _roles(auth, *TECHNICAL_PM_ROLES, *_WORKFLOW_ROLES)
    _ensure_item_scope(db, auth, work_package_item_id)
    try:
        events = production_items.item_history(
            db, actor=auth.user, role=_role(auth), work_package_item_id=work_package_item_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"work_package_item_id": work_package_item_id, "events": events}


@router.patch("/ortho/work-packages/{work_package_id}/timeline")
def workflow_package_timeline(
    work_package_id: int,
    payload: WorkflowPackageTimelineUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Set production target / buffer for one area. NEVER rewrites target_date."""
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        package = production_items.load_package(db, work_package_id)
        ctx = production_items.actor_context(db, package, auth.user, _role(auth))
        production_items._ensure_mutable(ctx)
        if "production_target_date" in payload.model_fields_set:
            package.production_target_date = payload.production_target_date
        if "buffer_days" in payload.model_fields_set:
            package.production_buffer_days = payload.buffer_days
        _audit(request, db, auth, "WORKFLOW_PACKAGE_TIMELINE_UPDATED", "ortho_work_package", work_package_id,
               {"production_target_date": package.production_target_date.isoformat() if package.production_target_date else None,
                "buffer_days": package.production_buffer_days, "target_date_unchanged": str(package.target_date)})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    deadline = production_items.deadline_status(
        package, completed_at=production_items.package_completion_for_deadline(db, package)
    )
    return {"id": package.id, "target_date": str(package.target_date) if package.target_date else None,
            "production_target_date": package.production_target_date.isoformat() if package.production_target_date else None,
            "buffer_days": package.production_buffer_days, "deadline": deadline}


# ===========================================================================================
# V8.3 Team Lead Excel-driven daily activity allocation (ADDITIVE). The Team Lead uploads the
# company work-file master, previews it, then confirms a transactional import that creates/reuses
# the shared work packages (areas) and their files. Allocation then uses cascading Lot/Code/Area
# selection with the three stage targets. Nothing here resets existing work history.
# ===========================================================================================

@router.post("/ortho/projects/{project_id}/master-import/preview")
async def workflow_master_import_preview(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Parse + validate the uploaded master workbook and return a preview. Writes nothing."""
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_project_department(db, auth, project_id)
    try:
        content = await file.read()
        return production_allocation.preview_master_import(
            db, actor=auth.user, role=_role(auth), project_id=project_id,
            filename=file.filename or "work-file-master", content=content,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/ortho/projects/{project_id}/master-import/commit", status_code=status.HTTP_201_CREATED)
async def workflow_master_import_commit(
    project_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Transactional import of the confirmed master workbook (idempotent, history-safe)."""
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_project_department(db, auth, project_id)
    try:
        content = await file.read()
        summary = production_allocation.commit_master_import(
            db, actor=auth.user, role=_role(auth), project_id=project_id,
            filename=file.filename or "work-file-master", content=content,
        )
        _audit(request, db, auth, "WORKFLOW_MASTER_IMPORT_COMMITTED", "finance_project", project_id, {
            "filename": file.filename, "created_packages": summary["created_packages"],
            "created_items": summary["created_items"], "skipped_existing": summary["skipped_existing"],
            "conflicts": len(summary["conflicts"]),
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return summary


@router.get("/ortho/projects/{project_id}/allocation-options")
def workflow_allocation_options(
    project_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Cascading Lot / Code / Area data + the PM-approved team lists for allocation."""
    _roles(auth, *TECHNICAL_PM_ROLES, *_WORKFLOW_ROLES)
    _ensure_project_department(db, auth, project_id)
    try:
        return production_allocation.allocation_options(
            db, actor=auth.user, role=_role(auth), project_id=project_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/ortho/work-packages/{work_package_id}/area-files")
def workflow_area_files(
    work_package_id: int,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Active files of one area with planned quantities grouped by compatible UOM."""
    _roles(auth, *TECHNICAL_PM_ROLES, *_WORKFLOW_ROLES)
    _ensure_package_project(db, auth, work_package_id)
    try:
        return production_allocation.area_files(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id
        )
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post("/ortho/work-packages/{work_package_id}/assign-files")
def workflow_assign_files(
    work_package_id: int,
    payload: WorkflowFileAllocation,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Team Lead allocation: selected files + Production/QC/QA targets + Supply Date."""
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        summary = production_allocation.assign_files(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id,
            item_ids=payload.item_ids,
            production_user_id=payload.production_user_id,
            production_target_date=payload.production_target_date,
            qc_user_id=payload.qc_user_id,
            qc_target_date=payload.qc_target_date,
            qa_user_id=payload.qa_user_id,
            qa_target_date=payload.qa_target_date,
            supply_date=payload.supply_date,
            note=payload.note,
        )
        _audit(request, db, auth, "WORKFLOW_FILES_ALLOCATED", "ortho_work_package", work_package_id, {
            "item_ids": payload.item_ids, "production_target_date": str(payload.production_target_date),
            "qc_target_date": str(payload.qc_target_date), "qa_target_date": str(payload.qa_target_date),
            "supply_date": str(payload.supply_date) if payload.supply_date else None,
        })
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return summary


@router.post("/ortho/work-packages/{work_package_id}/ready-for-delivery")
def workflow_ready_for_delivery(
    work_package_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Team Lead / PM confirms Ready for Delivery once every active file passed QA."""
    _roles(auth, *TECHNICAL_PM_ROLES, EMPLOYEE_ROLE)
    _ensure_package_project(db, auth, work_package_id)
    try:
        readiness = production_items.mark_ready_for_delivery(
            db, actor=auth.user, role=_role(auth), work_package_id=work_package_id
        )
        _audit(request, db, auth, "WORKFLOW_READY_FOR_DELIVERY", "ortho_work_package", work_package_id,
               {"total_files": readiness["total_files"], "qa_passed": readiness["qa_passed"]})
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _error(exc) from exc
    return readiness
