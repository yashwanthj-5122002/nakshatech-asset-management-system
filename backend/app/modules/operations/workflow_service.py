from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
import json
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import (
    ExpenseClaim,
    FinanceClient,
    FinanceProject,
    FinanceProjectAssignment,
    FinanceProjectMasterProfile,
)
from app.modules.finance.schemas import FinanceClientCreateRequest, FinanceClientProjectCreateRequest
from app.modules.finance.service import (
    approved_amount,
    claim_paid_amount,
    client_payload,
    create_client_project,
    create_finance_client,
    list_finance_clients,
    remaining_amount,
    set_project_status,
)
from app.modules.notifications.service import create_global_notification, resolve_recipient_users
from app.modules.operations.models import (
    OrthoDailyUpdate,
    OrthoProjectMember,
    OrthoProjectProfile,
    OrthoReview,
    OrthoWorkPackage,
    ProjectWorkflow,
    ProjectWorkflowEvent,
)
from app.modules.operations.schemas import (
    WorkflowDailyActivity,
    WorkflowDeliveryRequest,
    WorkflowFinanceClosure,
    WorkflowFinanceReview,
    WorkflowOperationalCompletion,
    WorkflowPMAssignment,
    WorkflowProjectCreate,
    WorkflowReviewRequest,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)

logger = logging.getLogger(__name__)

BD_ROLE = "bd"
FINANCE_ROLE = "finance"
ORTHO_ROLE = "ortho"
EMPLOYEE_ROLE = "employee"
ADMIN_ROLE = "admin"
MANAGEMENT_ROLE = "management"

WORKFLOW_DRAFT = "draft"
WORKFLOW_PENDING_FINANCE = "pending_finance_approval"
WORKFLOW_FINANCE_RETURNED = "finance_returned"
WORKFLOW_FINANCE_APPROVED = "finance_approved"
WORKFLOW_PM_ASSIGNED = "pm_assigned"
WORKFLOW_TEAM_ASSIGNED = "team_assigned"
WORKFLOW_IN_PROGRESS = "in_progress"
WORKFLOW_FINANCE_CLOSURE_PENDING = "finance_closure_pending"
WORKFLOW_CLOSED = "closed"

TEAM_ROLES = ("team_leader", "production", "qc", "qa")


def _event(
    db: Session,
    *,
    workflow: ProjectWorkflow,
    actor: User,
    event_type: str,
    to_status: str,
    comments: str | None = None,
) -> None:
    previous = workflow.status
    workflow.status = to_status
    workflow.updated_by_id = actor.id
    workflow.updated_at = utc_now()
    db.add(ProjectWorkflowEvent(
        project_id=workflow.project_id,
        event_type=event_type,
        from_status=previous,
        to_status=to_status,
        comments=(comments or "").strip() or None,
        actor_user_id=actor.id,
    ))


def _project_query():
    return (
        select(FinanceProject)
        .options(
            selectinload(FinanceProject.client),
            selectinload(FinanceProject.master_profile).selectinload(FinanceProjectMasterProfile.project_manager),
            selectinload(FinanceProject.assignments).selectinload(FinanceProjectAssignment.user),
        )
    )


def _project(db: Session, project_id: int) -> FinanceProject:
    row = db.scalar(_project_query().where(FinanceProject.id == project_id))
    if row is None:
        raise ValueError("Project not found")
    return row


def _workflow(db: Session, project_id: int) -> ProjectWorkflow:
    row = db.get(ProjectWorkflow, project_id)
    if row is None:
        raise ValueError("Project workflow not found")
    return row


def _client_code(project: FinanceProject) -> str | None:
    return project.client.client_code if project.client else None


def _client_name(project: FinanceProject) -> str | None:
    return project.client.client_name if project.client else project.client_name


def _pm(project: FinanceProject) -> User | None:
    return project.master_profile.project_manager if project.master_profile else None


def _events(db: Session, project_id: int) -> list[dict]:
    rows = db.scalars(
        select(ProjectWorkflowEvent)
        .where(ProjectWorkflowEvent.project_id == project_id)
        .order_by(ProjectWorkflowEvent.created_at.asc(), ProjectWorkflowEvent.id.asc())
    ).all()
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_({row.actor_user_id for row in rows}))).all()
    } if rows else {}
    return [
        {
            "id": row.id,
            "event_type": row.event_type,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "comments": row.comments,
            "actor_user_id": row.actor_user_id,
            "actor_name": users[row.actor_user_id].full_name if row.actor_user_id in users else None,
            "actor_role": users[row.actor_user_id].role if row.actor_user_id in users else None,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def _attachment_references(workflow: ProjectWorkflow) -> list[str]:
    if not workflow.attachment_references:
        return []
    try:
        value = json.loads(workflow.attachment_references)
    except (TypeError, ValueError):
        return [item.strip() for item in workflow.attachment_references.splitlines() if item.strip()]
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _full_project_payload(db: Session, project: FinanceProject, workflow: ProjectWorkflow) -> dict:
    pm = _pm(project)
    client = project.client
    client_profile = client.master_profile if client else None
    owner = db.get(User, workflow.bd_owner_user_id)
    reviewer = db.get(User, workflow.finance_reviewer_id) if workflow.finance_reviewer_id else None
    creator = db.get(User, project.created_by_id) if project.created_by_id else None
    events = _events(db, project.id)
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "client_id": project.client_id,
        "client_code": _client_code(project),
        "client_name": _client_name(project),
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "description": project.description,
        "scope_text": workflow.scope_text,
        "quantity": float(workflow.quantity) if workflow.quantity is not None else None,
        "quantity_unit": workflow.quantity_unit,
        "priority": workflow.priority,
        "commercial_value": float(workflow.commercial_value) if workflow.commercial_value is not None else None,
        "currency": workflow.currency,
        "po_wo_number": workflow.po_wo_number,
        "attachment_references": _attachment_references(workflow),
        "workflow_status": workflow.status,
        "finance_feedback": workflow.finance_feedback,
        "submission_count": workflow.submission_count or sum(1 for event in events if event["event_type"] == "submitted_to_finance"),
        "finance_reviewer_id": workflow.finance_reviewer_id,
        "finance_reviewer_name": reviewer.full_name if reviewer else None,
        "finance_reviewed_at": workflow.finance_reviewed_at.isoformat() if workflow.finance_reviewed_at else None,
        "project_manager_id": pm.id if pm else None,
        "project_manager_name": pm.full_name if pm else None,
        "project_manager_email": pm.email if pm else None,
        "submitted_at": workflow.submitted_at.isoformat() if workflow.submitted_at else None,
        "approved_at": workflow.approved_at.isoformat() if workflow.approved_at else None,
        "operational_completed_at": workflow.operational_completed_at.isoformat() if workflow.operational_completed_at else None,
        "completion_date": workflow.completion_date.isoformat() if workflow.completion_date else None,
        "final_delivery_reference": workflow.final_delivery_reference,
        "completion_remarks": workflow.completion_remarks,
        "finance_closed_at": workflow.finance_closed_at.isoformat() if workflow.finance_closed_at else None,
        "finance_closure_remarks": workflow.finance_closure_remarks,
        "created_at": project.created_at.isoformat(),
        "updated_at": project.updated_at.isoformat(),
        "created_by_name": creator.full_name if creator else None,
        "submitted_by_name": owner.full_name if owner else None,
        "submitted_by_email": owner.email if owner else None,
        "client": {
            "organization_name": client.client_name if client else project.client_name,
            "client_code": client.client_code if client else None,
            "client_email": client.client_email if client else None,
            "organization_email": client_profile.organization_email if client_profile else None,
            "location": (client.address or client.country) if client else None,
            "gst_number": client.gst_number if client else None,
            "contact_person_name": client.contact_person_name if client else None,
            "contact_person_email": client_profile.contact_person_email if client_profile else None,
            "contact_person_phone": client.contact_person_phone if client and client.contact_person_phone != "Not provided" else None,
            "bd_person": client_profile.bd_name if client_profile and client_profile.bd_name else (client.source_person_name if client else None),
        },
        "events": events,
    }


def project_manager_options(db: Session) -> list[dict]:
    users = db.scalars(
        select(User).where(
            User.role == ORTHO_ROLE,
            User.is_active.is_(True),
            User.account_status.in_(["active", "pending_mfa"]),
        ).order_by(User.full_name.asc(), User.email.asc())
    ).all()
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "employee_id": user.employee_id,
            "department": user.department,
            "designation": user.designation,
        }
        for user in users
    ]


def employee_options(db: Session) -> list[dict]:
    users = db.scalars(
        select(User).where(
            User.role == EMPLOYEE_ROLE,
            User.is_active.is_(True),
            User.account_status.in_(["active", "pending_mfa"]),
        ).order_by(User.full_name.asc(), User.email.asc())
    ).all()
    return [
        {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "employee_id": user.employee_id,
            "department": user.department,
            "designation": user.designation,
        }
        for user in users
    ]


def bd_dashboard(db: Session, *, actor: User, role: str) -> dict:
    query = _project_query().join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
    if role == BD_ROLE:
        query = query.where(ProjectWorkflow.bd_owner_user_id == actor.id)
    projects = list(db.scalars(query.order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())).unique().all())
    workflows = {row.project_id: row for row in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_([p.id for p in projects]))).all()} if projects else {}
    payloads = [_full_project_payload(db, project, workflows[project.id]) for project in projects]
    return {
        "summary": {
            "total": len(payloads),
            "draft": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_DRAFT),
            "pending_finance": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_PENDING_FINANCE),
            "returned": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_FINANCE_RETURNED),
            "approved": sum(1 for p in payloads if p["workflow_status"] in {WORKFLOW_FINANCE_APPROVED, WORKFLOW_PM_ASSIGNED, WORKFLOW_TEAM_ASSIGNED, WORKFLOW_IN_PROGRESS}),
            "completion_pending": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_FINANCE_CLOSURE_PENDING),
            "closed": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_CLOSED),
        },
        "clients": [client_payload(client) for client in list_finance_clients(db)],
        "project_managers": project_manager_options(db),
        "projects": payloads,
    }


def create_bd_client(db: Session, *, actor: User, payload: FinanceClientCreateRequest) -> FinanceClient:
    # BD is the authoritative creator. Force the source metadata to BD while keeping
    # all other Client Master validation and duplicate checks unchanged.
    data = payload.model_copy(update={
        "source_team": "bd_team",
        "source_person_name": payload.source_person_name or actor.full_name,
        "bd_name": payload.bd_name or actor.full_name,
    })
    return create_finance_client(db, actor=actor, payload=data)


def create_bd_project(db: Session, *, actor: User, payload: WorkflowProjectCreate) -> tuple[FinanceProject, ProjectWorkflow]:
    client = db.get(FinanceClient, payload.client_id)
    if client is None or not client.is_active:
        raise ValueError("Select an active existing Client ID before creating the project")
    finance_payload = FinanceClientProjectCreateRequest(
        project_code=payload.project_code,
        project_name=payload.project_name,
        task=payload.scope_text,
        project_status="inactive",
        project_manager_id=None,
        reporting_manager_id=None,
        assigned_employee_ids=[],
        project_source_team="bd_team",
        project_source_person_name=actor.full_name,
        client_awarded_by_name=None,
        project_award_date=None,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=False,
    )
    project = create_client_project(db, client=client, actor=actor, payload=finance_payload)
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=actor.id,
        status=WORKFLOW_DRAFT,
        scope_text=payload.scope_text,
        quantity=payload.quantity,
        quantity_unit=payload.quantity_unit,
        priority=payload.priority,
        commercial_value=payload.commercial_value,
        currency=payload.currency.upper(),
        po_wo_number=payload.po_wo_number,
        attachment_references=json.dumps(payload.attachment_references),
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.add(workflow)
    db.flush()
    db.add(ProjectWorkflowEvent(
        project_id=project.id,
        event_type="bd_project_created",
        from_status=None,
        to_status=WORKFLOW_DRAFT,
        comments="Project created by Business Development",
        actor_user_id=actor.id,
    ))
    db.flush()
    return project, workflow


def update_bd_project(
    db: Session, *, actor: User, project_id: int, payload: WorkflowProjectCreate
) -> tuple[FinanceProject, ProjectWorkflow]:
    """Allow the BD owner to correct a Draft/Finance Returned project before resubmission.

    The manually entered Project ID remains authoritative. Changes are audited through
    the workflow event stream; Finance-approved/operational records are intentionally
    immutable through this endpoint.
    """
    workflow = _workflow(db, project_id)
    if workflow.bd_owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can correct this project")
    if workflow.status not in {WORKFLOW_DRAFT, WORKFLOW_FINANCE_RETURNED}:
        raise ValueError("Only Draft or Finance Returned projects can be edited by BD")

    project = _project(db, project_id)
    client = db.get(FinanceClient, payload.client_id)
    if client is None or not client.is_active:
        raise ValueError("Select an active existing Client ID")

    duplicate = db.scalar(
        select(FinanceProject.id).where(
            func.lower(FinanceProject.project_code) == payload.project_code.lower(),
            FinanceProject.id != project.id,
        ).limit(1)
    )
    if duplicate is not None:
        raise ValueError(f"Project ID {payload.project_code} is already in use")

    project.project_code = payload.project_code
    project.project_name = payload.project_name
    project.client_id = client.id
    project.client_name = client.client_name
    project.project_source_team = "bd_team"
    project.project_source_person_name = actor.full_name
    project.description = payload.description
    project.start_date = payload.start_date
    project.end_date = payload.end_date
    project.updated_at = utc_now()
    if project.master_profile is not None:
        project.master_profile.task = payload.scope_text
        project.master_profile.updated_by_id = actor.id
        project.master_profile.updated_at = utc_now()

    workflow.scope_text = payload.scope_text
    workflow.quantity = payload.quantity
    workflow.quantity_unit = payload.quantity_unit
    workflow.priority = payload.priority
    workflow.commercial_value = payload.commercial_value
    workflow.currency = payload.currency.upper()
    workflow.po_wo_number = payload.po_wo_number
    workflow.attachment_references = json.dumps(payload.attachment_references)
    workflow.updated_by_id = actor.id
    workflow.updated_at = utc_now()
    # Keep Finance feedback visible until BD resubmits so the correction reason is not lost.
    db.add(ProjectWorkflowEvent(
        project_id=project.id,
        event_type="bd_project_corrected",
        from_status=workflow.status,
        to_status=workflow.status,
        comments="BD updated project details before Finance resubmission",
        actor_user_id=actor.id,
    ))
    db.flush()
    return project, workflow


def submit_project_to_finance(db: Session, *, actor: User, project_id: int) -> ProjectWorkflow:
    workflow = _workflow(db, project_id)
    if workflow.bd_owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can submit this project to Finance")
    if workflow.status not in {WORKFLOW_DRAFT, WORKFLOW_FINANCE_RETURNED}:
        raise ValueError("Only Draft or Finance Returned projects can be submitted to Finance")
    workflow.finance_feedback = None
    workflow.submitted_at = utc_now()
    workflow.submission_count = int(workflow.submission_count or 0) + 1
    _event(db, workflow=workflow, actor=actor, event_type="submitted_to_finance", to_status=WORKFLOW_PENDING_FINANCE)
    project = _project(db, project_id)
    create_global_notification(
        db,
        event_type="workflow.project.submitted_finance",
        title=f"Finance review required: {project.project_code}",
        message=f"BD submitted Project ID {project.project_code} for Finance approval. Client ID: {_client_code(project) or 'Not recorded'}.",
        category="approval",
        target_url="/finance",
        recipient_roles=[FINANCE_ROLE],
    )
    db.flush()
    return workflow


def _safe_send_email(*, recipient: str, subject: str, body: str, from_name: str) -> None:
    try:
        send_email(recipient=recipient, subject=subject, body=body, from_name=from_name)
    except Exception:
        logger.exception("Workflow email delivery failed to %s", recipient)


def email_finance_submission(db: Session, *, project_id: int) -> None:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    for user in resolve_recipient_users(db, recipient_roles=[FINANCE_ROLE]):
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Project approval required",
            body=(
                f"Hello {user.full_name},\n\n"
                f"Business Development submitted a project for Finance approval.\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Project Name: {project.project_name}\n"
                f"Start Date: {project.start_date.isoformat() if project.start_date else 'Not recorded'}\n"
                f"End Date: {project.end_date.isoformat() if project.end_date else 'Not recorded'}\n"
                f"Commercial Value: {workflow.currency} {workflow.commercial_value if workflow.commercial_value is not None else 'Not recorded'}\n"
                f"PO / WO: {workflow.po_wo_number or 'Not recorded'}\n\n"
                f"Review in ERP: {settings.app_public_url.rstrip('/')}/finance\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech BD -> Finance",
        )


def _project_expense_summary(db: Session, project_id: int) -> dict:
    claims = list(db.scalars(
        select(ExpenseClaim)
        .options(selectinload(ExpenseClaim.payments))
        .where(ExpenseClaim.project_id == project_id)
    ).unique().all())
    requested = sum((claim.total_amount or Decimal("0")) for claim in claims)
    approved = sum((approved_amount(claim) for claim in claims), Decimal("0"))
    paid = sum((claim_paid_amount(claim) for claim in claims), Decimal("0"))
    outstanding = sum((remaining_amount(claim) for claim in claims), Decimal("0"))
    unresolved_statuses = {
        "submitted", "admin_approved", "finance_approved", "partially_paid", "sent_back",
    }
    return {
        "claim_count": len(claims),
        "requested_amount": float(requested),
        "approved_amount": float(approved),
        "paid_amount": float(paid),
        "outstanding_amount": float(outstanding),
        "unresolved_claim_count": sum(1 for claim in claims if claim.status in unresolved_statuses),
    }


def finance_dashboard(db: Session) -> dict:
    projects = list(db.scalars(
        _project_query()
        .join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
        .order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())
    ).unique().all())
    workflows = {row.project_id: row for row in db.scalars(select(ProjectWorkflow)).all()}
    payloads = []
    for project in projects:
        if project.id not in workflows:
            continue
        payload = _full_project_payload(db, project, workflows[project.id])
        payload["expense_summary"] = _project_expense_summary(db, project.id)
        payloads.append(payload)
    return {
        "summary": {
            "pending_approval": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_PENDING_FINANCE),
            "returned": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_FINANCE_RETURNED),
            "approved": sum(1 for p in payloads if p["workflow_status"] in {WORKFLOW_FINANCE_APPROVED, WORKFLOW_PM_ASSIGNED, WORKFLOW_TEAM_ASSIGNED, WORKFLOW_IN_PROGRESS}),
            "closure_pending": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_FINANCE_CLOSURE_PENDING),
            "closed": sum(1 for p in payloads if p["workflow_status"] == WORKFLOW_CLOSED),
        },
        "projects": payloads,
    }


def finance_review_project(db: Session, *, actor: User, project_id: int, payload: WorkflowFinanceReview) -> ProjectWorkflow:
    workflow = _workflow(db, project_id)
    if workflow.status != WORKFLOW_PENDING_FINANCE:
        raise ValueError("This project is not waiting for Finance approval")
    project = _project(db, project_id)
    workflow.finance_reviewer_id = actor.id
    workflow.finance_reviewed_at = utc_now()
    if payload.decision == "return":
        feedback = (payload.feedback or "").strip()
        if not feedback:
            raise ValueError("Finance feedback is mandatory when returning a project")
        workflow.finance_feedback = feedback
        workflow.returned_at = utc_now()
        _event(db, workflow=workflow, actor=actor, event_type="finance_returned", to_status=WORKFLOW_FINANCE_RETURNED, comments=feedback)
        title = f"Finance returned {project.project_code}"
        message = f"Finance returned Project ID {project.project_code}. Feedback: {feedback}"
    else:
        workflow.finance_feedback = None
        workflow.approved_at = utc_now()
        set_project_status(db, project=project, actor=actor, project_status="active")
        _event(db, workflow=workflow, actor=actor, event_type="finance_approved", to_status=WORKFLOW_FINANCE_APPROVED, comments=payload.feedback)
        title = f"Finance approved {project.project_code}"
        message = f"Finance approved Project ID {project.project_code}. You can now assign the Ortho Project Manager."
    create_global_notification(
        db,
        event_type=f"workflow.project.finance_{payload.decision}",
        title=title,
        message=message,
        category="approval",
        target_url="/bd",
        recipient_user_ids=[workflow.bd_owner_user_id],
    )
    db.flush()
    return workflow


def email_bd_finance_review(db: Session, *, project_id: int, decision: str) -> None:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    owner = db.get(User, workflow.bd_owner_user_id)
    if owner is None:
        return
    status_text = "approved" if decision == "approve" else "returned for correction"
    feedback_line = f"\nFinance Feedback: {workflow.finance_feedback}" if workflow.finance_feedback else ""
    _safe_send_email(
        recipient=owner.email,
        subject=f"[{project.project_code}] Finance {status_text}",
        body=(
            f"Hello {owner.full_name},\n\n"
            f"Finance has {status_text} Project ID {project.project_code}.\n"
            f"Client ID: {_client_code(project) or 'Not recorded'}"
            f"{feedback_line}\n\n"
            f"ERP BD Dashboard: {settings.app_public_url.rstrip('/')}/bd\n\n"
            "Nakshatech ERP"
        ),
        from_name="Nakshatech Finance -> BD",
    )


def _ensure_profile_and_pm_member(db: Session, *, project: FinanceProject, workflow: ProjectWorkflow, actor: User, pm: User) -> OrthoProjectProfile:
    profile = db.get(OrthoProjectProfile, project.id)
    if profile is None:
        profile = OrthoProjectProfile(
            project_id=project.id,
            opportunity_id=None,
            total_area=workflow.quantity,
            area_unit=workflow.quantity_unit,
            scope_text=workflow.scope_text,
            planned_hours=None,
            target_value=None,
            project_manager_user_id=pm.id,
            status="active",
            created_by_id=actor.id,
        )
        db.add(profile)
        db.flush()
    else:
        profile.total_area = workflow.quantity
        profile.area_unit = workflow.quantity_unit
        profile.scope_text = workflow.scope_text
        profile.project_manager_user_id = pm.id
        if profile.status in {"closed", "delivered"}:
            raise ValueError("Project Manager cannot be changed after operational completion")

    rows = list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project.id,
        OrthoProjectMember.member_role == "project_manager",
    )).all())
    selected = None
    for row in rows:
        row.is_active = row.user_id == pm.id
        row.assigned_by_id = actor.id
        if row.user_id == pm.id:
            selected = row
    if selected is None:
        db.add(OrthoProjectMember(
            project_id=project.id,
            user_id=pm.id,
            member_role="project_manager",
            is_active=True,
            assigned_by_id=actor.id,
        ))
    db.flush()
    return profile


def assign_project_manager(db: Session, *, actor: User, project_id: int, payload: WorkflowPMAssignment) -> tuple[ProjectWorkflow, User]:
    workflow = _workflow(db, project_id)
    if workflow.bd_owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can assign the Ortho Project Manager")
    if workflow.status not in {WORKFLOW_FINANCE_APPROVED, WORKFLOW_PM_ASSIGNED}:
        raise ValueError("Project Manager can be assigned only after Finance approval and before the project team starts work")
    pm = db.get(User, payload.project_manager_id)
    if pm is None or not pm.is_active or pm.role != ORTHO_ROLE:
        raise ValueError("Select an active Ortho Project Manager account")
    project = _project(db, project_id)
    if project.master_profile is None:
        project.master_profile = FinanceProjectMasterProfile(
            project_id=project.id,
            project_status="active",
            project_manager_id=pm.id,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        db.add(project.master_profile)
    else:
        project.master_profile.project_manager_id = pm.id
        project.master_profile.updated_by_id = actor.id
        project.master_profile.updated_at = utc_now()
    _ensure_profile_and_pm_member(db, project=project, workflow=workflow, actor=actor, pm=pm)
    workflow.pm_assigned_at = utc_now()
    _event(db, workflow=workflow, actor=actor, event_type="bd_assigned_pm", to_status=WORKFLOW_PM_ASSIGNED, comments=f"PM user {pm.id}")
    create_global_notification(
        db,
        event_type="workflow.project.pm_assigned",
        title=f"New project assigned: {project.project_code}",
        message=f"You are the Ortho Project Manager for Project ID {project.project_code}. Client ID: {_client_code(project) or 'Not recorded'}.",
        category="system",
        target_url="/ortho",
        recipient_user_ids=[pm.id],
    )
    db.flush()
    return workflow, pm


def email_project_manager_assignment(db: Session, *, project_id: int, pm_id: int) -> None:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    pm = db.get(User, pm_id)
    if pm is None:
        return
    _safe_send_email(
        recipient=pm.email,
        subject=f"[{project.project_code}] Ortho Project Manager assignment",
        body=(
            f"Hello {pm.full_name},\n\n"
            "Business Development assigned you as the Ortho Project Manager.\n\n"
            f"Project ID: {project.project_code}\n"
            f"Client ID: {_client_code(project) or 'Not recorded'}\n"
            f"Start Date: {project.start_date.isoformat() if project.start_date else 'Not recorded'}\n"
            f"End Date: {project.end_date.isoformat() if project.end_date else 'Not recorded'}\n"
            f"Scope: {workflow.scope_text or 'Not recorded'}\n"
            f"Quantity: {workflow.quantity if workflow.quantity is not None else 'Not recorded'} {workflow.quantity_unit}\n\n"
            f"ERP Ortho Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
            "Nakshatech ERP"
        ),
        from_name="Nakshatech BD -> Ortho",
    )


def _is_pm(project: FinanceProject, user_id: int) -> bool:
    return bool(project.master_profile and project.master_profile.project_manager_id == user_id)


def _active_member_ids(db: Session, *, project_id: int, role: str) -> set[int]:
    return {int(value) for value in db.scalars(select(OrthoProjectMember.user_id).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.member_role == role,
        OrthoProjectMember.is_active.is_(True),
    )).all()}


def _validate_employee(db: Session, user_id: int, label: str) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.role != EMPLOYEE_ROLE:
        raise ValueError(f"Selected {label} must be an active Employee account")
    return user


def _assert_removable_members_not_assigned(db: Session, *, project_id: int, role: str, removed_ids: set[int]) -> None:
    if not removed_ids:
        return
    field = {
        "team_leader": OrthoWorkPackage.team_leader_user_id,
        "production": OrthoWorkPackage.production_user_id,
        "qc": OrthoWorkPackage.qc_user_id,
        "qa": OrthoWorkPackage.qa_user_id,
    }[role]
    referenced = set(db.scalars(select(field).where(
        OrthoWorkPackage.project_id == project_id,
        field.in_(removed_ids),
        OrthoWorkPackage.current_stage != "delivered",
    )).all())
    if referenced:
        raise ValueError(f"Reassign active work packages before removing {role.replace('_', ' ')} employee(s): {sorted(referenced)}")


def _set_role_members(db: Session, *, project_id: int, actor: User, role: str, selected_ids: set[int]) -> None:
    current = _active_member_ids(db, project_id=project_id, role=role)
    _assert_removable_members_not_assigned(db, project_id=project_id, role=role, removed_ids=current - selected_ids)
    rows = list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.member_role == role,
    )).all())
    existing = {(row.user_id, row.member_role): row for row in rows}
    for row in rows:
        row.is_active = row.user_id in selected_ids
        row.assigned_by_id = actor.id
    for user_id in selected_ids:
        if (user_id, role) not in existing:
            db.add(OrthoProjectMember(
                project_id=project_id,
                user_id=user_id,
                member_role=role,
                is_active=True,
                assigned_by_id=actor.id,
            ))


def _sync_finance_assignments(db: Session, *, project_id: int, actor: User, selected_ids: set[int]) -> None:
    rows = list(db.scalars(select(FinanceProjectAssignment).where(FinanceProjectAssignment.project_id == project_id)).all())
    by_user = {row.user_id: row for row in rows}
    for row in rows:
        row.is_active = row.user_id in selected_ids
        row.assigned_by_id = actor.id
        row.updated_at = utc_now()
    for user_id in selected_ids:
        if user_id not in by_user:
            db.add(FinanceProjectAssignment(
                project_id=project_id,
                user_id=user_id,
                assigned_by_id=actor.id,
                is_active=True,
            ))


def configure_team(db: Session, *, actor: User, project_id: int, payload: WorkflowTeamSetup) -> tuple[ProjectWorkflow, dict[int, list[str]]]:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if not _is_pm(project, actor.id):
        raise PermissionError("Only the BD-assigned Ortho Project Manager can select the project team")
    if workflow.status not in {WORKFLOW_PM_ASSIGNED, WORKFLOW_TEAM_ASSIGNED, WORKFLOW_IN_PROGRESS}:
        raise ValueError("BD must assign the Project Manager before team selection")

    selected = {
        "team_leader": {payload.team_leader_user_id},
        "production": set(payload.production_user_ids),
        "qc": set(payload.qc_user_ids),
        "qa": set(payload.qa_user_ids),
    }
    for role, ids in selected.items():
        if not ids:
            raise ValueError(f"Select at least one {role.replace('_', ' ')} employee")
        for user_id in ids:
            _validate_employee(db, user_id, role.replace("_", " "))
    if len(selected["team_leader"]) != 1:
        raise ValueError("Exactly one Team Lead is required")

    for role, ids in selected.items():
        _set_role_members(db, project_id=project_id, actor=actor, role=role, selected_ids=ids)

    all_employee_ids = set().union(*selected.values())
    _sync_finance_assignments(db, project_id=project_id, actor=actor, selected_ids=all_employee_ids)
    workflow.team_assigned_at = utc_now()
    next_status = WORKFLOW_IN_PROGRESS if db.scalar(select(OrthoWorkPackage.id).where(OrthoWorkPackage.project_id == project_id).limit(1)) else WORKFLOW_TEAM_ASSIGNED
    _event(db, workflow=workflow, actor=actor, event_type="pm_team_assigned", to_status=next_status)

    roles_by_user: dict[int, list[str]] = defaultdict(list)
    for role, ids in selected.items():
        for user_id in ids:
            roles_by_user[user_id].append(role)
    for user_id, roles in roles_by_user.items():
        create_global_notification(
            db,
            event_type="workflow.project.team_assignment",
            title=f"Project team assignment: {project.project_code}",
            message=f"Project ID {project.project_code} · Client ID {_client_code(project) or 'Not recorded'} · Role(s): {', '.join(role.replace('_', ' ').title() for role in roles)}.",
            category="system",
            target_url="/ortho",
            recipient_user_ids=[user_id],
        )
    db.flush()
    return workflow, dict(roles_by_user)


def email_team_assignments(db: Session, *, project_id: int, roles_by_user: dict[int, list[str]]) -> None:
    project = _project(db, project_id)
    tl_ids = _active_member_ids(db, project_id=project_id, role="team_leader")
    team_lead = db.get(User, next(iter(tl_ids))) if tl_ids else None
    for user_id, roles in roles_by_user.items():
        user = db.get(User, user_id)
        if user is None:
            continue
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Project team assignment",
            body=(
                f"Hello {user.full_name},\n\n"
                "You have been selected for an Ortho project in Nakshatech ERP.\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Role(s): {', '.join(role.replace('_', ' ').title() for role in roles)}\n"
                f"Team Lead: {(team_lead.employee_id or team_lead.full_name) if team_lead else 'Not assigned'}\n"
                f"Start Date: {project.start_date.isoformat() if project.start_date else 'Not recorded'}\n"
                f"End Date: {project.end_date.isoformat() if project.end_date else 'Not recorded'}\n\n"
                "Your exact Area / Code / Quantity task will appear after the Team Lead allocates it.\n"
                f"ERP Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Ortho",
        )


def _member_roles(db: Session, *, project_id: int, user_id: int) -> set[str]:
    return set(db.scalars(select(OrthoProjectMember.member_role).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.user_id == user_id,
        OrthoProjectMember.is_active.is_(True),
    )).all())


def _is_team_lead(db: Session, *, project_id: int, user_id: int) -> bool:
    return "team_leader" in _member_roles(db, project_id=project_id, user_id=user_id)


def _ensure_role_member(db: Session, *, project_id: int, role: str, user_id: int) -> None:
    exists = db.scalar(select(OrthoProjectMember.id).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.member_role == role,
        OrthoProjectMember.user_id == user_id,
        OrthoProjectMember.is_active.is_(True),
    ).limit(1))
    if exists is None:
        raise ValueError(f"The selected {role.replace('_', ' ')} employee was not selected by the Project Manager")


def allocate_work(db: Session, *, actor: User, project_id: int, payload: WorkflowWorkAllocation) -> OrthoWorkPackage:
    workflow = _workflow(db, project_id)
    if not _is_team_lead(db, project_id=project_id, user_id=actor.id):
        raise PermissionError("Only the Project Manager-selected Team Lead can distribute Area / Code / Quantity work")
    if workflow.status not in {WORKFLOW_TEAM_ASSIGNED, WORKFLOW_IN_PROGRESS}:
        raise ValueError("The Project Manager must select the project team before work allocation")
    _ensure_role_member(db, project_id=project_id, role="production", user_id=payload.production_user_id)
    _ensure_role_member(db, project_id=project_id, role="qc", user_id=payload.qc_user_id)
    _ensure_role_member(db, project_id=project_id, role="qa", user_id=payload.qa_user_id)
    duplicate = db.scalar(select(OrthoWorkPackage.id).where(
        OrthoWorkPackage.project_id == project_id,
        func.lower(OrthoWorkPackage.package_code) == payload.package_code.lower(),
    ).limit(1))
    if duplicate is not None:
        raise ValueError(f"Code {payload.package_code} already exists in this project")
    package = OrthoWorkPackage(
        project_id=project_id,
        package_code=payload.package_code,
        package_name=payload.area_name,
        area=payload.quantity,
        area_unit=payload.quantity_unit,
        target_hours=None,
        target_date=payload.target_date,
        instructions=payload.instructions,
        current_stage="not_started",
        production_state="not_started",
        qc_state="not_started",
        qa_state="not_started",
        team_leader_user_id=actor.id,
        production_user_id=payload.production_user_id,
        qc_user_id=payload.qc_user_id,
        qa_user_id=payload.qa_user_id,
        created_by_id=actor.id,
    )
    db.add(package)
    _event(db, workflow=workflow, actor=actor, event_type="team_lead_work_allocated", to_status=WORKFLOW_IN_PROGRESS, comments=payload.package_code)
    db.flush()
    project = _project(db, project_id)
    for role, user_id in (("production", payload.production_user_id), ("qc", payload.qc_user_id), ("qa", payload.qa_user_id)):
        create_global_notification(
            db,
            event_type="workflow.work.assigned",
            title=f"New {role.upper()} work: {payload.package_code}",
            message=(
                f"Project ID {project.project_code} · Client ID {_client_code(project) or 'Not recorded'} · "
                f"Area {payload.area_name} · Code {payload.package_code} · {payload.quantity} {payload.quantity_unit} · Target {payload.target_date.isoformat()}."
            ),
            category="system",
            target_url="/ortho",
            recipient_user_ids=[user_id],
        )
    db.flush()
    return package


def email_work_allocation(db: Session, *, work_package_id: int) -> None:
    package = db.get(OrthoWorkPackage, work_package_id)
    if package is None:
        return
    project = _project(db, package.project_id)
    for role, user_id in (("Production", package.production_user_id), ("QC", package.qc_user_id), ("QA", package.qa_user_id)):
        if not user_id:
            continue
        user = db.get(User, user_id)
        if user is None:
            continue
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] New {role} work - {package.package_code}",
            body=(
                f"Hello {user.full_name},\n\n"
                "New work has been assigned to you.\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Role: {role}\n"
                f"Area: {package.package_name}\n"
                f"Code: {package.package_code}\n"
                f"Assigned Quantity: {package.area} {package.area_unit}\n"
                f"Target Date: {package.target_date.isoformat() if package.target_date else 'Not recorded'}\n\n"
                f"Instructions: {package.instructions or 'Not recorded'}\n\n"
                f"ERP Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Team Lead",
        )


def _daily_totals(package: OrthoWorkPackage) -> tuple[Decimal, int]:
    quantity = sum((row.achieved_area or Decimal("0")) for row in package.daily_updates)
    files = sum(int(row.files_completed or 0) for row in package.daily_updates)
    return quantity, files


def _package_query():
    return select(OrthoWorkPackage).options(
        selectinload(OrthoWorkPackage.daily_updates),
        selectinload(OrthoWorkPackage.reviews),
        selectinload(OrthoWorkPackage.sessions),
    )


def package_by_id(db: Session, work_package_id: int) -> OrthoWorkPackage:
    package = db.scalar(_package_query().where(OrthoWorkPackage.id == work_package_id))
    if package is None:
        raise ValueError("Work package not found")
    return package


def record_daily_activity(db: Session, *, actor: User, work_package_id: int, payload: WorkflowDailyActivity) -> OrthoDailyUpdate:
    package = package_by_id(db, work_package_id)
    if package.production_user_id != actor.id:
        raise PermissionError("Only the Production employee assigned to this exact task can submit Daily Activity")
    if package.current_stage not in {"not_started", "production", "production_rework"}:
        raise ValueError("Daily Activity is available only while Production work is active")
    current, _ = _daily_totals(package)
    incoming = payload.quantity_completed
    if package.current_stage != "production_rework" and incoming <= 0:
        raise ValueError("Today's completed quantity must be greater than zero")
    target = package.area or Decimal("0")
    new_total = current + incoming
    if package.current_stage != "production_rework" and target > 0 and new_total > target:
        raise ValueError(f"Daily quantity would exceed the assigned quantity. Remaining: {target - current} {package.area_unit}")
    if package.current_stage == "not_started":
        package.current_stage = "production"
        package.production_state = "running"
    progress = Decimal("0") if target <= 0 else min(Decimal("100"), (new_total / target) * Decimal("100"))
    row = OrthoDailyUpdate(
        work_package_id=package.id,
        update_date=payload.update_date or date.today(),
        work_type=payload.work_type,
        achieved_area=incoming,
        progress_percent=progress.quantize(Decimal("0.01")),
        files_completed=payload.files_completed,
        hours_spent=payload.hours_spent,
        status=payload.status,
        blockers=(payload.blockers or "").strip() or None,
        remarks=(payload.remarks or "").strip() or None,
        updated_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def complete_production(db: Session, *, actor: User, work_package_id: int) -> OrthoWorkPackage:
    package = package_by_id(db, work_package_id)
    if package.production_user_id != actor.id:
        raise PermissionError("Only the Production employee assigned to this exact task can complete Production")
    total, _ = _daily_totals(package)
    target = package.area or Decimal("0")
    if package.current_stage != "production_rework" and target > 0 and total < target:
        raise ValueError(f"Complete the remaining {target - total} {package.area_unit} before finishing Production")
    if package.qc_user_id is None:
        raise ValueError("QC employee is not assigned")
    package.production_state = "completed"
    package.production_completed_at = utc_now()
    package.current_stage = "qc"
    package.qc_state = "pending"
    package.qc_submitted_at = utc_now()
    project = _project(db, package.project_id)
    pm = _pm(project)
    recipients = [uid for uid in {package.team_leader_user_id, package.qc_user_id, pm.id if pm else None} if uid]
    create_global_notification(
        db,
        event_type="workflow.production.completed",
        title=f"Production completed: {package.package_code}",
        message=f"Project ID {project.project_code} · Code {package.package_code} is ready for QC.",
        category="system",
        target_url="/ortho",
        recipient_user_ids=recipients,
    )
    db.flush()
    return package


def email_production_completion(db: Session, *, work_package_id: int) -> None:
    package = package_by_id(db, work_package_id)
    project = _project(db, package.project_id)
    pm = _pm(project)
    recipient_ids = {uid for uid in [package.team_leader_user_id, package.qc_user_id, pm.id if pm else None] if uid}
    for user_id in recipient_ids:
        user = db.get(User, user_id)
        if user is None:
            continue
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Production complete - {package.package_code}",
            body=(
                f"Hello {user.full_name},\n\n"
                f"Production is complete for the assigned work item.\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Area: {package.package_name}\n"
                f"Code: {package.package_code}\n"
                "Status: Ready for QC\n\n"
                f"ERP Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Production",
        )


def email_review_transition(db: Session, *, work_package_id: int, kind: str, decision: str) -> None:
    package = package_by_id(db, work_package_id)
    project = _project(db, package.project_id)
    pm = _pm(project)
    kind = kind.lower()
    decision = decision.lower()
    if kind == "qc" and decision == "approve":
        recipient_ids = {package.qa_user_id}
        headline = "QC approved - ready for QA"
    elif kind == "qc":
        recipient_ids = {package.production_user_id, package.team_leader_user_id, pm.id if pm else None}
        headline = "QC rejected - Production rework required"
    elif decision == "approve":
        recipient_ids = {package.team_leader_user_id, pm.id if pm else None}
        headline = "QA approved - ready for Delivery"
    else:
        recipient_ids = {package.production_user_id, package.team_leader_user_id, pm.id if pm else None}
        headline = "QA rejected - Production rework required"
    for user_id in {uid for uid in recipient_ids if uid}:
        user = db.get(User, user_id)
        if user is None:
            continue
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] {headline} - {package.package_code}",
            body=(
                f"Hello {user.full_name},\n\n"
                f"{headline}.\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Area: {package.package_name}\n"
                f"Code: {package.package_code}\n\n"
                f"ERP Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
                "Nakshatech ERP"
            ),
            from_name=f"Nakshatech {kind.upper()}",
        )


def email_delivery_completion(db: Session, *, work_package_id: int) -> None:
    package = package_by_id(db, work_package_id)
    project = _project(db, package.project_id)
    pm = _pm(project)
    for user_id in {uid for uid in [package.team_leader_user_id, pm.id if pm else None] if uid}:
        user = db.get(User, user_id)
        if user is None:
            continue
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Delivered - {package.package_code}",
            body=(
                f"Hello {user.full_name},\n\n"
                f"Project ID: {project.project_code}\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Area: {package.package_name}\n"
                f"Code: {package.package_code}\n"
                "Status: Delivered\n\n"
                f"ERP Dashboard: {settings.app_public_url.rstrip('/')}/ortho\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Delivery",
        )


def _review_attempt(db: Session, package_id: int, kind: str) -> int:
    current = db.scalar(select(func.max(OrthoReview.attempt_no)).where(
        OrthoReview.work_package_id == package_id,
        OrthoReview.review_type == kind,
    ))
    return int(current or 0) + 1


def review_work(db: Session, *, actor: User, work_package_id: int, kind: str, payload: WorkflowReviewRequest) -> OrthoWorkPackage:
    package = package_by_id(db, work_package_id)
    kind = kind.lower()
    if payload.decision == "reject" and not (payload.comments or "").strip():
        raise ValueError(f"{kind.upper()} rejection comments are required for rework")
    if kind == "qc":
        if package.qc_user_id != actor.id:
            raise PermissionError("Only the QC employee assigned to this exact task can record the QC decision")
        if package.current_stage != "qc" or package.qc_state != "pending":
            raise ValueError("This task is not waiting for QC")
    elif kind == "qa":
        if package.qa_user_id != actor.id:
            raise PermissionError("Only the QA employee assigned to this exact task can record the QA decision")
        if package.current_stage != "qa" or package.qa_state != "pending":
            raise ValueError("This task is not waiting for QA")
    else:
        raise ValueError("Review type must be QC or QA")

    db.add(OrthoReview(
        work_package_id=package.id,
        review_type=kind,
        attempt_no=_review_attempt(db, package.id, kind),
        reviewer_user_id=actor.id,
        decision=payload.decision,
        comments=(payload.comments or "").strip() or None,
    ))
    project = _project(db, package.project_id)
    pm = _pm(project)
    if kind == "qc" and payload.decision == "approve":
        package.qc_state = "approved"
        package.current_stage = "qa"
        package.qa_state = "pending"
        package.qa_submitted_at = utc_now()
        recipients = [package.qa_user_id]
        event_type = "workflow.qc.approved"
        title = f"QC approved: {package.package_code}"
        message = f"Project ID {project.project_code} · Code {package.package_code} is ready for QA."
    elif kind == "qc":
        package.qc_state = "rejected"
        package.current_stage = "production_rework"
        package.production_state = "rework_required"
        package.rework_source = "qc"
        recipients = [package.production_user_id, package.team_leader_user_id, pm.id if pm else None]
        event_type = "workflow.qc.rejected"
        title = f"QC rework required: {package.package_code}"
        message = f"Project ID {project.project_code} · Code {package.package_code} returned to Production. {payload.comments or ''}".strip()
    elif payload.decision == "approve":
        package.qa_state = "approved"
        package.current_stage = "delivery_ready"
        package.delivery_ready_at = utc_now()
        package.rework_source = None
        recipients = [package.team_leader_user_id, pm.id if pm else None]
        event_type = "workflow.qa.approved"
        title = f"Ready for delivery: {package.package_code}"
        message = f"Project ID {project.project_code} · Code {package.package_code} passed QA and is Ready for Delivery."
    else:
        package.qa_state = "rejected"
        package.current_stage = "production_rework"
        package.production_state = "rework_required"
        package.rework_source = "qa"
        recipients = [package.production_user_id, package.team_leader_user_id, pm.id if pm else None]
        event_type = "workflow.qa.rejected"
        title = f"QA rework required: {package.package_code}"
        message = f"Project ID {project.project_code} · Code {package.package_code} returned to Production. {payload.comments or ''}".strip()
    create_global_notification(
        db,
        event_type=event_type,
        title=title,
        message=message,
        category="system",
        target_url="/ortho",
        recipient_user_ids=[uid for uid in recipients if uid],
    )
    db.flush()
    return package


def mark_delivered(db: Session, *, actor: User, work_package_id: int, payload: WorkflowDeliveryRequest) -> OrthoWorkPackage:
    package = package_by_id(db, work_package_id)
    project = _project(db, package.project_id)
    if not (_is_pm(project, actor.id) or package.team_leader_user_id == actor.id):
        raise PermissionError("Only the Team Lead or Project Manager can record Delivery")
    if package.current_stage != "delivery_ready" or package.qa_state != "approved":
        raise ValueError("QA must approve the task before Delivery")
    package.current_stage = "delivered"
    package.delivered_at = utc_now()
    pm = _pm(project)
    create_global_notification(
        db,
        event_type="workflow.delivery.completed",
        title=f"Delivered: {package.package_code}",
        message=f"Project ID {project.project_code} · Code {package.package_code} has been delivered.",
        category="system",
        target_url="/ortho",
        recipient_user_ids=[uid for uid in {package.team_leader_user_id, pm.id if pm else None} if uid],
    )
    db.flush()
    return package


def operational_complete(db: Session, *, actor: User, project_id: int, payload: WorkflowOperationalCompletion) -> ProjectWorkflow:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if not _is_pm(project, actor.id):
        raise PermissionError("Only the BD-assigned Project Manager can confirm Operational Completion")
    packages = list(db.scalars(select(OrthoWorkPackage).where(OrthoWorkPackage.project_id == project_id)).all())
    if not packages:
        raise ValueError("Create and complete at least one work allocation before Project Completion")
    blocking = [pkg.package_code for pkg in packages if pkg.current_stage != "delivered"]
    if blocking:
        raise ValueError("All assigned work must be delivered before Project Completion: " + ", ".join(blocking[:10]))
    workflow.operational_completed_at = utc_now()
    workflow.completion_date = payload.completion_date
    workflow.final_delivery_reference = (payload.final_delivery_reference or "").strip() or None
    workflow.completion_remarks = (payload.remarks or "").strip() or None
    _event(db, workflow=workflow, actor=actor, event_type="pm_operational_completion", to_status=WORKFLOW_FINANCE_CLOSURE_PENDING, comments=payload.remarks)
    if project.master_profile:
        project.master_profile.project_status = "completed"
        project.master_profile.updated_by_id = actor.id
        project.master_profile.updated_at = utc_now()
    project.is_active = False
    profile = db.get(OrthoProjectProfile, project_id)
    if profile:
        profile.status = "completed"
        profile.final_delivery_at = workflow.operational_completed_at
        profile.final_delivery_by_id = actor.id
        profile.final_delivery_remarks = workflow.completion_remarks
    create_global_notification(
        db,
        event_type="workflow.project.operational_completed",
        title=f"Operational completion: {project.project_code}",
        message=f"Project ID {project.project_code} has completed operational delivery and is ready for Finance Closure.",
        category="approval",
        target_url="/finance",
        recipient_roles=[FINANCE_ROLE],
    )
    create_global_notification(
        db,
        event_type="workflow.project.operational_completed_bd",
        title=f"Project completed: {project.project_code}",
        message=f"Project ID {project.project_code} has completed operational delivery. Finance Closure is pending.",
        category="system",
        target_url="/bd",
        recipient_user_ids=[workflow.bd_owner_user_id],
    )
    db.flush()
    return workflow


def email_operational_completion(db: Session, *, project_id: int) -> None:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    recipients = resolve_recipient_users(db, recipient_roles=[FINANCE_ROLE])
    owner = db.get(User, workflow.bd_owner_user_id)
    if owner:
        recipients = [*recipients, owner]
    seen: set[int] = set()
    for user in recipients:
        if user.id in seen:
            continue
        seen.add(user.id)
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Operational completion",
            body=(
                f"Hello {user.full_name},\n\n"
                f"Project ID {project.project_code} has completed operational delivery.\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Completion Date: {workflow.completion_date.isoformat() if workflow.completion_date else 'Not recorded'}\n"
                f"Delivery Reference: {workflow.final_delivery_reference or 'Not recorded'}\n\n"
                "Finance Closure is now pending.\n"
                f"ERP: {settings.app_public_url.rstrip('/')}/finance\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Operations",
        )


def finance_close_project(db: Session, *, actor: User, project_id: int, payload: WorkflowFinanceClosure) -> ProjectWorkflow:
    workflow = _workflow(db, project_id)
    if workflow.status != WORKFLOW_FINANCE_CLOSURE_PENDING:
        raise ValueError("Operational Completion is required before Finance Closure")
    project = _project(db, project_id)
    workflow.finance_closed_at = utc_now()
    workflow.finance_closure_remarks = payload.remarks.strip()
    _event(db, workflow=workflow, actor=actor, event_type="finance_closed_project", to_status=WORKFLOW_CLOSED, comments=payload.remarks)
    if project.master_profile:
        project.master_profile.project_status = "completed"
        project.master_profile.updated_by_id = actor.id
        project.master_profile.updated_at = utc_now()
    project.is_active = False
    profile = db.get(OrthoProjectProfile, project_id)
    if profile:
        profile.status = "closed"
    pm = _pm(project)
    recipients = [workflow.bd_owner_user_id]
    if pm:
        recipients.append(pm.id)
    create_global_notification(
        db,
        event_type="workflow.project.closed",
        title=f"Project closed: {project.project_code}",
        message=f"Finance Closure is complete for Project ID {project.project_code}.",
        category="system",
        target_url="/bd",
        recipient_user_ids=recipients,
    )
    db.flush()
    return workflow


def email_finance_closure(db: Session, *, project_id: int) -> None:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    recipients: list[User] = []
    owner = db.get(User, workflow.bd_owner_user_id)
    pm = _pm(project)
    if owner is not None:
        recipients.append(owner)
    if pm is not None and all(existing.id != pm.id for existing in recipients):
        recipients.append(pm)
    for user in recipients:
        _safe_send_email(
            recipient=user.email,
            subject=f"[{project.project_code}] Finance Closure complete",
            body=(
                f"Hello {user.full_name},\n\n"
                f"Finance Closure is complete for Project ID {project.project_code}.\n"
                f"Client ID: {_client_code(project) or 'Not recorded'}\n"
                f"Closure Remarks: {workflow.finance_closure_remarks or 'Not recorded'}\n\n"
                "Final Status: CLOSED\n\n"
                f"ERP: {settings.app_public_url.rstrip('/')}\n\n"
                "Nakshatech ERP"
            ),
            from_name="Nakshatech Finance",
        )


def _member_map(db: Session, project_id: int) -> list[dict]:
    rows = list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.member_role.in_(TEAM_ROLES),
        OrthoProjectMember.is_active.is_(True),
    ).order_by(OrthoProjectMember.member_role.asc(), OrthoProjectMember.id.asc())).all())
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({row.user_id for row in rows}))).all()} if rows else {}
    return [
        {
            "user_id": row.user_id,
            "employee_id": users[row.user_id].employee_id if row.user_id in users else None,
            "full_name": users[row.user_id].full_name if row.user_id in users else None,
            "email": users[row.user_id].email if row.user_id in users else None,
            "member_role": row.member_role,
        }
        for row in rows
    ]


def _package_payload(db: Session, package: OrthoWorkPackage, *, viewer: User, viewer_is_pm: bool, viewer_is_tl: bool) -> dict:
    total, files = _daily_totals(package)
    target = package.area or Decimal("0")
    remaining = max(Decimal("0"), target - total)
    progress = 0.0 if target <= 0 else min(100.0, float((total / target) * Decimal("100")))
    my_roles = []
    if package.team_leader_user_id == viewer.id:
        my_roles.append("team_leader")
    if package.production_user_id == viewer.id:
        my_roles.append("production")
    if package.qc_user_id == viewer.id:
        my_roles.append("qc")
    if package.qa_user_id == viewer.id:
        my_roles.append("qa")

    updates = package.daily_updates
    if not (viewer_is_pm or viewer_is_tl):
        updates = [row for row in updates if row.updated_by_id == viewer.id]
    payload = {
        "id": package.id,
        "package_code": package.package_code,
        "area_name": package.package_name,
        "quantity": float(package.area) if package.area is not None else None,
        "quantity_unit": package.area_unit,
        "target_date": package.target_date.isoformat() if package.target_date else None,
        "instructions": package.instructions,
        "current_stage": package.current_stage,
        "production_state": package.production_state,
        "qc_state": package.qc_state,
        "qa_state": package.qa_state,
        "rework_source": package.rework_source,
        "cumulative_completed": float(total),
        "remaining_quantity": float(remaining),
        "progress_percent": round(progress, 2),
        "files_completed": files,
        "my_roles": my_roles,
        "can_daily_activity": package.production_user_id == viewer.id and package.current_stage in {"not_started", "production", "production_rework"},
        "can_complete_production": package.production_user_id == viewer.id and package.current_stage in {"not_started", "production", "production_rework"},
        "can_qc": package.qc_user_id == viewer.id and package.current_stage == "qc" and package.qc_state == "pending",
        "can_qa": package.qa_user_id == viewer.id and package.current_stage == "qa" and package.qa_state == "pending",
        "can_deliver": (viewer_is_pm or package.team_leader_user_id == viewer.id) and package.current_stage == "delivery_ready",
        "daily_updates": [
            {
                "id": row.id,
                "update_date": row.update_date.isoformat(),
                "work_type": row.work_type,
                "quantity_completed": float(row.achieved_area) if row.achieved_area is not None else 0.0,
                "progress_percent": float(row.progress_percent) if row.progress_percent is not None else None,
                "files_completed": int(row.files_completed or 0),
                "hours_spent": float(row.hours_spent) if row.hours_spent is not None else None,
                "status": row.status,
                "blockers": row.blockers,
                "remarks": row.remarks,
                "updated_by_id": row.updated_by_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in updates
        ],
        "review_history": [
            {
                "review_type": row.review_type,
                "attempt_no": row.attempt_no,
                "decision": row.decision,
                "comments": row.comments,
                "created_at": row.created_at.isoformat(),
            }
            for row in package.reviews
        ],
    }
    if viewer_is_pm or viewer_is_tl:
        user_ids = {uid for uid in [package.team_leader_user_id, package.production_user_id, package.qc_user_id, package.qa_user_id] if uid}
        users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
        payload["assignments"] = {
            "team_leader": _user_min(users.get(package.team_leader_user_id)),
            "production": _user_min(users.get(package.production_user_id)),
            "qc": _user_min(users.get(package.qc_user_id)),
            "qa": _user_min(users.get(package.qa_user_id)),
        }
    return payload


def _user_min(user: User | None) -> dict | None:
    if user is None:
        return None
    return {"id": user.id, "full_name": user.full_name, "email": user.email, "employee_id": user.employee_id}


def ortho_dashboard(db: Session, *, actor: User, role: str) -> dict:
    project_ids: set[int] = set()
    if role == ORTHO_ROLE:
        project_ids.update(int(v) for v in db.scalars(select(FinanceProjectMasterProfile.project_id).where(
            FinanceProjectMasterProfile.project_manager_id == actor.id,
        )).all())
    if role == EMPLOYEE_ROLE:
        project_ids.update(int(v) for v in db.scalars(select(OrthoProjectMember.project_id).where(
            OrthoProjectMember.user_id == actor.id,
            OrthoProjectMember.member_role.in_(TEAM_ROLES),
            OrthoProjectMember.is_active.is_(True),
        )).all())
    if role in {ADMIN_ROLE, MANAGEMENT_ROLE}:
        project_ids.update(int(v) for v in db.scalars(select(ProjectWorkflow.project_id)).all())

    if not project_ids:
        return {"viewer_mode": "participant" if role == EMPLOYEE_ROLE else "project_manager", "projects": [], "employees": []}

    projects = list(db.scalars(_project_query().where(FinanceProject.id.in_(project_ids)).order_by(FinanceProject.updated_at.desc())).unique().all())
    workflows = {row.project_id: row for row in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()}
    result = []
    for project in projects:
        workflow = workflows.get(project.id)
        if workflow is None or workflow.status in {WORKFLOW_DRAFT, WORKFLOW_PENDING_FINANCE, WORKFLOW_FINANCE_RETURNED}:
            continue
        viewer_is_pm = _is_pm(project, actor.id)
        roles = _member_roles(db, project_id=project.id, user_id=actor.id)
        viewer_is_tl = "team_leader" in roles
        packages = list(db.scalars(_package_query().where(OrthoWorkPackage.project_id == project.id).order_by(OrthoWorkPackage.id.asc())).unique().all())
        if not (viewer_is_pm or role in {ADMIN_ROLE, MANAGEMENT_ROLE}):
            packages = [pkg for pkg in packages if actor.id in {pkg.team_leader_user_id, pkg.production_user_id, pkg.qc_user_id, pkg.qa_user_id}]
        package_payloads = [_package_payload(db, pkg, viewer=actor, viewer_is_pm=viewer_is_pm or role in {ADMIN_ROLE, MANAGEMENT_ROLE}, viewer_is_tl=viewer_is_tl) for pkg in packages]
        summary = {
            "packages": len(package_payloads),
            "production": sum(1 for p in package_payloads if p["current_stage"] in {"not_started", "production", "production_rework"}),
            "qc": sum(1 for p in package_payloads if p["current_stage"] == "qc"),
            "qa": sum(1 for p in package_payloads if p["current_stage"] == "qa"),
            "delivery_ready": sum(1 for p in package_payloads if p["current_stage"] == "delivery_ready"),
            "delivered": sum(1 for p in package_payloads if p["current_stage"] == "delivered"),
        }
        base = {
            "project_id": project.id,
            "project_code": project.project_code,
            "client_code": _client_code(project),
            "workflow_status": workflow.status,
            "my_roles": ["project_manager"] if viewer_is_pm else sorted(roles),
            "summary": summary,
            "packages": package_payloads,
            "can_manage_team": viewer_is_pm,
            "can_allocate_work": viewer_is_tl,
            "can_complete_project": viewer_is_pm and bool(package_payloads) and all(p["current_stage"] == "delivered" for p in package_payloads),
        }
        if viewer_is_pm or viewer_is_tl or role in {ADMIN_ROLE, MANAGEMENT_ROLE}:
            base.update({
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None,
                "scope_text": workflow.scope_text,
                "quantity": float(workflow.quantity) if workflow.quantity is not None else None,
                "quantity_unit": workflow.quantity_unit,
                "priority": workflow.priority,
                "members": _member_map(db, project.id),
            })
        result.append(base)
    return {
        "viewer_mode": "read_only" if role in {ADMIN_ROLE, MANAGEMENT_ROLE} else ("project_manager" if role == ORTHO_ROLE else "participant"),
        "projects": result,
        "employees": employee_options(db) if role == ORTHO_ROLE and any(p["can_manage_team"] for p in result) else [],
    }
