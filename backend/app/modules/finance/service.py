from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import html
import logging
import secrets
from typing import Iterable

from sqlalchemy import func, inspect as sa_inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import record_audit, send_email
from app.modules.finance.models import (
    ExpenseClaim,
    ExpenseClaimAttachment,
    ExpenseClaimEvent,
    ExpenseClaimItem,
    ExpenseClaimPayment,
    FinanceClient,
    FinanceClientMasterProfile,
    FinanceProject,
    FinanceProjectAssignment,
    FinanceProjectMasterProfile,
)
from app.modules.finance.schemas import (
    ExpenseClaimCreateRequest,
    FinanceClientCreateRequest,
    FinanceClientProjectCreateRequest,
    FinanceClientProjectUpdateRequest,
    FinanceClientUpdateRequest,
)
from app.modules.notifications.service import create_global_notification

logger = logging.getLogger(__name__)

FINANCE_ROLE = "finance"
EMPLOYEE_ROLE = "employee"
ADMIN_ROLE = "admin"
MANAGEMENT_ROLE = "management"

CLAIM_TYPES = {"advance", "reimbursement", "additional_advance"}
EDITABLE_STATUSES = {"draft", "admin_sent_back", "finance_sent_back"}
VISIBLE_STAFF_ROLES = {ADMIN_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE}

CLAIM_TYPE_LABELS = {
    "advance": "Advance Request",
    "reimbursement": "Reimbursement",
    "additional_advance": "Additional Advance",
}
STATUS_LABELS = {
    "draft": "Draft",
    "submitted": "Pending Admin Verification",
    "admin_approved": "Pending Finance Verification",
    "admin_rejected": "Rejected by Admin",
    "admin_sent_back": "Sent Back by Admin",
    "finance_approved": "Finance Approved / Payment Pending",
    "partially_paid": "Partially Paid",
    "finance_rejected": "Rejected by Finance",
    "finance_sent_back": "Sent Back by Finance",
    "paid": "Paid / Amount Released",
}

LEGACY_FAKE_PROJECT_CODES = {
    "PRJ-2026-001",
    "PRJ-2026-002",
    "PRJ-2026-003",
    "PRJ-2026-004",
    "PRJ-2026-005",
    "PRJ-2026-006",
}

def money(value: float | Decimal | int | str | None) -> Decimal:
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def approved_amount(claim: ExpenseClaim) -> Decimal:
    if claim.finance_approved_amount is not None:
        return money(claim.finance_approved_amount)
    if claim.status in {"finance_approved", "partially_paid", "paid"}:
        return money(claim.total_amount)
    return Decimal("0.00")


def claim_paid_amount(claim: ExpenseClaim) -> Decimal:
    if claim.payments:
        return money(sum((money(payment.amount) for payment in claim.payments), Decimal("0.00")))
    return money(claim.paid_amount)


def remaining_amount(claim: ExpenseClaim) -> Decimal:
    return max(Decimal("0.00"), money(approved_amount(claim) - claim_paid_amount(claim)))


def _locked_claim(db: Session, claim: ExpenseClaim) -> ExpenseClaim:
    locked = db.scalar(select(ExpenseClaim).where(ExpenseClaim.id == claim.id).with_for_update())
    if locked is None:
        raise ValueError("Expense claim no longer exists")
    db.expire(locked, ["payments", "items", "attachments", "events"])
    return locked


def ensure_finance_seed_data(db: Session) -> None:
    """Keep production free of demo projects while retaining deterministic QA fixtures.

    Finance V4 uses Client Management as the authoritative production project
    master. Existing legacy demo projects are made inactive without deletion.
    The pytest suite uses SQLite, so two isolated NT test projects are created
    there only to keep Finance lifecycle regression tests deterministic.
    """
    if engine.url.get_backend_name() == "sqlite":
        client = db.scalar(select(FinanceClient).where(FinanceClient.client_code == "NT1001"))
        if client is None:
            client = FinanceClient(
                client_code="NT1001", client_name="Finance Test Client",
                primary_phone="9000000000", contact_person_name="Test Contact",
                contact_person_phone="9000000001", country="India",
                source_team="bd_team", source_person_name="Test BD User", is_active=True,
            )
            db.add(client); db.flush()
        for number, name in ((1, "Finance Test Project One"), (2, "Finance Test Project Two")):
            code = f"{client.client_code}-P{number}"
            if db.scalar(select(FinanceProject.id).where(FinanceProject.project_code == code)) is None:
                db.add(FinanceProject(
                    project_code=code, project_name=name, client_id=client.id, client_name=client.client_name,
                    project_number=number, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), is_active=True,
                ))
        db.commit()
        return

    # Historical demo codes are inactive by default in production, but once
    # Finance/Admin deliberately manages one through Project Master its explicit
    # lifecycle profile becomes authoritative. This prevents application startup
    # from silently undoing an Activate action for a legacy Project ID such as
    # PRJ-2026-005.
    projects = list(db.scalars(
        select(FinanceProject).where(FinanceProject.project_code.in_(LEGACY_FAKE_PROJECT_CODES))
    ).all())
    project_ids = [project.id for project in projects]
    profiles = {
        profile.project_id: profile
        for profile in (
            db.scalars(
                select(FinanceProjectMasterProfile).where(
                    FinanceProjectMasterProfile.project_id.in_(project_ids)
                )
            ).all()
            if project_ids
            else []
        )
    }

    changed = False
    for project in projects:
        profile = profiles.get(project.id)
        desired_active = bool(profile and profile.project_status == "active")
        if project.is_active != desired_active:
            project.is_active = desired_active
            project.updated_at = utc_now()
            changed = True
    if changed:
        db.commit()


def _client_master_profile(db: Session, client: FinanceClient) -> FinanceClientMasterProfile | None:
    return client.master_profile or db.get(FinanceClientMasterProfile, client.id)


def _project_master_profile(db: Session, project: FinanceProject) -> FinanceProjectMasterProfile | None:
    return project.master_profile or db.get(FinanceProjectMasterProfile, project.id)


def _validate_active_user(db: Session, user_id: int | None, label: str) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.account_status not in {"active", "pending_mfa"}:
        raise ValueError(f"{label} is not an active user")
    return user


def _sync_project_assignments(db: Session, *, project: FinanceProject, actor: User, user_ids: list[int]) -> None:
    requested_ids = set(user_ids or [])
    if requested_ids:
        users = list(db.scalars(select(User).where(User.id.in_(requested_ids))).all())
        by_id = {user.id: user for user in users}
        missing = requested_ids - set(by_id)
        if missing:
            raise ValueError(f"Assigned employee user IDs were not found: {sorted(missing)}")
        invalid = [
            user.full_name for user in users
            if not user.is_active or user.account_status not in {"active", "pending_mfa"} or user.role != EMPLOYEE_ROLE
        ]
        if invalid:
            raise ValueError("Project assignments can include only active Employee accounts: " + ", ".join(sorted(invalid)))

    existing_rows = list(db.scalars(
        select(FinanceProjectAssignment).where(FinanceProjectAssignment.project_id == project.id)
    ).all())
    existing = {assignment.user_id: assignment for assignment in existing_rows}
    for user_id, assignment in existing.items():
        assignment.is_active = user_id in requested_ids
        assignment.assigned_by_id = actor.id
        assignment.updated_at = utc_now()
    for user_id in requested_ids - set(existing):
        db.add(FinanceProjectAssignment(
            project_id=project.id,
            user_id=user_id,
            assigned_by_id=actor.id,
            is_active=True,
        ))
    db.flush()
    db.expire(project, ["assignments"])



def project_is_assigned_to_user(db: Session, *, project_id: int, user_id: int) -> bool:
    return db.scalar(
        select(FinanceProjectAssignment.id).where(
            FinanceProjectAssignment.project_id == project_id,
            FinanceProjectAssignment.user_id == user_id,
            FinanceProjectAssignment.is_active.is_(True),
        ).limit(1)
    ) is not None


def assigned_projects_for_user(db: Session, *, user_id: int) -> list[FinanceProject]:
    rows = list(db.scalars(
        select(FinanceProject)
        .join(FinanceProjectAssignment, FinanceProjectAssignment.project_id == FinanceProject.id)
        .where(
            FinanceProjectAssignment.user_id == user_id,
            FinanceProjectAssignment.is_active.is_(True),
            FinanceProject.is_active.is_(True),
        )
        .order_by(FinanceProject.project_code.asc())
    ).unique().all())
    return [project for project in rows if project_expense_allowed(project)[0]]


def project_master_users(db: Session) -> list[User]:
    return list(db.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.account_status.in_(["active", "pending_mfa"]),
        ).order_by(User.full_name.asc(), User.email.asc())
    ).all())


def list_finance_clients(db: Session) -> list[FinanceClient]:
    return list(db.scalars(select(FinanceClient).order_by(FinanceClient.client_code.asc())).all())


def client_payload(client: FinanceClient) -> dict:
    projects = list(client.projects or [])
    profile = client.master_profile
    return {
        "id": client.id,
        "vendor_code": profile.vendor_code if profile else None,
        "client_type": profile.client_type if profile else "client",
        "import_source": profile.import_source if profile else None,
        "imported_at": profile.imported_at if profile else None,
        "client_code": client.client_code,
        "client_name": client.client_name,
        "primary_phone": client.primary_phone,
        "client_email": client.client_email,
        "contact_person_name": client.contact_person_name,
        "contact_person_phone": None if client.contact_person_phone == "Not provided" else client.contact_person_phone,
        "contact_person_email": profile.contact_person_email if profile else None,
        "task": profile.task if profile else None,
        "bd_name": profile.bd_name if profile else None,
        "address": client.address,
        "description": client.description,
        "country": client.country,
        "gst_number": client.gst_number,
        "source_team": client.source_team,
        "source_person_name": client.source_person_name,
        "is_active": client.is_active,
        "project_count": len(projects),
        "active_project_count": sum(1 for project in projects if project.is_active),
        "created_at": client.created_at,
        "updated_at": client.updated_at,
    }


def create_finance_client(db: Session, *, actor: User, payload: FinanceClientCreateRequest) -> FinanceClient:
    duplicate = db.scalar(select(FinanceClient.id).where(func.lower(FinanceClient.client_code) == payload.client_code.lower()).limit(1))
    if duplicate is not None:
        raise ValueError(f"Client Code {payload.client_code} already exists")
    client = FinanceClient(
        client_code=payload.client_code,
        client_name=payload.client_name,
        primary_phone=payload.primary_phone,
        client_email=payload.client_email,
        contact_person_name=payload.contact_person_name,
        contact_person_phone=payload.contact_person_phone or "Not provided",
        address=payload.address,
        description=payload.description,
        country=payload.country,
        gst_number=payload.gst_number,
        source_team=payload.source_team,
        source_person_name=payload.source_person_name or payload.bd_name or "Not specified",
        is_active=payload.is_active,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    db.add(client)
    try:
        db.flush()
        client.master_profile = FinanceClientMasterProfile(
            client_id=client.id,
            vendor_code=payload.vendor_code,
            client_type=payload.client_type,
            task=payload.task,
            bd_name=payload.bd_name,
            contact_person_email=payload.contact_person_email,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        db.add(client.master_profile)
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"Client Code {payload.client_code} already exists") from exc
    return client


def update_finance_client(db: Session, *, client: FinanceClient, actor: User, payload: FinanceClientUpdateRequest) -> FinanceClient:
    client.client_name = payload.client_name
    client.primary_phone = payload.primary_phone
    client.client_email = payload.client_email
    client.contact_person_name = payload.contact_person_name
    client.contact_person_phone = payload.contact_person_phone or "Not provided"
    client.address = payload.address
    client.description = payload.description
    client.country = payload.country
    client.gst_number = payload.gst_number
    client.source_team = payload.source_team
    client.source_person_name = payload.source_person_name or payload.bd_name or client.source_person_name or "Not specified"
    client.is_active = payload.is_active
    client.updated_by_id = actor.id
    client.updated_at = utc_now()
    profile = client.master_profile or FinanceClientMasterProfile(client_id=client.id, created_by_id=actor.id)
    profile.vendor_code = payload.vendor_code
    profile.client_type = payload.client_type
    profile.task = payload.task
    profile.bd_name = payload.bd_name
    profile.contact_person_email = payload.contact_person_email
    profile.updated_by_id = actor.id
    profile.updated_at = utc_now()
    if client.master_profile is None:
        client.master_profile = profile
        db.add(profile)
    for project in client.projects:
        project.client_name = client.client_name
        project.updated_at = utc_now()
    db.flush()
    return client


def client_projects(db: Session, client_id: int) -> list[FinanceProject]:
    return list(db.scalars(
        select(FinanceProject)
        .where(FinanceProject.client_id == client_id)
        .order_by(FinanceProject.project_code.asc(), FinanceProject.id.asc())
    ).all())


def create_client_project(db: Session, *, client: FinanceClient, actor: User, payload: FinanceClientProjectCreateRequest) -> FinanceProject:
    if not client.is_active:
        raise ValueError("Activate the client before creating a new project")
    duplicate = db.scalar(select(FinanceProject.id).where(func.lower(FinanceProject.project_code) == payload.project_code.lower()).limit(1))
    if duplicate is not None:
        raise ValueError(f"Project Number {payload.project_code} already exists")
    project = FinanceProject(
        project_code=payload.project_code,
        project_name=payload.project_name,
        client_id=client.id,
        client_name=client.client_name,
        project_number=None,
        project_source_team=payload.project_source_team,
        project_source_person_name=payload.project_source_person_name,
        client_awarded_by_name=payload.client_awarded_by_name,
        project_award_date=payload.project_award_date,
        description=payload.description,
        start_date=payload.start_date,
        end_date=payload.end_date,
        is_active=payload.is_active,
        created_by_id=actor.id,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError(f"Project Number {payload.project_code} already exists") from exc
    status = payload.project_status or ("active" if payload.is_active else "inactive")
    manager = _validate_active_user(db, payload.project_manager_id, "Project Manager")
    reporting = _validate_active_user(db, payload.reporting_manager_id, "Reporting Manager")
    profile = FinanceProjectMasterProfile(
        project_id=project.id,
        task=payload.task,
        project_status=status,
        project_manager_id=manager.id if manager else None,
        reporting_manager_id=reporting.id if reporting else None,
        created_by_id=actor.id,
        updated_by_id=actor.id,
    )
    project.master_profile = profile
    db.add(profile)
    project.is_active = status == "active"
    _sync_project_assignments(db, project=project, actor=actor, user_ids=payload.assigned_employee_ids)
    db.flush()
    return project


def update_client_project(db: Session, *, project: FinanceProject, actor: User, payload: FinanceClientProjectUpdateRequest) -> FinanceProject:
    project.project_name = payload.project_name
    project.project_source_team = payload.project_source_team
    project.project_source_person_name = payload.project_source_person_name
    project.client_awarded_by_name = payload.client_awarded_by_name
    project.project_award_date = payload.project_award_date
    project.description = payload.description
    project.start_date = payload.start_date
    project.end_date = payload.end_date
    status = payload.project_status or ("active" if payload.is_active else "inactive")
    project.is_active = status == "active"
    if project.client:
        project.client_name = project.client.client_name
    profile = project.master_profile or FinanceProjectMasterProfile(project_id=project.id, created_by_id=actor.id)
    manager = _validate_active_user(db, payload.project_manager_id, "Project Manager")
    reporting = _validate_active_user(db, payload.reporting_manager_id, "Reporting Manager")
    profile.task = payload.task
    profile.project_status = status
    profile.project_manager_id = manager.id if manager else None
    profile.reporting_manager_id = reporting.id if reporting else None
    profile.updated_by_id = actor.id
    profile.updated_at = utc_now()
    if project.master_profile is None:
        project.master_profile = profile
        db.add(profile)
    _sync_project_assignments(db, project=project, actor=actor, user_ids=payload.assigned_employee_ids)
    project.updated_at = utc_now()
    db.flush()
    return project


def set_project_status(
    db: Session,
    *,
    project: FinanceProject,
    actor: User,
    project_status: str,
) -> FinanceProject:
    """Update project lifecycle independently of Client-Master navigation.

    This intentionally works for legacy projects that have a historical
    client_name but no finance_clients.client_id link. It lets Finance/Admin
    activate or close any Project ID from the global Project Master.
    """
    allowed_statuses = {"active", "on_hold", "completed", "inactive"}
    if project_status not in allowed_statuses:
        raise ValueError("Unsupported project status")

    profile = project.master_profile
    if profile is None:
        profile = FinanceProjectMasterProfile(
            project_id=project.id,
            project_status=project_status,
            created_by_id=actor.id,
            updated_by_id=actor.id,
        )
        project.master_profile = profile
        db.add(profile)
    else:
        profile.project_status = project_status
        profile.updated_by_id = actor.id
        profile.updated_at = utc_now()

    project.is_active = project_status == "active"
    project.updated_at = utc_now()
    db.flush()
    return project


_PROJECT_MASTER_TABLE_CACHE_KEY = "_finance_project_master_table_available"


def _project_status_for_claim_rules(project: FinanceProject) -> str:
    """Return the authoritative lifecycle status without breaking legacy schemas.

    The V6 Project Master lifecycle lives in ``finance_project_master_profiles``.
    After ``Session.refresh(project)`` SQLAlchemy expires relationships, so relying
    only on ``project.__dict__["master_profile"]`` incorrectly collapses
    ``completed`` and ``on_hold`` projects to generic ``inactive``.

    Some older isolated Travel/KM tests intentionally create only the legacy
    ``finance_projects`` table, so blindly lazy-loading the relationship would
    query a table that does not exist in those compatibility databases. We first
    detect the additive table once per Session, then read the profile only when
    the legacy boolean is false and the richer status is actually needed.
    """
    loaded_profile = project.__dict__.get("master_profile")
    if loaded_profile is not None:
        return loaded_profile.project_status or ("active" if project.is_active else "inactive")

    # The legacy boolean is sufficient for open projects and avoids an extra
    # database query on the high-volume employee project-selection path.
    if project.is_active:
        return "active"

    session = object_session(project)
    if session is None or project.id is None:
        return "inactive"

    if _PROJECT_MASTER_TABLE_CACHE_KEY not in session.info:
        try:
            session.info[_PROJECT_MASTER_TABLE_CACHE_KEY] = sa_inspect(session.get_bind()).has_table(
                FinanceProjectMasterProfile.__tablename__
            )
        except Exception:  # Compatibility fallback for unusual legacy test engines.
            session.info[_PROJECT_MASTER_TABLE_CACHE_KEY] = False

    if not session.info[_PROJECT_MASTER_TABLE_CACHE_KEY]:
        return "inactive"

    profile = session.get(FinanceProjectMasterProfile, project.id)
    if profile is None:
        return "inactive"
    return profile.project_status or "inactive"


def project_expense_allowed(project: FinanceProject, *, on_date: date | None = None) -> tuple[bool, str | None]:
    today = on_date or utc_now().date()
    # Project lifecycle is Finance-controlled. Employee claim access is based on
    # whether the project itself is currently open, not on employee assignment.
    # Assignment remains useful for staffing/tracking reports only.
    master_status = _project_status_for_claim_rules(project)
    if project.client is not None and not project.client.is_active:
        return False, "This client is inactive. New claims cannot be raised for this project."
    if master_status == "completed":
        return False, "This project has been completed. New claims cannot be raised."
    if master_status == "on_hold":
        return False, "This project is on hold. New claims cannot be raised until Finance/Admin marks it Active."
    if master_status == "inactive" or not project.is_active:
        return False, "This project is inactive. New claims cannot be raised."
    if project.start_date and today < project.start_date:
        return False, f"This project starts on {project.start_date.isoformat()}. New claims can be raised only after the project starts."
    if project.end_date and today > project.end_date:
        return False, f"This project has finished and is completed (project end date {project.end_date.isoformat()}). New claims cannot be raised."
    return True, None


def active_projects(db: Session) -> list[FinanceProject]:
    projects = list(db.scalars(
        select(FinanceProject)
        .where(FinanceProject.is_active.is_(True))
        .order_by(FinanceProject.project_code.asc())
    ).all())
    return [project for project in projects if project_expense_allowed(project)[0]]


def all_projects(db: Session) -> list[FinanceProject]:
    return list(db.scalars(select(FinanceProject).order_by(FinanceProject.project_code.asc())).all())


def project_payload(project: FinanceProject) -> dict:
    today = utc_now().date()
    allowed, block_reason = project_expense_allowed(project, on_date=today)
    profile = project.master_profile
    master_status = profile.project_status if profile else ("active" if project.is_active else "inactive")
    if master_status in {"inactive", "on_hold", "completed"}:
        lifecycle = master_status
    elif project.client is not None and not project.client.is_active:
        lifecycle = "inactive"
    elif project.end_date and today > project.end_date:
        lifecycle = "completed"
    elif project.start_date and today < project.start_date:
        lifecycle = "upcoming"
    else:
        lifecycle = "active"
    client = project.client
    active_assignments = [assignment for assignment in project.assignments if assignment.is_active and assignment.user is not None]
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "client_id": client.id if client else project.client_id,
        "client_code": client.client_code if client else None,
        "client_name": client.client_name if client else project.client_name,
        "project_number": project.project_number,
        "project_source_team": project.project_source_team,
        "project_source_person_name": project.project_source_person_name,
        "client_awarded_by_name": project.client_awarded_by_name,
        "project_award_date": project.project_award_date,
        "description": project.description,
        "start_date": project.start_date,
        "end_date": project.end_date,
        "is_active": project.is_active,
        "lifecycle_status": lifecycle,
        "expense_allowed": allowed,
        "expense_block_reason": block_reason,
        "task": profile.task if profile else None,
        "project_status": master_status,
        "project_manager_id": profile.project_manager_id if profile else None,
        "project_manager_name": profile.project_manager.full_name if profile and profile.project_manager else None,
        "reporting_manager_id": profile.reporting_manager_id if profile else None,
        "reporting_manager_name": profile.reporting_manager.full_name if profile and profile.reporting_manager else None,
        "assigned_employee_ids": [assignment.user_id for assignment in active_assignments],
        "assigned_employees": [
            {
                "id": assignment.user.id,
                "full_name": assignment.user.full_name,
                "email": assignment.user.email,
                "employee_id": assignment.user.employee_id,
                "department": assignment.user.department,
            }
            for assignment in active_assignments
        ],
    }


def employee_project_payload(project: FinanceProject) -> dict:
    """Employee-safe project view: assigned client/project identity, never client contacts/commercial metadata."""
    data = project_payload(project)
    return {
        **data,
        "client_id": None,
        "client_code": None,
        "project_source_team": None,
        "project_source_person_name": None,
        "client_awarded_by_name": None,
        "project_award_date": None,
        "description": None,
        "project_manager_id": None,
        "project_manager_name": None,
        "reporting_manager_id": None,
        "reporting_manager_name": None,
        "assigned_employee_ids": [],
        "assigned_employees": [],
    }


def _user_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.full_name if user else None


def _attachment_payload(db: Session, attachment: ExpenseClaimAttachment) -> dict:
    uploader = db.get(User, attachment.uploaded_by_id)
    return {
        "id": attachment.id,
        "original_filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "file_size": attachment.file_size,
        "content_sha256": attachment.content_sha256,
        "uploaded_by_id": attachment.uploaded_by_id,
        "uploaded_by_name": uploader.full_name if uploader else "Unknown user",
        "created_at": attachment.created_at,
    }


def _payment_payload(db: Session, payment: ExpenseClaimPayment) -> dict:
    recorder = db.get(User, payment.recorded_by_id)
    return {
        "id": payment.id,
        "payment_reference": payment.payment_reference,
        "payment_mode": payment.payment_mode,
        "amount": float(payment.amount),
        "payment_date": payment.payment_date,
        "recorded_by_id": payment.recorded_by_id,
        "recorded_by_name": recorder.full_name if recorder else "Unknown user",
        "comments": payment.comments,
        "created_at": payment.created_at,
    }


def _inclusive_days(start: date | None, end: date | None) -> int | None:
    if not start or not end or end < start:
        return None
    return (end - start).days + 1


def effective_settlement_due_date(claim: ExpenseClaim) -> date | None:
    """Return the final due date for an original advance and all linked top-ups."""
    due_dates = [claim.settlement_due_date] if claim.settlement_due_date else []
    if claim.claim_type == "advance":
        due_dates.extend(
            child.settlement_due_date
            for child in claim.linked_additional_advances
            if child.settlement_due_date
        )
    return max(due_dates) if due_dates else None


def claim_payload(db: Session, claim: ExpenseClaim, viewer: User, effective_role: str) -> dict:
    requester = db.get(User, claim.requester_id)
    role = (effective_role or viewer.role).strip().lower()
    is_requester_employee_view = role == EMPLOYEE_ROLE and claim.requester_id == viewer.id
    can_edit = is_requester_employee_view and claim.status in EDITABLE_STATUSES
    can_submit = can_edit
    paid = claim_paid_amount(claim)
    settlement = claim.settlement if claim.claim_type == "advance" else None
    settlement_final = bool(settlement and settlement.status == "finance_finalized")
    chain_due_date = effective_settlement_due_date(claim)
    settlement_overdue = bool(
        chain_due_date
        and utc_now().date() > chain_due_date
        and claim.claim_type == "advance"
        and paid > 0
        and not settlement_final
    )
    settlement_payload_value = None
    if settlement is not None:
        from app.modules.finance.settlement_service import settlement_payload
        settlement_payload_value = settlement_payload(db, settlement, viewer=viewer, effective_role=role)
    parent = claim.parent_advance if claim.parent_advance_claim_id else None
    project_allowed, _ = project_expense_allowed(claim.project)
    return {
        "id": claim.id,
        "claim_code": claim.claim_code,
        "requester_id": claim.requester_id,
        "requester_name": requester.full_name if requester else "Unknown employee",
        "requester_email": requester.email if requester else "unknown@nakshatech.com",
        "requester_department": requester.department if requester else None,
        "project": employee_project_payload(claim.project) if is_requester_employee_view else project_payload(claim.project),
        "claim_type": claim.claim_type,
        "purpose_description": claim.purpose_description,
        "currency": claim.currency,
        "total_amount": float(claim.total_amount or 0),
        "previous_advance_amount": float(claim.previous_advance_amount) if claim.previous_advance_amount is not None else None,
        "amount_already_used": float(claim.amount_already_used) if claim.amount_already_used is not None else None,
        "parent_advance_claim_id": claim.parent_advance_claim_id,
        "parent_advance_claim_code": parent.claim_code if parent else None,
        "requested_work_start_date": claim.requested_work_start_date,
        "requested_work_end_date": claim.requested_work_end_date,
        "requested_work_days": _inclusive_days(claim.requested_work_start_date, claim.requested_work_end_date),
        "approved_work_start_date": claim.approved_work_start_date,
        "approved_work_end_date": claim.approved_work_end_date,
        "approved_work_days": _inclusive_days(claim.approved_work_start_date, claim.approved_work_end_date),
        "settlement_due_date": chain_due_date if claim.claim_type == "advance" else claim.settlement_due_date,
        "settlement_status": claim.settlement_status or ("not_required" if claim.claim_type == "reimbursement" else "pending_release"),
        "settlement_overdue": settlement_overdue,
        "status": claim.status,
        "admin_decision_by_name": _user_name(db, claim.admin_decision_by_id),
        "admin_decision_at": claim.admin_decision_at,
        "admin_comments": claim.admin_comments,
        "finance_decision_by_name": _user_name(db, claim.finance_decision_by_id),
        "finance_decision_at": claim.finance_decision_at,
        "finance_comments": claim.finance_comments,
        "finance_approved_amount": float(approved_amount(claim)) if approved_amount(claim) > 0 else None,
        "remaining_amount": float(remaining_amount(claim)),
        "payment_reference": claim.payment_reference,
        "paid_amount": float(paid) if paid > 0 else None,
        "paid_at": claim.paid_at,
        "submitted_at": claim.submitted_at,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
        "items": [
            {
                "id": item.id,
                "category": item.category,
                "other_category": item.other_category,
                "description": item.description,
                "amount": float(item.amount),
                "payment_mode": item.payment_mode,
                "expense_date": item.expense_date,
            }
            for item in claim.items
        ],
        "attachments": [_attachment_payload(db, attachment) for attachment in claim.attachments],
        "events": [
            {
                "id": event.id,
                "action": event.action,
                "actor_name": event.actor_name,
                "actor_email": event.actor_email,
                "actor_role": event.actor_role,
                "from_status": event.from_status,
                "to_status": event.to_status,
                "comments": event.comments,
                "created_at": event.created_at,
            }
            for event in claim.events
        ],
        "payments": [_payment_payload(db, payment) for payment in claim.payments],
        "settlement": settlement_payload_value,
        "linked_additional_advance_ids": [item.id for item in claim.linked_additional_advances],
        "can_edit": can_edit,
        "can_submit": can_submit,
        "can_admin_decide": role == ADMIN_ROLE and claim.status == "submitted",
        "can_finance_decide": role == FINANCE_ROLE and claim.status == "admin_approved",
        "can_mark_paid": role == FINANCE_ROLE and claim.status in {"finance_approved", "partially_paid"} and remaining_amount(claim) > 0,
        "can_settle_advance": is_requester_employee_view and claim.claim_type == "advance" and paid > 0 and not settlement_final,
        "can_request_additional_advance": is_requester_employee_view and claim.claim_type == "advance" and paid > 0 and project_allowed and not settlement_final,
    }


def list_visible_claims(db: Session, *, viewer: User, effective_role: str, status: str | None = None) -> list[ExpenseClaim]:
    role = effective_role.strip().lower()
    query = select(ExpenseClaim)
    if role == EMPLOYEE_ROLE:
        query = query.where(ExpenseClaim.requester_id == viewer.id)
    elif role in VISIBLE_STAFF_ROLES:
        query = query.where(ExpenseClaim.status != "draft")
    else:
        return []
    if status:
        query = query.where(ExpenseClaim.status == status.strip().lower())
    return list(db.scalars(query.order_by(ExpenseClaim.updated_at.desc(), ExpenseClaim.id.desc()).limit(1000)).unique().all())


def get_visible_claim(db: Session, *, claim_id: int, viewer: User, effective_role: str) -> ExpenseClaim | None:
    claim = db.get(ExpenseClaim, claim_id)
    if claim is None:
        return None
    role = effective_role.strip().lower()
    if role == EMPLOYEE_ROLE:
        return claim if claim.requester_id == viewer.id else None
    if role in VISIBLE_STAFF_ROLES:
        if claim.status == "draft" and claim.requester_id != viewer.id:
            return None
        return claim
    return None


def _replace_items(claim: ExpenseClaim, payload: ExpenseClaimCreateRequest) -> None:
    claim.items.clear()
    total = Decimal("0.00")
    for entry in payload.items:
        amount = money(entry.amount)
        total += amount
        claim.items.append(
            ExpenseClaimItem(
                category=entry.category.strip().lower(),
                other_category=(entry.other_category or "").strip() or None,
                description=entry.description.strip(),
                amount=amount,
                payment_mode=entry.payment_mode,
                expense_date=entry.expense_date,
            )
        )
    claim.total_amount = money(total)


def _validate_project_dates(project: FinanceProject, start_date: date, end_date: date) -> None:
    allowed, reason = project_expense_allowed(project)
    if not allowed:
        raise ValueError(reason or "This project does not accept new expenses")
    if project.start_date and start_date < project.start_date:
        raise ValueError(f"Work start date cannot be before the project start date {project.start_date.isoformat()}")
    if project.end_date and end_date > project.end_date:
        raise ValueError(f"Work end date cannot be after the project end date {project.end_date.isoformat()}")


def _validate_parent_advance(db: Session, requester: User, payload: ExpenseClaimCreateRequest, project: FinanceProject) -> ExpenseClaim | None:
    if payload.claim_type != "additional_advance":
        return None
    parent = db.get(ExpenseClaim, payload.parent_advance_claim_id) if payload.parent_advance_claim_id else None
    if parent is None or parent.claim_type != "advance":
        raise ValueError("Select a valid original Advance Request")
    if parent.requester_id != requester.id:
        raise ValueError("The original Advance Request must belong to the same employee")
    if parent.project_id != project.id:
        raise ValueError("Additional Advance must use the same Project ID as the original Advance Request")
    if claim_paid_amount(parent) <= 0:
        raise ValueError("Additional Advance can be requested only after the original advance has been released")
    if parent.settlement and parent.settlement.status == "finance_finalized":
        raise ValueError("This advance is already finally settled")
    return parent


def total_released_for_advance_chain(root: ExpenseClaim) -> Decimal:
    total = claim_paid_amount(root)
    for additional in root.linked_additional_advances:
        total += claim_paid_amount(additional)
    return money(total)


def _apply_claim_fields(
    db: Session,
    claim: ExpenseClaim,
    requester: User,
    payload: ExpenseClaimCreateRequest,
    project: FinanceProject,
) -> None:
    _validate_project_dates(project, payload.requested_work_start_date, payload.requested_work_end_date)
    parent = _validate_parent_advance(db, requester, payload, project)
    claim.project = project
    claim.project_id = project.id
    claim.claim_type = payload.claim_type
    claim.purpose_description = payload.purpose_description.strip()
    claim.requested_work_start_date = payload.requested_work_start_date
    claim.requested_work_end_date = payload.requested_work_end_date
    claim.parent_advance_claim_id = parent.id if parent else None
    if parent is not None:
        claim.previous_advance_amount = total_released_for_advance_chain(parent)
        claim.amount_already_used = money(payload.amount_already_used)
        claim.settlement_status = "covered_by_parent"
    else:
        claim.previous_advance_amount = money(payload.previous_advance_amount) if payload.previous_advance_amount is not None else None
        claim.amount_already_used = money(payload.amount_already_used) if payload.amount_already_used is not None else None
        claim.settlement_status = "pending_release" if payload.claim_type == "advance" else "not_required"
    _replace_items(claim, payload)


def create_claim(db: Session, *, requester: User, payload: ExpenseClaimCreateRequest) -> ExpenseClaim:
    project = db.get(FinanceProject, payload.project_id)
    if not project:
        raise ValueError("Select a valid Project ID")
    claim = ExpenseClaim(
        claim_code=f"DRAFT-{secrets.token_hex(10)}",
        requester_id=requester.id,
        project_id=project.id,
        claim_type=payload.claim_type,
        purpose_description=payload.purpose_description.strip(),
        currency="INR",
        status="draft",
        settlement_status="pending_release" if payload.claim_type == "advance" else "not_required",
    )
    _apply_claim_fields(db, claim, requester, payload, project)
    db.add(claim)
    db.flush()
    claim.claim_code = f"NT-EXP-{utc_now().year}-{claim.id:05d}"
    add_event(db, claim=claim, action="created", actor=requester, from_status=None, to_status="draft", comments="Expense claim draft created")
    db.commit()
    db.refresh(claim)
    return claim


def update_claim(db: Session, *, claim: ExpenseClaim, requester: User, payload: ExpenseClaimCreateRequest) -> ExpenseClaim:
    if claim.requester_id != requester.id or claim.status not in EDITABLE_STATUSES:
        raise PermissionError("This claim is not editable")
    project = db.get(FinanceProject, payload.project_id)
    if not project:
        raise ValueError("Select a valid Project ID")
    _apply_claim_fields(db, claim, requester, payload, project)
    add_event(
        db,
        claim=claim,
        action="updated",
        actor=requester,
        from_status=claim.status,
        to_status=claim.status,
        comments="Employee updated claim details before resubmission",
    )
    db.commit()
    db.refresh(claim)
    return claim


def add_event(
    db: Session,
    *,
    claim: ExpenseClaim,
    action: str,
    actor: User | None,
    from_status: str | None,
    to_status: str,
    comments: str | None,
) -> ExpenseClaimEvent:
    event = ExpenseClaimEvent(
        claim_id=claim.id,
        event_key=f"{claim.id}:{action}:{secrets.token_hex(12)}",
        action=action,
        actor_user_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.role if actor else None,
        from_status=from_status,
        to_status=to_status,
        comments=(comments or "").strip() or None,
    )
    db.add(event)
    return event


def _safe_notification(db: Session, **kwargs) -> None:
    try:
        create_global_notification(db, **kwargs)
    except Exception:
        logger.exception("Finance notification creation failed")


def submit_claim(db: Session, *, claim: ExpenseClaim, requester: User, request=None) -> ExpenseClaim:
    claim = _locked_claim(db, claim)
    if claim.requester_id != requester.id or claim.status not in EDITABLE_STATUSES:
        raise PermissionError("This claim cannot be submitted")
    if not claim.items or money(claim.total_amount) <= 0:
        raise ValueError("Add at least one valid expense item before submitting")
    if claim.claim_type in {"reimbursement", "additional_advance"} and not claim.attachments:
        raise ValueError("Attach at least one bill, receipt, invoice, or proof before submitting this claim")

    previous = claim.status
    claim.status = "submitted"
    claim.submitted_at = utc_now()
    claim.admin_decision_by_id = None
    claim.admin_decision_at = None
    claim.admin_comments = None
    claim.finance_decision_by_id = None
    claim.finance_decision_at = None
    claim.finance_comments = None
    claim.finance_approved_amount = None
    add_event(db, claim=claim, action="submitted", actor=requester, from_status=previous, to_status="submitted", comments="Submitted for Admin verification")
    _safe_notification(
        db,
        event_type="FINANCE_CLAIM_SUBMITTED",
        category="approval",
        title=f"Expense claim awaiting Admin verification: {claim.claim_code}",
        message=f"{requester.full_name} submitted {CLAIM_TYPE_LABELS.get(claim.claim_type, claim.claim_type)} for INR {float(claim.total_amount):,.2f}.",
        target_url=f"/finance/claims/{claim.id}",
        recipient_roles=[ADMIN_ROLE],
        dedupe_key=f"finance-claim:{claim.id}:submitted:{claim.submitted_at.isoformat()}",
    )
    record_audit(
        db,
        event_type="FINANCE_CLAIM_SUBMITTED",
        request=request,
        user=requester,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={"claim_code": claim.claim_code, "claim_type": claim.claim_type, "amount": float(claim.total_amount), "project": claim.project.project_code},
    )
    db.commit()
    db.refresh(claim)
    return claim


def admin_decision(
    db: Session,
    *,
    claim: ExpenseClaim,
    actor: User,
    action: str,
    comments: str,
    approved_work_start_date: date | None = None,
    approved_work_end_date: date | None = None,
    settlement_due_date: date | None = None,
    request=None,
) -> ExpenseClaim:
    claim = _locked_claim(db, claim)
    if claim.status != "submitted":
        raise ValueError("Only claims awaiting Admin verification can be decided by Admin")
    previous = claim.status
    target = {
        "approve": "admin_approved",
        "reject": "admin_rejected",
        "send_back": "admin_sent_back",
    }[action]
    claim.status = target
    claim.admin_decision_by_id = actor.id
    claim.admin_decision_at = utc_now()
    claim.admin_comments = comments.strip()
    if action == "approve":
        work_start = approved_work_start_date or claim.requested_work_start_date
        work_end = approved_work_end_date or claim.requested_work_end_date
        if work_start and work_end:
            if work_end < work_start:
                raise ValueError("Approved work end date cannot be earlier than approved work start date")
            _validate_project_dates(claim.project, work_start, work_end)
            claim.approved_work_start_date = work_start
            claim.approved_work_end_date = work_end
        if settlement_due_date:
            if claim.approved_work_end_date and settlement_due_date < claim.approved_work_end_date:
                raise ValueError("Settlement due date cannot be earlier than the approved work end date")
            claim.settlement_due_date = settlement_due_date
    add_event(db, claim=claim, action=f"admin_{action}", actor=actor, from_status=previous, to_status=target, comments=comments)

    if action == "approve":
        _safe_notification(
            db,
            event_type="FINANCE_CLAIM_ADMIN_APPROVED",
            category="approval",
            title=f"Finance verification required: {claim.claim_code}",
            message=f"Admin verified {claim.claim_code}. Finance review is now required for INR {float(claim.total_amount):,.2f}.",
            target_url=f"/finance/claims/{claim.id}",
            recipient_roles=[FINANCE_ROLE],
            dedupe_key=f"finance-claim:{claim.id}:admin-approved:{claim.admin_decision_at.isoformat()}",
        )
    else:
        _safe_notification(
            db,
            event_type="FINANCE_CLAIM_ADMIN_RETURNED" if action == "send_back" else "FINANCE_CLAIM_ADMIN_REJECTED",
            category="approval",
            title=f"Expense claim update: {claim.claim_code}",
            message=f"Admin {('sent back' if action == 'send_back' else 'rejected')} your claim. Review the comments and status.",
            target_url=f"/expenses/{claim.id}",
            recipient_user_ids=[claim.requester_id],
            dedupe_key=f"finance-claim:{claim.id}:admin-{action}:{claim.admin_decision_at.isoformat()}",
        )
    record_audit(
        db,
        event_type=f"FINANCE_CLAIM_ADMIN_{action.upper()}",
        request=request,
        user=actor,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={"claim_code": claim.claim_code, "from": previous, "to": target, "comments": comments},
    )
    db.commit()
    db.refresh(claim)
    return claim


def finance_decision(
    db: Session,
    *,
    claim: ExpenseClaim,
    actor: User,
    action: str,
    comments: str,
    approved_value: float | None = None,
    approved_work_start_date: date | None = None,
    approved_work_end_date: date | None = None,
    settlement_due_date: date | None = None,
    request=None,
) -> ExpenseClaim:
    claim = _locked_claim(db, claim)
    if claim.status != "admin_approved":
        raise ValueError("Finance can decide only claims already verified by Admin")
    previous = claim.status
    target = {
        "approve": "finance_approved",
        "reject": "finance_rejected",
        "send_back": "finance_sent_back",
    }[action]
    claim.status = target
    claim.finance_decision_by_id = actor.id
    claim.finance_decision_at = utc_now()
    claim.finance_comments = comments.strip()

    if action == "approve":
        work_start = approved_work_start_date or claim.approved_work_start_date or claim.requested_work_start_date
        work_end = approved_work_end_date or claim.approved_work_end_date or claim.requested_work_end_date
        if not work_start or not work_end:
            raise ValueError("Finance must confirm the approved work start and end dates")
        if work_end < work_start:
            raise ValueError("Approved work end date cannot be earlier than approved work start date")
        _validate_project_dates(claim.project, work_start, work_end)
        claim.approved_work_start_date = work_start
        claim.approved_work_end_date = work_end
        due = settlement_due_date or claim.settlement_due_date
        if claim.claim_type in {"advance", "additional_advance"}:
            if due is None:
                raise ValueError("Set a settlement due date before Finance approves an advance")
            if due < work_end:
                raise ValueError("Settlement due date cannot be earlier than the approved work end date")
            claim.settlement_due_date = due
        elif due is not None:
            claim.settlement_due_date = due
        approved = money(approved_value) if approved_value is not None else money(claim.total_amount)
        if approved <= 0:
            raise ValueError("Finance approved amount must be greater than zero")
        if approved > money(claim.total_amount):
            raise ValueError("Finance approved amount cannot exceed the employee requested amount")
        claim.finance_approved_amount = approved
        event_comment = f"{comments.strip()} | Approved amount: INR {float(approved):,.2f} | Work: {claim.approved_work_start_date} to {claim.approved_work_end_date}" + (f" | Settlement due: {claim.settlement_due_date}" if claim.settlement_due_date else "")
    else:
        claim.finance_approved_amount = None
        event_comment = comments

    add_event(db, claim=claim, action=f"finance_{action}", actor=actor, from_status=previous, to_status=target, comments=event_comment)
    _safe_notification(
        db,
        event_type=f"FINANCE_CLAIM_FINANCE_{action.upper()}",
        category="approval",
        title=f"Finance decision: {claim.claim_code}",
        message=(
            f"Finance approved your expense claim for INR {float(claim.finance_approved_amount):,.2f}."
            if action == "approve"
            else f"Finance {('sent back' if action == 'send_back' else 'rejected')} your expense claim."
        ),
        target_url=f"/expenses/{claim.id}",
        recipient_user_ids=[claim.requester_id],
        dedupe_key=f"finance-claim:{claim.id}:finance-{action}:{claim.finance_decision_at.isoformat()}",
    )
    if action == "approve":
        _safe_notification(
            db,
            event_type="FINANCE_CLAIM_APPROVED_MANAGEMENT_VISIBILITY",
            category="approval",
            title=f"Finance approved {claim.claim_code}",
            message=f"Approved amount: INR {float(claim.finance_approved_amount):,.2f}. The claim is awaiting payment/settlement.",
            target_url=f"/finance/claims/{claim.id}",
            recipient_roles=[MANAGEMENT_ROLE],
            dedupe_key=f"finance-claim:{claim.id}:management-approved:{claim.finance_decision_at.isoformat()}",
        )
    record_audit(
        db,
        event_type=f"FINANCE_CLAIM_FINANCE_{action.upper()}",
        request=request,
        user=actor,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={
            "claim_code": claim.claim_code,
            "from": previous,
            "to": target,
            "comments": comments,
            "requested_amount": float(claim.total_amount),
            "approved_amount": float(claim.finance_approved_amount) if claim.finance_approved_amount is not None else None,
        },
    )
    db.commit()
    db.refresh(claim)
    return claim


def mark_paid(
    db: Session,
    *,
    claim: ExpenseClaim,
    actor: User,
    payment_reference: str,
    paid_amount: float | None,
    payment_mode: str = "bank_transfer",
    payment_date: date | None = None,
    comments: str | None,
    request=None,
) -> ExpenseClaim:
    claim = _locked_claim(db, claim)
    if claim.status not in {"finance_approved", "partially_paid"}:
        raise ValueError("Only a Finance-approved claim with an outstanding balance can receive a payment")

    approved = approved_amount(claim)
    if approved <= 0:
        approved = money(claim.total_amount)
        claim.finance_approved_amount = approved

    already_paid = claim_paid_amount(claim)
    remaining = max(Decimal("0.00"), approved - already_paid)
    if remaining <= 0:
        raise ValueError("This claim is already fully paid")

    amount = money(paid_amount) if paid_amount is not None else money(remaining)
    if amount <= 0:
        raise ValueError("Paid amount must be greater than zero")
    if amount > remaining:
        raise ValueError("Payment cannot exceed the outstanding approved amount")

    reference = payment_reference.strip()
    duplicate = db.scalar(
        select(ExpenseClaimPayment.id).where(
            ExpenseClaimPayment.claim_id == claim.id,
            func.lower(ExpenseClaimPayment.payment_reference) == reference.lower(),
        )
    )
    if duplicate is not None:
        raise ValueError("This payment reference is already recorded for the claim")

    actual_date = payment_date or utc_now().date()
    payment = ExpenseClaimPayment(
        claim_id=claim.id,
        payment_reference=reference,
        payment_mode=payment_mode.strip().lower(),
        amount=amount,
        payment_date=actual_date,
        recorded_by_id=actor.id,
        comments=(comments or "").strip() or None,
    )
    db.add(payment)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("This payment reference is already recorded for the claim") from exc

    aggregate_paid = money(already_paid + amount)
    balance = max(Decimal("0.00"), approved - aggregate_paid)
    previous = claim.status
    claim.status = "paid" if balance == 0 else "partially_paid"
    claim.payment_reference = reference
    claim.paid_amount = aggregate_paid
    claim.paid_at = utc_now() if balance == 0 else claim.paid_at
    if claim.claim_type == "advance":
        claim.settlement_status = "open"
    elif claim.claim_type == "additional_advance" and claim.parent_advance is not None:
        claim.settlement_status = "covered_by_parent"
        if claim.parent_advance.settlement_status not in {"settled", "finalized_balance_pending", "finalized_shortage"}:
            claim.parent_advance.settlement_status = "open"

    add_event(
        db,
        claim=claim,
        action="payment_recorded",
        actor=actor,
        from_status=previous,
        to_status=claim.status,
        comments=(
            f"INR {float(amount):,.2f} via {payment.payment_mode.replace('_', ' ').title()} "
            f"on {actual_date.isoformat()} | Ref: {reference} | Remaining: INR {float(balance):,.2f}"
            + (f" | {comments.strip()}" if comments and comments.strip() else "")
        ),
    )
    _safe_notification(
        db,
        event_type="FINANCE_CLAIM_PAID" if balance == 0 else "FINANCE_CLAIM_PARTIAL_PAYMENT",
        category="approval",
        title=(f"Payment completed: {claim.claim_code}" if balance == 0 else f"Partial payment recorded: {claim.claim_code}"),
        message=(
            f"Finance recorded payment of INR {float(amount):,.2f}. Total paid: INR {float(aggregate_paid):,.2f}. "
            f"Outstanding: INR {float(balance):,.2f}. Reference: {reference}."
        ),
        target_url=f"/expenses/{claim.id}",
        recipient_user_ids=[claim.requester_id],
        dedupe_key=f"finance-claim:{claim.id}:payment:{payment.id}",
    )
    record_audit(
        db,
        event_type="FINANCE_CLAIM_PAYMENT_RECORDED",
        request=request,
        user=actor,
        module="finance",
        target_type="expense_claim",
        target_id=claim.id,
        details={
            "claim_code": claim.claim_code,
            "payment_id": payment.id,
            "payment_reference": reference,
            "payment_mode": payment.payment_mode,
            "payment_date": actual_date.isoformat(),
            "payment_amount": float(amount),
            "aggregate_paid_amount": float(aggregate_paid),
            "approved_amount": float(approved),
            "outstanding_amount": float(balance),
            "status": claim.status,
        },
    )
    db.commit()
    db.refresh(claim)
    return claim


def dashboard_payload(db: Session, *, viewer: User, effective_role: str) -> dict:
    claims = list_visible_claims(db, viewer=viewer, effective_role=effective_role)
    total_requested = sum((money(claim.total_amount) for claim in claims), Decimal("0.00"))
    pending_admin = [claim for claim in claims if claim.status == "submitted"]
    pending_finance = [claim for claim in claims if claim.status == "admin_approved"]
    approved = [claim for claim in claims if claim.status in {"finance_approved", "partially_paid", "paid"}]
    partially_paid = [claim for claim in claims if claim.status == "partially_paid"]
    paid = [claim for claim in claims if claim.status == "paid"]
    rejected = [claim for claim in claims if claim.status in {"admin_rejected", "finance_rejected"}]
    sent_back = [claim for claim in claims if claim.status in {"admin_sent_back", "finance_sent_back"}]
    advance_roots = [claim for claim in claims if claim.claim_type == "advance" and claim_paid_amount(claim) > 0]
    pending_settlement = [claim for claim in advance_roots if claim.settlement_status not in {"settled", "finalized_balance_pending", "finalized_shortage"}]
    overdue_settlement = [
        claim for claim in pending_settlement
        if effective_settlement_due_date(claim) and utc_now().date() > effective_settlement_due_date(claim)
    ]
    settlement_under_review = [claim for claim in advance_roots if claim.settlement and claim.settlement.status in {"submitted", "admin_approved"}]
    settled_advances = [claim for claim in advance_roots if claim.settlement_status in {"settled", "finalized_balance_pending", "finalized_shortage"}]

    type_data: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"amount": Decimal("0.00"), "count": 0})
    category_data: dict[str, dict[str, Decimal | int]] = defaultdict(lambda: {"amount": Decimal("0.00"), "count": 0})
    project_data: dict[str, dict[str, Decimal | int | str]] = defaultdict(lambda: {"amount": Decimal("0.00"), "count": 0, "label": ""})

    for claim in claims:
        type_data[claim.claim_type]["amount"] += money(claim.total_amount)
        type_data[claim.claim_type]["count"] += 1
        project_data[claim.project.project_code]["amount"] += money(claim.total_amount)
        project_data[claim.project.project_code]["count"] += 1
        project_data[claim.project.project_code]["label"] = f"{claim.project.project_code} · {claim.project.project_name}"
        for item in claim.items:
            category_key = item.other_category if item.category == "other" and item.other_category else item.category
            category_data[category_key]["amount"] += money(item.amount)
            category_data[category_key]["count"] += 1

    def breakdown(source, label_for_key=None):
        rows = []
        for key, values in source.items():
            label = label_for_key(key, values) if label_for_key else str(key).replace("_", " ").title()
            rows.append({"key": key, "label": label, "amount": float(values["amount"]), "count": int(values["count"])})
        return sorted(rows, key=lambda item: (-item["amount"], item["label"]))

    return {
        "total_claims": len(claims),
        "total_requested_amount": float(total_requested),
        "pending_admin_count": len(pending_admin),
        "pending_admin_amount": float(sum((money(c.total_amount) for c in pending_admin), Decimal("0.00"))),
        "pending_finance_count": len(pending_finance),
        "pending_finance_amount": float(sum((money(c.total_amount) for c in pending_finance), Decimal("0.00"))),
        "approved_count": len(approved),
        "approved_amount": float(sum((approved_amount(c) for c in approved), Decimal("0.00"))),
        "paid_count": len(paid),
        "paid_amount": float(sum((claim_paid_amount(c) for c in approved), Decimal("0.00"))),
        "outstanding_amount": float(sum((remaining_amount(c) for c in approved), Decimal("0.00"))),
        "rejected_count": len(rejected),
        "partially_paid_count": len(partially_paid),
        "sent_back_count": len(sent_back),
        "pending_settlement_count": len(pending_settlement),
        "overdue_settlement_count": len(overdue_settlement),
        "settlement_under_review_count": len(settlement_under_review),
        "settled_count": len(settled_advances),
        "by_type": breakdown(type_data, lambda key, _values: CLAIM_TYPE_LABELS.get(key, key.replace("_", " ").title())),
        "by_category": breakdown(category_data),
        "by_project": breakdown(project_data, lambda _key, values: str(values["label"])),
        "recent_claims": [claim_payload(db, claim, viewer, effective_role) for claim in claims[:8]],
    }


def _configured_email_list(raw: str) -> list[str]:
    return [value.strip().lower() for value in raw.replace(";", ",").split(",") if value.strip()]


def _role_emails(db: Session, roles: Iterable[str]) -> list[str]:
    role_set = {role.strip().lower() for role in roles}
    return list(db.scalars(
        select(User.email)
        .where(User.role.in_(role_set), User.is_active.is_(True), User.account_status == "active")
        .order_by(User.id.asc())
    ).all())


def _email_recipients_for_event(db: Session, claim: ExpenseClaim, event: str) -> list[tuple[str, str]]:
    requester = db.get(User, claim.requester_id)
    recipients: list[tuple[str, str]] = []
    if event == "submitted":
        emails = _configured_email_list(settings.finance_admin_notification_emails) or _role_emails(db, [ADMIN_ROLE])
        recipients.extend((email, "Admin verification") for email in emails)
    elif event == "admin_approved":
        emails = _configured_email_list(settings.finance_team_notification_emails) or _role_emails(db, [FINANCE_ROLE])
        recipients.extend((email, "Finance verification") for email in emails)
    elif event in {"admin_rejected", "admin_sent_back", "finance_approved", "finance_rejected", "finance_sent_back", "partially_paid", "paid"} and requester:
        recipients.append((requester.email, "Employee update"))
    if event in {"finance_approved", "partially_paid", "paid"}:
        recipients.extend((email, "Management visibility") for email in _role_emails(db, [MANAGEMENT_ROLE]))
    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for email, audience in recipients:
        normalized = email.strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append((normalized, audience))
    return deduped


def _claim_email_content(db: Session, claim: ExpenseClaim, event: str, audience: str) -> tuple[str, str, str]:
    requester = db.get(User, claim.requester_id)
    requester_name = requester.full_name if requester else "NakshaTech employee"
    project = claim.project
    event_label = {
        "submitted": "Submitted for Admin verification",
        "admin_approved": "Admin verified - Finance action required",
        "admin_rejected": "Rejected by Admin",
        "admin_sent_back": "Sent back by Admin",
        "finance_approved": "Approved by Finance",
        "finance_rejected": "Rejected by Finance",
        "finance_sent_back": "Sent back by Finance",
        "partially_paid": "Partial payment recorded",
        "paid": "Payment completed",
    }.get(event, STATUS_LABELS.get(claim.status, claim.status))
    target_path = f"/expenses/{claim.id}" if audience == "Employee update" else f"/finance/claims/{claim.id}"
    link = f"{settings.app_public_url.rstrip('/')}{target_path}"
    subject = f"[{claim.claim_code}] {event_label}"
    lines = [
        settings.finance_email_heading,
        "",
        f"Status: {event_label}",
        f"Claim: {claim.claim_code}",
        f"Employee: {requester_name}",
        f"Project: {project.project_code} - {project.project_name}",
        f"Request type: {CLAIM_TYPE_LABELS.get(claim.claim_type, claim.claim_type)}",
        f"Requested amount: INR {float(claim.total_amount):,.2f}",
        *( [f"Finance approved amount: INR {float(approved_amount(claim)):,.2f}"] if approved_amount(claim) > 0 else [] ),
        *( [f"Paid to date: INR {float(claim_paid_amount(claim)):,.2f}", f"Outstanding: INR {float(remaining_amount(claim)):,.2f}"] if claim_paid_amount(claim) > 0 else [] ),
        f"Description: {claim.purpose_description}",
        f"Open in Asset Management: {link}",
    ]
    if claim.admin_comments:
        lines.append(f"Admin comments: {claim.admin_comments}")
    if claim.finance_comments:
        lines.append(f"Finance comments: {claim.finance_comments}")
    if claim.payment_reference:
        lines.append(f"Payment reference: {claim.payment_reference}")
    text_body = "\n".join(lines)

    item_rows = "".join(
        "<tr>"
        f"<td>{html.escape((item.other_category if item.category == 'other' and item.other_category else item.category).replace('_', ' ').title())}</td>"
        f"<td>{html.escape(item.description)}</td>"
        f"<td style='text-align:right'>INR {float(item.amount):,.2f}</td>"
        "</tr>"
        for item in claim.items
    )
    html_body = f"""
    <div style="font-family:Arial,sans-serif;color:#17324a;max-width:760px;margin:auto">
      <div style="background:#06233a;color:#fff;padding:20px 24px;border-radius:12px 12px 0 0">
        <div style="font-size:12px;letter-spacing:1.5px;color:#35d2e8;font-weight:700">NAKSHATECH · FINANCE CRM</div>
        <h2 style="margin:8px 0 0">{html.escape(event_label)}</h2>
      </div>
      <div style="border:1px solid #d8e6ef;border-top:0;padding:22px 24px;border-radius:0 0 12px 12px;background:#fff">
        <p><strong>{html.escape(claim.claim_code)}</strong> · {html.escape(CLAIM_TYPE_LABELS.get(claim.claim_type, claim.claim_type))}</p>
        <p><strong>Employee:</strong> {html.escape(requester_name)}<br/>
           <strong>Project:</strong> {html.escape(project.project_code)} - {html.escape(project.project_name)}<br/>
           <strong>Requested:</strong> INR {float(claim.total_amount):,.2f}<br/>
           {f'<strong>Finance approved:</strong> INR {float(approved_amount(claim)):,.2f}<br/>' if approved_amount(claim) > 0 else ''}
           {f'<strong>Paid to date:</strong> INR {float(claim_paid_amount(claim)):,.2f}<br/><strong>Outstanding:</strong> INR {float(remaining_amount(claim)):,.2f}' if claim_paid_amount(claim) > 0 else ''}</p>
        <p>{html.escape(claim.purpose_description)}</p>
        <table style="width:100%;border-collapse:collapse;margin:18px 0">
          <thead><tr><th style="text-align:left;border-bottom:1px solid #d8e6ef;padding:8px">Category</th><th style="text-align:left;border-bottom:1px solid #d8e6ef;padding:8px">Usage</th><th style="text-align:right;border-bottom:1px solid #d8e6ef;padding:8px">Amount</th></tr></thead>
          <tbody>{item_rows}</tbody>
        </table>
        {f'<p><strong>Admin comments:</strong> {html.escape(claim.admin_comments)}</p>' if claim.admin_comments else ''}
        {f'<p><strong>Finance comments:</strong> {html.escape(claim.finance_comments)}</p>' if claim.finance_comments else ''}
        {f'<p><strong>Payment reference:</strong> {html.escape(claim.payment_reference)}</p>' if claim.payment_reference else ''}
        <p style="margin-top:22px"><a href="{html.escape(link)}" style="display:inline-block;background:#0a8fbd;color:#fff;text-decoration:none;padding:11px 16px;border-radius:8px;font-weight:700">Open Expense Claim</a></p>
      </div>
    </div>
    """
    return subject, text_body, html_body


def deliver_finance_lifecycle_emails(claim_id: int, event: str, actor_id: int | None = None) -> None:
    """Best-effort lifecycle email delivery.

    SMTP errors are deliberately isolated from the expense transaction. The
    database status and audit trail remain authoritative even if email is down.
    """
    with SessionLocal() as db:
        claim = db.get(ExpenseClaim, claim_id)
        if not claim:
            return
        actor = db.get(User, actor_id) if actor_id else None
        for recipient, audience in _email_recipients_for_event(db, claim, event):
            try:
                subject, text_body, html_body = _claim_email_content(db, claim, event, audience)
                send_email(
                    recipient=recipient,
                    subject=subject,
                    body=text_body,
                    html_body=html_body,
                    from_name=settings.finance_email_heading,
                )
                record_audit(
                    db,
                    event_type="FINANCE_EMAIL_SENT",
                    user=actor,
                    actor_email=actor.email if actor else None,
                    module="finance",
                    target_type="expense_claim",
                    target_id=claim.id,
                    details={"recipient": recipient, "event": event, "audience": audience},
                )
            except Exception as exc:
                logger.exception("Finance email delivery failed for %s to %s", claim.claim_code, recipient)
                record_audit(
                    db,
                    event_type="FINANCE_EMAIL_FAILED",
                    user=actor,
                    actor_email=actor.email if actor else None,
                    result="failed",
                    module="finance",
                    target_type="expense_claim",
                    target_id=claim.id,
                    details={"recipient": recipient, "event": event, "error": str(exc)[:500]},
                )
        db.commit()
