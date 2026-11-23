"""Scoped official BD client/project access for BD employee accounts.

No employee identity is ever accepted from a request body. Any action on an
existing client/project checks the persisted creator and BD source on the server.
Legacy manager-approved client/project links remain readable, not writable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.core.departments import SUPPORTED_DEPARTMENTS, department_label
from app.models.entities import User
from app.modules.bd_employee.handoff_models import BdClientHandoff, BdEmployeeProjectLink
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.schemas import FinanceClientCreateRequest
from app.modules.finance.service import client_payload
from app.modules.finance.visibility import exclude_hidden_projects, hidden_client_ids, hidden_project_ids
from app.modules.operations.models import ProjectWorkflow
from app.modules.operations.schemas import WorkflowProjectCreate, WorkflowPMAssignment, WorkflowDepartmentChange
from app.modules.operations.workflow_service import (
    _full_project_payload, _project_query, assign_project_manager, change_project_department_before_work, create_bd_client,
    create_bd_project, update_bd_project, submit_project_to_finance,
    project_manager_options, email_finance_submission, email_project_manager_assignment,
    WORKFLOW_DRAFT, WORKFLOW_PENDING_FINANCE, WORKFLOW_FINANCE_RETURNED,
    WORKFLOW_FINANCE_APPROVED, WORKFLOW_PM_ASSIGNED, WORKFLOW_TEAM_ASSIGNED,
    WORKFLOW_IN_PROGRESS, WORKFLOW_FINANCE_CLOSURE_PENDING, WORKFLOW_CLOSED,
)
from app.modules.commercial.service import commercial_summary
from app.modules.business.schemas import BusinessHistoryEntry, BusinessOverview
from app.modules.business.service import business_employee_history, business_employee_overview
from app.modules.employee_portal.service import record_audit

router = APIRouter(prefix="/direct", tags=["BD Employee Direct Clients and Projects"])


def _employee(auth: CurrentAuth = Depends(get_current_auth)) -> User:
    if auth.user.role != "bd_employee" or auth.effective_role != "bd_employee":
        raise HTTPException(403, "BD Employee access required")
    if not auth.user.is_active:
        raise HTTPException(403, "Employee account inactive")
    return auth.user


def _own_client_ids(db: Session, employee: User) -> set[int]:
    direct = set(db.scalars(select(FinanceClient.id).where(
        FinanceClient.created_by_id == employee.id,
        FinanceClient.source_team == "bd_team",
        FinanceClient.is_active.is_(True),
    )).all())
    # Keep already-approved, historical Get Client handoffs visible. New direct
    # clients never go through the Get Client approval workflow.
    legacy = set(db.scalars(select(BdClientHandoff.registered_client_id).join(
        FinanceClient, FinanceClient.id == BdClientHandoff.registered_client_id,
    ).where(
        BdClientHandoff.employee_user_id == employee.id,
        BdClientHandoff.status == "approved",
        FinanceClient.source_team == "bd_team",
        FinanceClient.is_active.is_(True),
    )).all())
    return (direct | legacy) - hidden_client_ids(db)


def _owned_client(db: Session, employee: User, client_id: int) -> FinanceClient:
    row = db.scalar(select(FinanceClient).where(
        FinanceClient.id == client_id,
        FinanceClient.id.in_(_own_client_ids(db, employee)),
        FinanceClient.source_team == "bd_team",
        FinanceClient.is_active.is_(True),
    ))
    if row is None:
        raise HTTPException(404, "Your BD client was not found")
    return row


def _owned_project(db: Session, employee: User, project_id: int) -> FinanceProject:
    row = db.scalar(select(FinanceProject).join(
        ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id,
    ).join(FinanceClient, FinanceClient.id == FinanceProject.client_id).where(
        FinanceProject.id == project_id,
        FinanceProject.id.not_in(hidden_project_ids(db)),
        FinanceProject.client_id.in_(_own_client_ids(db, employee)),
        FinanceProject.created_by_id == employee.id,
        ProjectWorkflow.bd_owner_user_id == employee.id,
        FinanceProject.project_source_team == "bd_team",
        FinanceClient.source_team == "bd_team",
    ))
    if row is None:
        raise HTTPException(404, "Your BD project was not found")
    return row


def _audit(db: Session, request: Request, employee: User, event: str, target: str, target_id: int, details: dict | None = None) -> None:
    record_audit(db, event_type=event, request=request, user=employee,
                 module="bd_employee_direct", target_type=target, target_id=target_id,
                 details=details or {})


def _visible_employee_project_query(db: Session, employee: User):
    """Single authorization boundary shared by employee projects and business reporting."""
    ids = _own_client_ids(db, employee)
    # Direct ownership, approved historical handoff, or a BD Manager project on
    # this employee's own client. Never trust IDs submitted from a browser.
    own = and_(FinanceProject.created_by_id == employee.id,
               ProjectWorkflow.bd_owner_user_id == employee.id)
    historical = and_(
        BdEmployeeProjectLink.employee_user_id == employee.id,
        BdClientHandoff.employee_user_id == employee.id,
        BdClientHandoff.status == "approved",
        BdClientHandoff.registered_client_id == FinanceProject.client_id,
        BdEmployeeProjectLink.manager_user_id == FinanceProject.created_by_id,
        ProjectWorkflow.bd_owner_user_id == FinanceProject.created_by_id,
    )
    manager_on_own_client = and_(
        FinanceClient.created_by_id == employee.id,
        FinanceProject.created_by_id.in_(select(User.id).where(User.role == "bd")),
        ProjectWorkflow.bd_owner_user_id == FinanceProject.created_by_id,
    )
    query = _project_query().join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
    query = query.join(FinanceClient, FinanceClient.id == FinanceProject.client_id)
    query = query.outerjoin(BdEmployeeProjectLink, BdEmployeeProjectLink.project_id == FinanceProject.id)
    query = query.outerjoin(BdClientHandoff, BdClientHandoff.id == BdEmployeeProjectLink.request_id)
    query = exclude_hidden_projects(db, query).where(
        FinanceProject.client_id.in_(ids),
        FinanceProject.project_source_team == "bd_team",
        FinanceClient.source_team == "bd_team",
        or_(own, historical, manager_on_own_client),
    )
    return query


def _business_project_ids(db: Session, employee: User) -> set[int]:
    return {project.id for project in db.scalars(_visible_employee_project_query(db, employee)).unique().all()}


@router.get("/business/overview", response_model=BusinessOverview)
def employee_business_overview(
    month: str | None = None,
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> BusinessOverview:
    return business_employee_overview(db, month=month, project_ids=_business_project_ids(db, employee))


@router.get("/business/records/{record_id}/history", response_model=list[BusinessHistoryEntry])
def employee_business_history(
    record_id: int,
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> list[BusinessHistoryEntry]:
    return business_employee_history(
        db, record_id=record_id, actor=employee, project_ids=_business_project_ids(db, employee),
    )


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    ids = _own_client_ids(db, employee)
    clients = db.scalars(select(FinanceClient).where(
        FinanceClient.id.in_(ids), FinanceClient.source_team == "bd_team",
    ).order_by(FinanceClient.created_at.desc())).all()
    # Use the exact same project permission check as the employee financial view.
    query = _visible_employee_project_query(db, employee)
    projects = db.scalars(query.order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())).unique().all()
    workflows = {w.project_id: w for w in db.scalars(select(ProjectWorkflow).where(
        ProjectWorkflow.project_id.in_([p.id for p in projects])
    )).all()} if projects else {}
    payloads = []
    for project in projects:
        item = _full_project_payload(db, project, workflows[project.id])
        item["employee_can_edit"] = (
            project.created_by_id == employee.id and
            workflows[project.id].bd_owner_user_id == employee.id
        )
        payloads.append(item)
    counts = {}
    for row in projects:
        counts[row.client_id] = counts.get(row.client_id, 0) + 1
    client_rows = []
    for c in clients:
        data = client_payload(c)
        data["project_count"] = counts.get(c.id, 0)
        data["active_project_count"] = sum(
            1 for p in projects if p.client_id == c.id and p.is_active
        )
        client_rows.append(data)
    pm = project_manager_options(db)
    return {
        "summary": {
            "total": len(payloads),
            "draft": sum(x["normalized_status"] == WORKFLOW_DRAFT for x in payloads),
            "pending_finance": sum(x["normalized_status"] == WORKFLOW_PENDING_FINANCE for x in payloads),
            "returned": sum(x["normalized_status"] == WORKFLOW_FINANCE_RETURNED for x in payloads),
            "approved": sum(x["normalized_status"] in {WORKFLOW_FINANCE_APPROVED, WORKFLOW_PM_ASSIGNED, WORKFLOW_TEAM_ASSIGNED, WORKFLOW_IN_PROGRESS} for x in payloads),
            "completion_pending": sum(x["normalized_status"] == WORKFLOW_FINANCE_CLOSURE_PENDING for x in payloads),
            "closed": sum(x["normalized_status"] == WORKFLOW_CLOSED for x in payloads),
        },
        "clients": client_rows,
        "projects": payloads,
        "project_managers": pm,
        "project_managers_by_department": {code: project_manager_options(db, department_code=code) for code in SUPPORTED_DEPARTMENTS},
        "departments": [{"code": code, "label": department_label(code)} for code in SUPPORTED_DEPARTMENTS],
    }


@router.post("/clients", status_code=status.HTTP_201_CREATED)
def create_client(payload: FinanceClientCreateRequest, request: Request,
                  db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    try:
        # Ignore/overwrite any untrusted source, BD person, management attribution.
        fixed = payload.model_copy(update={
            "source_team": "bd_team", "source_person_name": employee.full_name,
            "bd_name": employee.full_name,
        })
        client = create_bd_client(db, actor=employee, payload=fixed)
        _audit(db, request, employee, "BD_EMPLOYEE_CLIENT_CREATED", "finance_client", client.id,
               {"client_code": client.client_code})
        db.commit()
        db.refresh(client)
        return client_payload(client)
    except Exception as exc:
        db.rollback()
        if isinstance(exc, HTTPException):
            raise
        if isinstance(exc, ValueError):
            raise HTTPException(409, str(exc)) from exc
        raise


@router.post("/projects", status_code=status.HTTP_201_CREATED)
def create_project(payload: WorkflowProjectCreate, request: Request,
                   db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    _owned_client(db, employee, payload.client_id)
    try:
        project, workflow = create_bd_project(db, actor=employee, payload=payload)
        _audit(db, request, employee, "BD_EMPLOYEE_PROJECT_CREATED", "finance_project", project.id,
               {"project_code": project.project_code, "workflow_status": workflow.status})
        db.commit()
        return {"project_id": project.id, "project_code": project.project_code,
                "workflow_status": workflow.status,
                "commercial": commercial_summary(db, project_id=project.id)}
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (ValueError, PermissionError)):
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc
        raise


@router.put("/projects/{project_id}")
def edit_project(project_id: int, payload: WorkflowProjectCreate, request: Request,
                 db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    _owned_project(db, employee, project_id)
    _owned_client(db, employee, payload.client_id)
    try:
        project, workflow = update_bd_project(db, actor=employee, project_id=project_id, payload=payload)
        _audit(db, request, employee, "BD_EMPLOYEE_PROJECT_UPDATED", "finance_project", project.id,
               {"project_code": project.project_code})
        db.commit()
        return {"project_id": project.id, "project_code": project.project_code,
                "workflow_status": workflow.status,
                "commercial": commercial_summary(db, project_id=project.id)}
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (ValueError, PermissionError)):
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc
        raise


@router.post("/projects/{project_id}/submit-finance")
def submit_project(project_id: int, request: Request, db: Session = Depends(get_db),
                   employee: User = Depends(_employee)) -> dict:
    _owned_project(db, employee, project_id)
    try:
        workflow = submit_project_to_finance(db, actor=employee, project_id=project_id)
        _audit(db, request, employee, "BD_EMPLOYEE_PROJECT_SUBMITTED_FINANCE", "finance_project", project_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (ValueError, PermissionError)):
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc
        raise
    email_finance_submission(db, project_id=project_id)
    return {"project_id": project_id, "workflow_status": workflow.status}


@router.post("/projects/{project_id}/assign-pm")
def assign_pm(project_id: int, payload: WorkflowPMAssignment, request: Request,
              db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    _owned_project(db, employee, project_id)
    try:
        workflow, manager = assign_project_manager(db, actor=employee, project_id=project_id, payload=payload)
        _audit(db, request, employee, "BD_EMPLOYEE_ASSIGNED_PM", "finance_project", project_id,
               {"project_manager_id": manager.id})
        db.commit()
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (ValueError, PermissionError)):
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc
        raise
    email_project_manager_assignment(db, project_id=project_id, pm_id=manager.id)
    return {"project_id": project_id, "project_manager_id": manager.id,
            "workflow_status": workflow.status}


@router.post("/projects/{project_id}/change-department")
def change_department(project_id: int, payload: WorkflowDepartmentChange, request: Request,
                      db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    _owned_project(db, employee, project_id)
    try:
        result = change_project_department_before_work(
            db, actor=employee, project_id=project_id, payload=payload, source="bd",
        )
        _audit(db, request, employee, "BD_EMPLOYEE_PROJECT_DEPARTMENT_CHANGED", "finance_project", project_id, result)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (ValueError, PermissionError)):
            raise HTTPException(422 if isinstance(exc, ValueError) else 403, str(exc)) from exc
        raise


@router.get("/project-tracking")
def employee_official_project_tracking(
    project_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    employee: User = Depends(_employee),
) -> dict:
    """BD Manager's live tracking read-model, scoped to the caller's own projects.

    The existing direct dashboard is authoritative for employee project visibility:
    BD-origin only; same employee's clients and own projects; or verified
    historical client attribution. Request-provided IDs can only narrow it.
    The tracking service is called in BD read-only mode; no operations mutations.
    """
    from app.modules.operations.production_service import tracking_summary

    registered = dashboard(db=db, employee=employee)
    allowed_ids = {
        int(row["id"])
        for row in registered["projects"]
        if row.get("id") is not None
    }
    if project_id is not None:
        allowed_ids.intersection_update({project_id})
    return tracking_summary(
        db,
        actor=employee,
        role="bd",
        authorized_bd_project_ids=allowed_ids,
        project_id=project_id,
    )
