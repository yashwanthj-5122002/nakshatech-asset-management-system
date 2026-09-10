from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.models import (
    BDOpportunity,
    BDOpportunityEvent,
    OrthoDailyUpdate,
    OrthoDelivery,
    OrthoProjectMember,
    OrthoProjectProfile,
    OrthoReview,
    OrthoWorkPackage,
    OrthoWorkSession,
)
from app.modules.operations.schemas import (
    BDOpportunityCreate,
    BDProjectLink,
    BDStageUpdate,
    OrthoDailyUpdateRequest,
    OrthoDeliveryRequest,
    OrthoMemberUpsert,
    OrthoProjectActivate,
    OrthoReviewRequest,
    OrthoTeamSetup,
    OrthoWorkPackageAssignments,
    OrthoWorkPackageCreate,
)

BD_ROLE = "bd"
ORTHO_ROLE = "ortho"
ADMIN_ROLE = "admin"
MANAGEMENT_ROLE = "management"
FINANCE_ROLE = "finance"
SOFTWARE_TEAM_ROLE = "software_team"
EMPLOYEE_ROLE = "employee"

BD_WRITE_ROLES = {BD_ROLE}
ORTHO_GLOBAL_ROLES = {ORTHO_ROLE}
OVERSIGHT_ROLES = {ADMIN_ROLE, MANAGEMENT_ROLE}

BD_STAGE_ORDER = [
    "opportunity",
    "technical_sample",
    "client_review",
    "revision",
    "accepted",
    "finance_handoff",
    "project_linked",
    "production",
    "delivery_ready",
    "delivered",
    "closed",
]

MEMBER_ROLES = {"project_manager", "team_leader", "production", "qc", "qa"}
PARTICIPANT_MEMBER_ROLES = {"team_leader", "production", "qc", "qa"}


def normalize_role(role: str | None) -> str:
    return (role or "").strip().lower()


def _user_name_map(db: Session, user_ids: Iterable[int | None]) -> dict[int, str]:
    ids = sorted({int(user_id) for user_id in user_ids if user_id})
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.full_name).where(User.id.in_(ids))).all()
    return {int(row.id): row.full_name for row in rows}


def _user_detail_map(db: Session, user_ids: Iterable[int | None]) -> dict[int, dict]:
    ids = sorted({int(user_id) for user_id in user_ids if user_id})
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {
        int(row.id): {
            "id": row.id,
            "full_name": row.full_name,
            "email": row.email,
            "employee_id": row.employee_id,
            "department": row.department,
            "designation": row.designation,
            "role": row.role,
        }
        for row in rows
    }


def _next_code(db: Session, prefix: str, model, column) -> str:
    year = utc_now().year
    stem = f"{prefix}-{year}-"
    existing = db.scalars(select(column).where(column.like(f"{stem}%"))).all()
    numbers: list[int] = []
    for value in existing:
        try:
            numbers.append(int(str(value).rsplit("-", 1)[1]))
        except (TypeError, ValueError, IndexError):
            continue
    return f"{stem}{(max(numbers, default=0) + 1):04d}"


def resolve_finance_project(db: Session, *, project_id: int | None = None, project_code: str | None = None) -> FinanceProject:
    project: FinanceProject | None = None
    if project_id:
        project = db.get(FinanceProject, project_id)
    elif project_code:
        project = db.scalar(select(FinanceProject).where(func.lower(FinanceProject.project_code) == project_code.strip().lower()))
    if project is None:
        raise ValueError("Finance Project Master project was not found")
    return project


def project_lifecycle_status(project: FinanceProject) -> str:
    profile = project.master_profile
    if profile and profile.project_status:
        return profile.project_status.strip().lower()
    return "active" if project.is_active else "inactive"


def finance_project_payload(project: FinanceProject) -> dict:
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "client_id": project.client_id,
        "client_name": project.client.client_name if project.client else project.client_name,
        "start_date": project.start_date.isoformat() if project.start_date else None,
        "end_date": project.end_date.isoformat() if project.end_date else None,
        "project_status": project_lifecycle_status(project),
        "project_manager_id": project.master_profile.project_manager_id if project.master_profile else None,
        "reporting_manager_id": project.master_profile.reporting_manager_id if project.master_profile else None,
    }


def finance_project_options(db: Session, *, project_manager_id: int | None = None) -> list[dict]:
    query = (
        select(FinanceProject)
        .options(selectinload(FinanceProject.client), selectinload(FinanceProject.master_profile))
        .order_by(FinanceProject.project_code.asc())
    )
    projects = db.scalars(query).all()
    rows = [finance_project_payload(project) for project in projects]
    if project_manager_id is not None:
        rows = [row for row in rows if row["project_manager_id"] == project_manager_id]
    return rows


def client_options(db: Session) -> list[dict]:
    clients = db.scalars(select(FinanceClient).order_by(FinanceClient.client_code.asc())).all()
    return [
        {"id": row.id, "client_code": row.client_code, "client_name": row.client_name, "is_active": bool(row.is_active)}
        for row in clients
    ]


def bd_opportunity_payload(db: Session, opportunity: BDOpportunity) -> dict:
    project = db.get(FinanceProject, opportunity.linked_project_id) if opportunity.linked_project_id else None
    progress = ortho_project_progress(db, project.id) if project else None
    return {
        "id": opportunity.id,
        "opportunity_code": opportunity.opportunity_code,
        "title": opportunity.title,
        "client_id": opportunity.client_id,
        "client_name": opportunity.client_name_snapshot,
        "requirement": opportunity.requirement,
        "service_type": opportunity.service_type,
        "priority": opportunity.priority,
        "stage": opportunity.stage,
        "technical_sample_notes": opportunity.technical_sample_notes,
        "client_feedback": opportunity.client_feedback,
        "expected_value": float(opportunity.expected_value) if opportunity.expected_value is not None else None,
        "expected_start_date": opportunity.expected_start_date.isoformat() if opportunity.expected_start_date else None,
        "expected_delivery_date": opportunity.expected_delivery_date.isoformat() if opportunity.expected_delivery_date else None,
        "owner_user_id": opportunity.owner_user_id,
        "linked_project": finance_project_payload(project) if project else None,
        "production_progress": progress,
        "accepted_at": opportunity.accepted_at.isoformat() if opportunity.accepted_at else None,
        "finance_handoff_at": opportunity.finance_handoff_at.isoformat() if opportunity.finance_handoff_at else None,
        "linked_at": opportunity.linked_at.isoformat() if opportunity.linked_at else None,
        "created_at": opportunity.created_at.isoformat(),
        "updated_at": opportunity.updated_at.isoformat(),
        "events": [
            {
                "id": event.id,
                "action": event.action,
                "from_stage": event.from_stage,
                "to_stage": event.to_stage,
                "comments": event.comments,
                "actor_user_id": event.actor_user_id,
                "created_at": event.created_at.isoformat(),
            }
            for event in opportunity.events
        ],
    }


def create_bd_opportunity(db: Session, *, actor: User, payload: BDOpportunityCreate) -> BDOpportunity:
    client: FinanceClient | None = None
    client_name = (payload.client_name or "").strip() or None
    if payload.client_id:
        client = db.get(FinanceClient, payload.client_id)
        if client is None:
            raise ValueError("Selected client was not found in Client Master")
        client_name = client.client_name
    row = BDOpportunity(
        opportunity_code=_next_code(db, "BD", BDOpportunity, BDOpportunity.opportunity_code),
        title=payload.title.strip(),
        client_id=client.id if client else None,
        client_name_snapshot=client_name,
        requirement=payload.requirement.strip(),
        service_type=payload.service_type.strip().lower(),
        priority=payload.priority,
        stage="opportunity",
        expected_value=payload.expected_value,
        expected_start_date=payload.expected_start_date,
        expected_delivery_date=payload.expected_delivery_date,
        owner_user_id=actor.id,
    )
    db.add(row)
    db.flush()
    db.add(BDOpportunityEvent(
        opportunity_id=row.id,
        action="created",
        from_stage=None,
        to_stage="opportunity",
        comments=None,
        actor_user_id=actor.id,
    ))
    db.flush()
    return row


def update_bd_stage(db: Session, *, opportunity: BDOpportunity, actor: User, payload: BDStageUpdate) -> BDOpportunity:
    old = opportunity.stage
    new = payload.stage
    if old == "closed" and new != "closed":
        raise ValueError("Closed opportunities cannot be reopened from this screen")
    if new not in BD_STAGE_ORDER:
        raise ValueError("Unsupported BD stage")
    if new in {"project_linked", "production", "delivery_ready", "delivered"}:
        raise ValueError("Project-linked Production, Delivery Ready and Delivered stages are controlled by the Ortho workflow, not by BD")
    opportunity.stage = new
    if payload.technical_sample_notes is not None:
        opportunity.technical_sample_notes = payload.technical_sample_notes.strip() or None
    if payload.client_feedback is not None:
        opportunity.client_feedback = payload.client_feedback.strip() or None
    now = utc_now()
    if new == "accepted" and opportunity.accepted_at is None:
        opportunity.accepted_at = now
    if new == "finance_handoff" and opportunity.finance_handoff_at is None:
        opportunity.finance_handoff_at = now
    db.add(BDOpportunityEvent(
        opportunity_id=opportunity.id,
        action="stage_changed",
        from_stage=old,
        to_stage=new,
        comments=(payload.comments or "").strip() or None,
        actor_user_id=actor.id,
    ))
    db.flush()
    return opportunity


def link_bd_project(db: Session, *, opportunity: BDOpportunity, actor: User, payload: BDProjectLink) -> tuple[BDOpportunity, OrthoProjectProfile]:
    if opportunity.stage not in {"accepted", "finance_handoff", "project_linked", "production", "delivery_ready"}:
        raise ValueError("Client acceptance must be recorded before linking an official Project ID")
    project = resolve_finance_project(db, project_id=payload.project_id, project_code=payload.project_code)
    if project_lifecycle_status(project) not in {"active", "on_hold"}:
        raise ValueError("Only ACTIVE or ON HOLD Finance Project Master projects can be linked")
    existing_link = db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project.id, BDOpportunity.id != opportunity.id))
    if existing_link is not None:
        raise ValueError(f"Project {project.project_code} is already linked to {existing_link.opportunity_code}")
    old = opportunity.stage
    opportunity.linked_project_id = project.id
    opportunity.linked_at = opportunity.linked_at or utc_now()
    opportunity.stage = "project_linked"
    db.add(BDOpportunityEvent(
        opportunity_id=opportunity.id,
        action="finance_project_linked",
        from_stage=old,
        to_stage="project_linked",
        comments=(payload.comments or "").strip() or None,
        actor_user_id=actor.id,
    ))
    profile = db.get(OrthoProjectProfile, project.id)
    if profile is None:
        finance_pm = project.master_profile.project_manager_id if project.master_profile else None
        profile = OrthoProjectProfile(
            project_id=project.id,
            opportunity_id=opportunity.id,
            project_manager_user_id=finance_pm,
            status="active",
            created_by_id=actor.id,
        )
        db.add(profile)
        db.flush()
        if finance_pm:
            db.add(OrthoProjectMember(
                project_id=project.id,
                user_id=finance_pm,
                member_role="project_manager",
                is_active=True,
                assigned_by_id=actor.id,
            ))
    elif profile.opportunity_id is None:
        profile.opportunity_id = opportunity.id
    db.flush()
    return opportunity, profile


def bd_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    role = normalize_role(effective_role)
    query = select(BDOpportunity).options(selectinload(BDOpportunity.events)).order_by(BDOpportunity.updated_at.desc(), BDOpportunity.id.desc())
    if role == BD_ROLE:
        query = query.where(BDOpportunity.owner_user_id == actor.id)
    opportunities = db.scalars(query).unique().all()
    counts = Counter(item.stage for item in opportunities)
    return {
        "viewer_mode": "editor" if role == BD_ROLE else "read_only",
        "summary": {
            "total": len(opportunities),
            "active": sum(1 for item in opportunities if item.stage not in {"delivered", "closed"}),
            "accepted": counts.get("accepted", 0) + counts.get("finance_handoff", 0),
            "linked": sum(1 for item in opportunities if item.linked_project_id is not None),
            "delivery_ready": counts.get("delivery_ready", 0),
            "delivered": counts.get("delivered", 0),
        },
        "opportunities": [bd_opportunity_payload(db, item) for item in opportunities],
        "clients": client_options(db),
        "project_master": finance_project_options(db),
    }


def _profile_with_children(db: Session, project_id: int) -> OrthoProjectProfile | None:
    return db.scalar(
        select(OrthoProjectProfile)
        .options(
            selectinload(OrthoProjectProfile.members),
            selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.sessions),
            selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.reviews),
            selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.daily_updates),
            selectinload(OrthoProjectProfile.deliveries),
        )
        .where(OrthoProjectProfile.project_id == project_id)
    )


def member_roles(db: Session, project_id: int, user_id: int) -> set[str]:
    values = db.scalars(
        select(OrthoProjectMember.member_role).where(
            OrthoProjectMember.project_id == project_id,
            OrthoProjectMember.user_id == user_id,
            OrthoProjectMember.is_active.is_(True),
        )
    ).all()
    return {str(value) for value in values}


def is_effective_pm(db: Session, *, project_id: int, user_id: int) -> bool:
    # Finance Project Master is authoritative whenever it has a PM assignment.
    finance_profile = db.get(FinanceProjectMasterProfile, project_id)
    if finance_profile and finance_profile.project_manager_id is not None:
        return finance_profile.project_manager_id == user_id
    profile = db.get(OrthoProjectProfile, project_id)
    if profile and profile.project_manager_user_id == user_id:
        return True
    return "project_manager" in member_roles(db, project_id, user_id)


def activate_ortho_project(db: Session, *, actor: User, payload: OrthoProjectActivate) -> OrthoProjectProfile:
    project = resolve_finance_project(db, project_id=payload.project_id, project_code=payload.project_code)
    if project_lifecycle_status(project) not in {"active", "on_hold"}:
        raise ValueError("Finance Project Master must be ACTIVE or ON HOLD before Ortho activation")
    existing = db.get(OrthoProjectProfile, project.id)
    if existing:
        if not is_effective_pm(db, project_id=project.id, user_id=actor.id):
            raise PermissionError("Only this project's Ortho Project Manager can update the Ortho project profile")
        if payload.total_area is not None:
            existing.total_area = payload.total_area
        if payload.area_unit:
            existing.area_unit = payload.area_unit.strip()
        if payload.scope_text is not None:
            existing.scope_text = payload.scope_text.strip() or None
        if payload.planned_hours is not None:
            existing.planned_hours = payload.planned_hours
        if payload.target_value is not None:
            existing.target_value = payload.target_value
        return existing
    finance_pm = project.master_profile.project_manager_id if project.master_profile else None
    if finance_pm is None:
        raise ValueError("Finance Project Master must assign the Ortho Project Manager before Ortho activation")
    if finance_pm != actor.id:
        raise PermissionError("Only the Project Manager assigned in Finance Project Master can activate this Ortho project")
    profile = OrthoProjectProfile(
        project_id=project.id,
        opportunity_id=payload.opportunity_id,
        total_area=payload.total_area,
        area_unit=payload.area_unit.strip(),
        scope_text=(payload.scope_text or "").strip() or None,
        planned_hours=payload.planned_hours,
        target_value=payload.target_value,
        project_manager_user_id=finance_pm,
        status="active",
        created_by_id=actor.id,
    )
    db.add(profile)
    db.flush()
    db.add(OrthoProjectMember(
        project_id=project.id,
        user_id=profile.project_manager_user_id or actor.id,
        member_role="project_manager",
        is_active=True,
        assigned_by_id=actor.id,
    ))
    db.flush()
    return profile


def _resolve_assignment_user(db: Session, payload: OrthoMemberUpsert) -> User:
    user: User | None = None
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
    elif payload.employee_email:
        email = payload.employee_email.strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
    else:
        raise ValueError("Type or select the employee email before assigning an Ortho responsibility")
    if user is None or not user.is_active:
        raise ValueError("The employee email must belong to an active ERP user before Ortho access can be assigned")
    if payload.employee_name and payload.employee_name.strip().lower() != user.full_name.strip().lower():
        # Email is authoritative. Keep the ERP account identity instead of storing a second name.
        payload.employee_name = user.full_name
    return user


def upsert_project_member(db: Session, *, project_id: int, actor: User, payload: OrthoMemberUpsert) -> OrthoProjectMember:
    if payload.member_role not in MEMBER_ROLES:
        raise ValueError("Unsupported Ortho project role")
    if payload.member_role == "project_manager":
        raise ValueError("Project Manager is controlled by the existing Finance Project Master and cannot be changed from Ortho")
    if not is_effective_pm(db, project_id=project_id, user_id=actor.id):
        raise PermissionError("Only this project's Ortho Project Manager can change project team roles")
    user = _resolve_assignment_user(db, payload)
    row = db.scalar(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.user_id == user.id,
        OrthoProjectMember.member_role == payload.member_role,
    ))
    if row is None:
        row = OrthoProjectMember(
            project_id=project_id,
            user_id=user.id,
            member_role=payload.member_role,
            is_active=payload.is_active,
            assigned_by_id=actor.id,
        )
        db.add(row)
    else:
        row.is_active = payload.is_active
        row.assigned_by_id = actor.id
    db.flush()
    return row


def configure_project_team(db: Session, *, project_id: int, actor: User, payload: OrthoTeamSetup) -> list[OrthoProjectMember]:
    """Save the four primary Ortho responsibilities independently of email delivery.

    One active primary member is kept for each responsibility. Existing membership rows
    are preserved as inactive history when the PM changes the selected employee. Existing
    work packages receive the new project-team owner only where that package role is still
    unassigned; explicit package assignments are never overwritten here.
    """
    if not is_effective_pm(db, project_id=project_id, user_id=actor.id):
        raise PermissionError("Only this project's Ortho Project Manager can configure the project team")

    role_user_ids = {
        "team_leader": payload.team_leader_user_id,
        "production": payload.production_user_id,
        "qc": payload.qc_user_id,
        "qa": payload.qa_user_id,
    }

    selected_users: dict[str, User] = {}
    for role, user_id in role_user_ids.items():
        user = db.get(User, user_id)
        if user is None or not user.is_active:
            raise ValueError(f"Selected {role.replace('_', ' ')} employee is missing or inactive")
        selected_users[role] = user

    package_role_fields = {
        "team_leader": OrthoWorkPackage.team_leader_user_id,
        "production": OrthoWorkPackage.production_user_id,
        "qc": OrthoWorkPackage.qc_user_id,
        "qa": OrthoWorkPackage.qa_user_id,
    }

    selected_rows: list[OrthoProjectMember] = []
    for role, user in selected_users.items():
        rows = list(db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project_id,
            OrthoProjectMember.member_role == role,
        )).all())
        role_field = package_role_fields[role]
        referenced_ids = {int(value) for value in db.scalars(select(role_field).where(
            OrthoWorkPackage.project_id == project_id,
            role_field.is_not(None),
        )).all() if value is not None}
        selected = None
        for row in rows:
            if row.user_id == user.id:
                row.is_active = True
                row.assigned_by_id = actor.id
                selected = row
            elif row.is_active and row.user_id not in referenced_ids:
                # Preserve access for an employee who still explicitly owns an existing package.
                row.is_active = False
                row.assigned_by_id = actor.id
        if selected is None:
            selected = OrthoProjectMember(
                project_id=project_id,
                user_id=user.id,
                member_role=role,
                is_active=True,
                assigned_by_id=actor.id,
            )
            db.add(selected)
        selected_rows.append(selected)

    if payload.apply_to_unassigned_packages:
        packages = list(db.scalars(select(OrthoWorkPackage).where(
            OrthoWorkPackage.project_id == project_id
        )).all())
        for package in packages:
            if package.team_leader_user_id is None:
                package.team_leader_user_id = selected_users["team_leader"].id
            if package.production_user_id is None:
                package.production_user_id = selected_users["production"].id
            if package.qc_user_id is None:
                package.qc_user_id = selected_users["qc"].id
            if package.qa_user_id is None:
                package.qa_user_id = selected_users["qa"].id

    db.flush()
    return selected_rows


def active_project_team_members(db: Session, *, project_id: int) -> list[OrthoProjectMember]:
    return list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.member_role.in_(PARTICIPANT_MEMBER_ROLES),
        OrthoProjectMember.is_active.is_(True),
    ).order_by(OrthoProjectMember.id.asc())).all())


def send_ortho_assignment_email(db: Session, *, project_id: int, member: OrthoProjectMember) -> None:
    if not member.is_active:
        return
    project = db.scalar(
        select(FinanceProject)
        .options(selectinload(FinanceProject.client), selectinload(FinanceProject.master_profile))
        .where(FinanceProject.id == project_id)
    )
    if project is None:
        raise ValueError("Finance Project Master project was not found for assignment email")
    assignee = db.get(User, member.user_id)
    if assignee is None or not assignee.is_active:
        raise ValueError("Assigned employee is missing or inactive")
    pm_id = project.master_profile.project_manager_id if project.master_profile else None
    pm = db.get(User, pm_id) if pm_id else None
    profile = db.get(OrthoProjectProfile, project_id)
    role_label = member.member_role.replace("_", " ").title()
    role_instructions = {
        "team_leader": "Open the Ortho dashboard and submit the daily project/work-package update: achieved area, progress %, hours, blockers and remarks.",
        "production": "Open the Ortho dashboard for your assigned package and update Production Start / Pause / Resume / Complete, then submit completed work to QC.",
        "qc": "Open the Ortho dashboard when work reaches the QC queue and record Approve or Reject with your QC remarks.",
        "qa": "Open the Ortho dashboard when work reaches the QA queue and record Approve or Reject with your QA remarks.",
    }
    dashboard_url = f"{settings.app_public_url.rstrip('/')}/ortho"
    subject = f"[{project.project_code}] Ortho/LiDAR assignment - {role_label}"
    body = (
        f"Hello {assignee.full_name},\n\n"
        f"You have been assigned to the following NakshaTech Ortho/LiDAR project.\n\n"
        f"Project ID: {project.project_code}\n"
        f"Project Name: {project.project_name}\n"
        f"Client: {(project.client.client_name if project.client else project.client_name) or 'Not specified'}\n"
        f"Role / Responsibility: {role_label}\n"
        f"Project Manager: {(pm.full_name if pm else 'Not assigned')}\n"
        f"Project Manager Email: {(pm.email if pm else 'Not assigned')}\n"
        f"Start Date: {project.start_date.isoformat() if project.start_date else 'Not specified'}\n"
        f"End Date: {project.end_date.isoformat() if project.end_date else 'Not specified'}\n"
        f"Scope: {(profile.scope_text if profile and profile.scope_text else 'See the project/work-package details in ERP.')}\n\n"
        f"Your update responsibility:\n{role_instructions.get(member.member_role, 'Open the Ortho dashboard and review your assigned work.')}\n\n"
        f"ERP Ortho Dashboard: {dashboard_url}\n"
        f"Use your existing NakshaTech employee login. The Project Manager can also update and monitor every stage.\n\n"
        f"NakshaTech ERP"
    )
    send_email(
        recipient=assignee.email,
        subject=subject,
        body=body,
        from_name="NakshaTech Ortho / LiDAR",
    )



def _ensure_assignment_role(db: Session, *, project_id: int, user_id: int | None, role: str) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ValueError(f"Assigned {role.replace('_', ' ')} user is missing or inactive")
    existing = db.scalar(select(OrthoProjectMember.id).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.user_id == user_id,
        OrthoProjectMember.member_role == role,
        OrthoProjectMember.is_active.is_(True),
    ))
    if existing is None:
        raise ValueError(f"Assign {user.full_name} the {role.replace('_', ' ')} project role before assigning this work package")


def create_work_package(db: Session, *, project_id: int, actor: User, payload: OrthoWorkPackageCreate) -> OrthoWorkPackage:
    if not is_effective_pm(db, project_id=project_id, user_id=actor.id):
        raise PermissionError("Only this project's Ortho Project Manager can create work packages")
    profile = db.get(OrthoProjectProfile, project_id)
    if profile is None:
        raise ValueError("Ortho project profile not found")
    for user_id, role in [
        (payload.team_leader_user_id, "team_leader"),
        (payload.production_user_id, "production"),
        (payload.qc_user_id, "qc"),
        (payload.qa_user_id, "qa"),
    ]:
        _ensure_assignment_role(db, project_id=project_id, user_id=user_id, role=role)
    row = OrthoWorkPackage(
        project_id=project_id,
        package_code=payload.package_code,
        package_name=payload.package_name,
        area=payload.area,
        area_unit=payload.area_unit,
        target_hours=payload.target_hours,
        current_stage="not_started",
        production_state="not_started",
        team_leader_user_id=payload.team_leader_user_id,
        production_user_id=payload.production_user_id,
        qc_user_id=payload.qc_user_id,
        qa_user_id=payload.qa_user_id,
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def update_package_assignments(db: Session, *, work_package: OrthoWorkPackage, actor: User, payload: OrthoWorkPackageAssignments) -> OrthoWorkPackage:
    if not is_effective_pm(db, project_id=work_package.project_id, user_id=actor.id):
        raise PermissionError("Only this project's Ortho Project Manager can update work-package assignments")
    values = {
        "team_leader_user_id": (payload.team_leader_user_id, "team_leader"),
        "production_user_id": (payload.production_user_id, "production"),
        "qc_user_id": (payload.qc_user_id, "qc"),
        "qa_user_id": (payload.qa_user_id, "qa"),
    }
    for attr, (user_id, role) in values.items():
        if user_id is not None:
            _ensure_assignment_role(db, project_id=work_package.project_id, user_id=user_id, role=role)
            setattr(work_package, attr, user_id)
    db.flush()
    return work_package


def _open_session(db: Session, package_id: int, user_id: int) -> OrthoWorkSession | None:
    return db.scalar(select(OrthoWorkSession).where(
        OrthoWorkSession.work_package_id == package_id,
        OrthoWorkSession.user_id == user_id,
        OrthoWorkSession.ended_at.is_(None),
    ).order_by(OrthoWorkSession.id.desc()))


def work_action(db: Session, *, work_package: OrthoWorkPackage, actor: User, action: str) -> OrthoWorkPackage:
    if not (is_effective_pm(db, project_id=work_package.project_id, user_id=actor.id) or work_package.production_user_id == actor.id):
        raise PermissionError("Only the assigned Production employee or this project's Ortho Project Manager can update Production work")
    production_user_id = work_package.production_user_id
    if production_user_id is None:
        raise ValueError("Assign a Production employee before recording Production work")
    if work_package.current_stage not in {"not_started", "production", "production_rework"}:
        raise ValueError("Production timer is not available at the current workflow stage")
    # The assigned Production employee or the Project Manager can operate the
    # timer. Tracked Production time is always attributed to the employee assigned
    # to this work package; audit logs separately preserve the authenticated actor.
    open_session = _open_session(db, work_package.id, production_user_id)
    now = utc_now()
    if action in {"start", "resume"}:
        if open_session is not None:
            raise ValueError("A Production work session is already running")
        if action == "resume" and work_package.production_state not in {"paused", "rework_paused"}:
            raise ValueError("Resume is available only after Pause")
        if action == "start" and work_package.production_state not in {"not_started", "rework_required"}:
            raise ValueError("Start is not available for the current Production state")
        session_type = "rework" if work_package.current_stage == "production_rework" else "production"
        db.add(OrthoWorkSession(work_package_id=work_package.id, user_id=production_user_id, session_type=session_type, started_at=now))
        work_package.current_stage = "production_rework" if session_type == "rework" else "production"
        work_package.production_state = "rework_running" if session_type == "rework" else "running"
    elif action in {"pause", "complete"}:
        if open_session is None:
            raise ValueError("No running Production work session was found")
        open_session.ended_at = now
        open_session.duration_seconds = max(0, int((now - open_session.started_at).total_seconds()))
        open_session.close_reason = action
        if action == "pause":
            work_package.production_state = "rework_paused" if work_package.current_stage == "production_rework" else "paused"
        else:
            work_package.production_state = "completed"
            work_package.production_completed_at = now
    else:
        raise ValueError("Unsupported work action")
    db.flush()
    return work_package


def submit_to_qc(db: Session, *, work_package: OrthoWorkPackage, actor: User) -> OrthoWorkPackage:
    if not (is_effective_pm(db, project_id=work_package.project_id, user_id=actor.id) or work_package.production_user_id == actor.id):
        raise PermissionError("Only the assigned Production employee or this project's Ortho Project Manager can submit work to QC")
    if work_package.production_state != "completed":
        raise ValueError("Complete Production work before submitting to QC")
    if work_package.qc_user_id is None:
        raise ValueError("Assign a QC employee before submitting this package")
    work_package.current_stage = "qc"
    work_package.qc_state = "pending"
    work_package.qa_state = "not_started" if work_package.rework_source == "qa" else work_package.qa_state
    work_package.qc_submitted_at = utc_now()
    db.flush()
    return work_package


def _next_review_attempt(db: Session, work_package_id: int, review_type: str) -> int:
    value = db.scalar(select(func.max(OrthoReview.attempt_no)).where(
        OrthoReview.work_package_id == work_package_id,
        OrthoReview.review_type == review_type,
    ))
    return int(value or 0) + 1


def review_package(db: Session, *, work_package: OrthoWorkPackage, actor: User, review_type: str, payload: OrthoReviewRequest) -> OrthoWorkPackage:
    kind = review_type.lower()
    is_pm = is_effective_pm(db, project_id=work_package.project_id, user_id=actor.id)
    if kind == "qc":
        if not (is_pm or work_package.qc_user_id == actor.id):
            raise PermissionError("Only the assigned QC employee or this project's Ortho Project Manager can record the QC decision")
        if work_package.current_stage != "qc" or work_package.qc_state != "pending":
            raise ValueError("This package is not waiting for QC")
        if work_package.qc_user_id is None:
            raise ValueError("Assign a QC employee before recording the QC decision")
    elif kind == "qa":
        if not (is_pm or work_package.qa_user_id == actor.id):
            raise PermissionError("Only the assigned QA employee or this project's Ortho Project Manager can record the QA decision")
        if work_package.current_stage != "qa" or work_package.qa_state != "pending":
            raise ValueError("This package is not waiting for QA")
        if work_package.qa_user_id is None:
            raise ValueError("Assign a QA employee before recording the QA decision")
    else:
        raise ValueError("Review type must be QC or QA")

    db.add(OrthoReview(
        work_package_id=work_package.id,
        review_type=kind,
        attempt_no=_next_review_attempt(db, work_package.id, kind),
        reviewer_user_id=actor.id,
        decision=payload.decision,
        comments=(payload.comments or "").strip() or None,
    ))
    now = utc_now()
    if kind == "qc":
        if payload.decision == "reject":
            work_package.qc_state = "rejected"
            work_package.current_stage = "production_rework"
            work_package.production_state = "rework_required"
            work_package.rework_source = "qc"
        else:
            if work_package.qa_user_id is None:
                raise ValueError("Assign a QA employee before approving QC")
            work_package.qc_state = "approved"
            work_package.current_stage = "qa"
            work_package.qa_state = "pending"
            work_package.qa_submitted_at = now
    else:
        if payload.decision == "reject":
            work_package.qa_state = "rejected"
            work_package.current_stage = "production_rework"
            work_package.production_state = "rework_required"
            work_package.rework_source = "qa"
        else:
            work_package.qa_state = "approved"
            work_package.current_stage = "delivery_ready"
            work_package.delivery_ready_at = now
            work_package.rework_source = None
    db.flush()
    return work_package


def record_daily_update(db: Session, *, work_package: OrthoWorkPackage, actor: User, payload: OrthoDailyUpdateRequest) -> OrthoDailyUpdate:
    is_pm = is_effective_pm(db, project_id=work_package.project_id, user_id=actor.id)
    if not (is_pm or work_package.team_leader_user_id == actor.id):
        raise PermissionError("Only the assigned Team Leader or this project's Ortho Project Manager can submit the daily update")
    row = OrthoDailyUpdate(
        work_package_id=work_package.id,
        update_date=payload.update_date or date.today(),
        achieved_area=payload.achieved_area,
        progress_percent=payload.progress_percent,
        hours_spent=payload.hours_spent,
        status=payload.status,
        blockers=(payload.blockers or "").strip() or None,
        remarks=(payload.remarks or "").strip() or None,
        updated_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    return row


def package_hours(work_package: OrthoWorkPackage) -> float:
    return round(sum(int(session.duration_seconds or 0) for session in work_package.sessions) / 3600.0, 3)


def package_payload(db: Session, work_package: OrthoWorkPackage, *, viewer: User | None = None) -> dict:
    detail_map = _user_detail_map(db, [
        work_package.team_leader_user_id,
        work_package.production_user_id,
        work_package.qc_user_id,
        work_package.qa_user_id,
        *[item.updated_by_id for item in work_package.daily_updates],
    ])
    current_user_id = viewer.id if viewer else None
    is_pm = bool(current_user_id and is_effective_pm(db, project_id=work_package.project_id, user_id=current_user_id))
    open_session = None
    if current_user_id:
        session_user_id = work_package.production_user_id if is_pm else current_user_id
        if session_user_id:
            open_session = next((session for session in reversed(work_package.sessions) if session.user_id == session_user_id and session.ended_at is None), None)
    permissions = {
        "can_daily_update": bool(is_pm or (current_user_id and work_package.team_leader_user_id == current_user_id)),
        "can_production": bool(is_pm or (current_user_id and work_package.production_user_id == current_user_id)),
        "can_qc": bool(is_pm or (current_user_id and work_package.qc_user_id == current_user_id)),
        "can_qa": bool(is_pm or (current_user_id and work_package.qa_user_id == current_user_id)),
    }
    return {
        "id": work_package.id,
        "project_id": work_package.project_id,
        "package_code": work_package.package_code,
        "package_name": work_package.package_name,
        "area": float(work_package.area) if work_package.area is not None else None,
        "area_unit": work_package.area_unit,
        "target_hours": float(work_package.target_hours) if work_package.target_hours is not None else None,
        "current_stage": work_package.current_stage,
        "production_state": work_package.production_state,
        "qc_state": work_package.qc_state,
        "qa_state": work_package.qa_state,
        "rework_source": work_package.rework_source,
        "team_leader_user_id": work_package.team_leader_user_id,
        "team_leader_name": (detail_map.get(work_package.team_leader_user_id or -1) or {}).get("full_name"),
        "team_leader_email": (detail_map.get(work_package.team_leader_user_id or -1) or {}).get("email"),
        "production_user_id": work_package.production_user_id,
        "production_user_name": (detail_map.get(work_package.production_user_id or -1) or {}).get("full_name"),
        "production_user_email": (detail_map.get(work_package.production_user_id or -1) or {}).get("email"),
        "qc_user_id": work_package.qc_user_id,
        "qc_user_name": (detail_map.get(work_package.qc_user_id or -1) or {}).get("full_name"),
        "qc_user_email": (detail_map.get(work_package.qc_user_id or -1) or {}).get("email"),
        "qa_user_id": work_package.qa_user_id,
        "qa_user_name": (detail_map.get(work_package.qa_user_id or -1) or {}).get("full_name"),
        "qa_user_email": (detail_map.get(work_package.qa_user_id or -1) or {}).get("email"),
        "actual_hours": package_hours(work_package),
        "timer_running_for_viewer": open_session is not None,
        "permissions": permissions,
        "production_completed_at": work_package.production_completed_at.isoformat() if work_package.production_completed_at else None,
        "delivery_ready_at": work_package.delivery_ready_at.isoformat() if work_package.delivery_ready_at else None,
        "delivered_at": work_package.delivered_at.isoformat() if work_package.delivered_at else None,
        "daily_updates": [
            {
                "id": item.id,
                "update_date": item.update_date.isoformat(),
                "achieved_area": float(item.achieved_area) if item.achieved_area is not None else None,
                "progress_percent": float(item.progress_percent) if item.progress_percent is not None else None,
                "hours_spent": float(item.hours_spent) if item.hours_spent is not None else None,
                "status": item.status,
                "blockers": item.blockers,
                "remarks": item.remarks,
                "updated_by_id": item.updated_by_id,
                "updated_by_name": (detail_map.get(item.updated_by_id) or {}).get("full_name"),
                "created_at": item.created_at.isoformat(),
            }
            for item in work_package.daily_updates
        ],
        "review_history": [
            {
                "id": review.id,
                "review_type": review.review_type,
                "attempt_no": review.attempt_no,
                "reviewer_user_id": review.reviewer_user_id,
                "decision": review.decision,
                "comments": review.comments,
                "created_at": review.created_at.isoformat(),
            }
            for review in work_package.reviews
        ],
    }



def ortho_project_progress(db: Session, project_id: int) -> dict | None:
    profile = _profile_with_children(db, project_id)
    if profile is None:
        return None
    packages = profile.work_packages
    total = len(packages)
    stage_counts = Counter(package.current_stage for package in packages)
    complete = sum(1 for package in packages if package.current_stage in {"delivery_ready", "delivered"})
    delivered = sum(1 for package in packages if package.current_stage == "delivered")
    total_hours = round(sum(package_hours(package) for package in packages), 3)
    total_area = float(sum((package.area or Decimal("0")) for package in packages)) if packages else 0.0
    delivered_area = float(sum((package.area or Decimal("0")) for package in packages if package.current_stage == "delivered")) if packages else 0.0
    return {
        "total_packages": total,
        "progress_percent": round((complete / total) * 100.0, 1) if total else 0.0,
        "delivered_packages": delivered,
        "stage_counts": dict(stage_counts),
        "total_hours": total_hours,
        "total_area": round(total_area, 3),
        "delivered_area": round(delivered_area, 3),
        "status": profile.status,
        "final_delivery_at": profile.final_delivery_at.isoformat() if profile.final_delivery_at else None,
    }


def project_payload(db: Session, profile: OrthoProjectProfile, *, viewer: User | None = None) -> dict:
    project = db.scalar(
        select(FinanceProject)
        .options(selectinload(FinanceProject.client), selectinload(FinanceProject.master_profile))
        .where(FinanceProject.id == profile.project_id)
    )
    if project is None:
        raise ValueError("Linked Finance Project Master record no longer exists")
    authoritative_pm_id = project.master_profile.project_manager_id if project.master_profile and project.master_profile.project_manager_id is not None else profile.project_manager_user_id
    user_ids = [authoritative_pm_id]
    user_ids.extend(member.user_id for member in profile.members)
    details = _user_detail_map(db, user_ids)
    viewer_id = viewer.id if viewer else None
    roles = member_roles(db, profile.project_id, viewer_id) if viewer_id else set()
    is_pm = bool(viewer_id and is_effective_pm(db, project_id=profile.project_id, user_id=viewer_id))
    permissions = {
        "project_manager": is_pm,
        "team_leader": is_pm or "team_leader" in roles,
        "production": is_pm or "production" in roles,
        "qc": is_pm or "qc" in roles,
        "qa": is_pm or "qa" in roles,
    }
    return {
        "project": finance_project_payload(project),
        "profile": {
            "project_id": profile.project_id,
            "opportunity_id": profile.opportunity_id,
            "total_area": float(profile.total_area) if profile.total_area is not None else None,
            "area_unit": profile.area_unit,
            "scope_text": profile.scope_text,
            "planned_hours": float(profile.planned_hours) if profile.planned_hours is not None else None,
            "target_value": float(profile.target_value) if profile.target_value is not None else None,
            "project_manager_user_id": authoritative_pm_id,
            "project_manager_name": (details.get(authoritative_pm_id or -1) or {}).get("full_name"),
            "project_manager_email": (details.get(authoritative_pm_id or -1) or {}).get("email"),
            "status": profile.status,
            "final_delivery_at": profile.final_delivery_at.isoformat() if profile.final_delivery_at else None,
            "final_delivery_remarks": profile.final_delivery_remarks,
        },
        "permissions": permissions,
        "progress": ortho_project_progress(db, profile.project_id),
        "members": [
            {
                "id": member.id,
                "user_id": member.user_id,
                "user_name": (details.get(member.user_id) or {}).get("full_name"),
                "user_email": (details.get(member.user_id) or {}).get("email"),
                "employee_id": (details.get(member.user_id) or {}).get("employee_id"),
                "member_role": member.member_role,
                "is_active": bool(member.is_active),
            }
            for member in profile.members
        ],
        "work_packages": [package_payload(db, package, viewer=viewer) for package in profile.work_packages],
    }



def visible_ortho_profiles(db: Session, *, actor: User, effective_role: str) -> list[OrthoProjectProfile]:
    role = normalize_role(effective_role)
    query = select(OrthoProjectProfile).options(
        selectinload(OrthoProjectProfile.members),
        selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.sessions),
        selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.reviews),
        selectinload(OrthoProjectProfile.work_packages).selectinload(OrthoWorkPackage.daily_updates),
        selectinload(OrthoProjectProfile.deliveries),
    ).order_by(OrthoProjectProfile.updated_at.desc(), OrthoProjectProfile.project_id.desc())
    if role == ORTHO_ROLE:
        candidates = db.scalars(query).unique().all()
        return [
            profile
            for profile in candidates
            if is_effective_pm(db, project_id=profile.project_id, user_id=actor.id)
            or bool(member_roles(db, profile.project_id, actor.id) & PARTICIPANT_MEMBER_ROLES)
        ]
    if role == EMPLOYEE_ROLE:
        candidates = db.scalars(query).unique().all()
        return [profile for profile in candidates if bool(member_roles(db, profile.project_id, actor.id) & PARTICIPANT_MEMBER_ROLES)]
    if role in OVERSIGHT_ROLES:
        return db.scalars(query).unique().all()
    return []


def ortho_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    role = normalize_role(effective_role)
    profiles = visible_ortho_profiles(db, actor=actor, effective_role=role)
    projects = [project_payload(db, profile, viewer=actor) for profile in profiles]
    all_packages = [package for project in projects for package in project["work_packages"]]

    # Finance Project Master is authoritative for Ortho PM assignment. A freshly
    # assigned Ortho PM must be able to see and activate Finance projects even
    # before any OrthoProjectProfile exists. V7.0.9 incorrectly gated the
    # project-master list on an already-visible Ortho PM project, creating a
    # circular dependency for first-time assignments. Keep this list server-side
    # filtered so one Ortho PM never receives another PM's Finance projects.
    assigned_finance_projects = finance_project_options(db, project_manager_id=actor.id) if role == ORTHO_ROLE else []
    has_pm_project = any(project["permissions"]["project_manager"] for project in projects)
    can_manage_any_project = has_pm_project or bool(assigned_finance_projects)

    if role in OVERSIGHT_ROLES:
        viewer_mode = "read_only"
    elif role == ORTHO_ROLE and can_manage_any_project:
        viewer_mode = "project_manager"
    elif role in {EMPLOYEE_ROLE, ORTHO_ROLE}:
        viewer_mode = "participant"
    else:
        viewer_mode = "read_only"
    view_permissions = {
        key: any(project["permissions"][key] for project in projects)
        for key in ["project_manager", "team_leader", "production", "qc", "qa"]
    }
    if role == ORTHO_ROLE and can_manage_any_project:
        view_permissions["project_manager"] = True
    if role in OVERSIGHT_ROLES:
        view_permissions = {key: True for key in view_permissions}
    return {
        "viewer_mode": viewer_mode,
        "view_permissions": view_permissions,
        "summary": {
            "projects": len(projects),
            "packages": len(all_packages),
            "production": sum(1 for p in all_packages if p["current_stage"] in {"production", "production_rework", "not_started"}),
            "qc": sum(1 for p in all_packages if p["current_stage"] == "qc"),
            "qa": sum(1 for p in all_packages if p["current_stage"] == "qa"),
            "delivery_ready": sum(1 for p in all_packages if p["current_stage"] == "delivery_ready"),
            "delivered": sum(1 for p in all_packages if p["current_stage"] == "delivered"),
            "total_hours": round(sum(float(p["actual_hours"]) for p in all_packages), 3),
        },
        "projects": projects,
        "project_master": assigned_finance_projects,
        "users": [
            {
                "id": user.id,
                "full_name": user.full_name,
                "email": user.email,
                "employee_id": user.employee_id,
                "department": user.department,
                "designation": user.designation,
                "role": user.role,
                "is_active": bool(user.is_active),
            }
            for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name.asc())).all()
        ] if can_manage_any_project else [],
    }


def get_visible_work_package(db: Session, *, work_package_id: int, actor: User, effective_role: str) -> OrthoWorkPackage | None:
    row = db.scalar(
        select(OrthoWorkPackage)
        .options(
            selectinload(OrthoWorkPackage.sessions),
            selectinload(OrthoWorkPackage.reviews),
            selectinload(OrthoWorkPackage.daily_updates),
        )
        .where(OrthoWorkPackage.id == work_package_id)
    )
    if row is None:
        return None
    role = normalize_role(effective_role)
    if role in OVERSIGHT_ROLES:
        return row
    if role not in {ORTHO_ROLE, EMPLOYEE_ROLE}:
        return None
    if is_effective_pm(db, project_id=row.project_id, user_id=actor.id):
        return row
    if actor.id in {row.team_leader_user_id, row.production_user_id, row.qc_user_id, row.qa_user_id}:
        return row
    if member_roles(db, row.project_id, actor.id) & PARTICIPANT_MEMBER_ROLES:
        return row
    return None



def finalize_delivery(db: Session, *, profile: OrthoProjectProfile, actor: User, payload: OrthoDeliveryRequest) -> OrthoDelivery:
    if not is_effective_pm(db, project_id=profile.project_id, user_id=actor.id):
        raise PermissionError("Only this project's Ortho Project Manager can record Final Delivery")
    full = _profile_with_children(db, profile.project_id)
    if full is None:
        raise ValueError("Ortho project profile not found")
    if not full.work_packages:
        raise ValueError("Create at least one work package before Final Delivery")
    blocking = [package.package_code for package in full.work_packages if package.current_stage != "delivery_ready"]
    if blocking:
        raise ValueError("All work packages must be QA-approved and Delivery Ready before Final Delivery: " + ", ".join(blocking[:8]))
    now = utc_now()
    for package in full.work_packages:
        package.current_stage = "delivered"
        package.delivered_at = now
    full.status = "delivered"
    full.final_delivery_at = now
    full.final_delivery_by_id = actor.id
    full.final_delivery_remarks = (payload.remarks or "").strip() or None
    delivery = OrthoDelivery(
        project_id=full.project_id,
        delivered_by_id=actor.id,
        package_count=len(full.work_packages),
        remarks=(payload.remarks or "").strip() or None,
        delivered_at=now,
    )
    db.add(delivery)
    if full.opportunity_id:
        opportunity = db.get(BDOpportunity, full.opportunity_id)
        if opportunity:
            old = opportunity.stage
            opportunity.stage = "delivered"
            db.add(BDOpportunityEvent(
                opportunity_id=opportunity.id,
                action="final_delivery_received",
                from_stage=old,
                to_stage="delivered",
                comments=(payload.remarks or "").strip() or None,
                actor_user_id=actor.id,
            ))
    db.flush()
    return delivery


def sync_bd_progress_stage(db: Session, project_id: int) -> None:
    opportunity = db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project_id))
    if opportunity is None or opportunity.stage in {"delivered", "closed"}:
        return
    progress = ortho_project_progress(db, project_id)
    if not progress:
        return
    if progress["total_packages"] and progress["progress_percent"] >= 100.0:
        opportunity.stage = "delivery_ready"
    elif progress["total_packages"]:
        opportunity.stage = "production"


def corporate_summary_payload(db: Session) -> dict:
    opportunities = db.scalars(select(BDOpportunity)).all()
    profiles = db.scalars(select(OrthoProjectProfile)).all()
    project_summaries = [ortho_project_progress(db, profile.project_id) for profile in profiles]
    project_summaries = [summary for summary in project_summaries if summary]
    return {
        "bd": {
            "total_opportunities": len(opportunities),
            "active_opportunities": sum(1 for item in opportunities if item.stage not in {"delivered", "closed"}),
            "linked_projects": sum(1 for item in opportunities if item.linked_project_id is not None),
            "delivered": sum(1 for item in opportunities if item.stage == "delivered"),
        },
        "ortho": {
            "projects": len(profiles),
            "active_projects": sum(1 for profile in profiles if profile.status != "delivered"),
            "delivered_projects": sum(1 for profile in profiles if profile.status == "delivered"),
            "total_packages": sum(summary["total_packages"] for summary in project_summaries),
            "delivered_packages": sum(summary["delivered_packages"] for summary in project_summaries),
            "total_hours": round(sum(summary["total_hours"] for summary in project_summaries), 3),
            "total_area": round(sum(summary["total_area"] for summary in project_summaries), 3),
            "delivered_area": round(sum(summary["delivered_area"] for summary in project_summaries), 3),
        },
    }
