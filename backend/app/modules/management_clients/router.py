from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.models.entities import utc_now
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.management_projects.models import ManagementProjectLink
from app.modules.management_projects.router import (
    _legacy_stage_counts, _project_packages, _project_payload, _tracking_rollup,
)
from app.modules.operations.models import ProjectWorkflow, WorkPackageItemActivity
from app.modules.operations.lifecycle_models import ProjectInvoice
from app.modules.operations.lifecycle_service import (
    APPROVAL_PENDING, FEEDBACK_NOT_SENT, READY_FOR_BILLING,
    MANAGEMENT_SOURCE_APPROVED_EVENT, _transition, management_source_approval_event,
)
from app.modules.operations.production_items import build_item_rows, file_aggregates_for_packages
from app.modules.management_clients.models import ManagementClientIntake
from app.modules.management_clients.schemas import ManagementClientInput, ManagementClientResponse

router = APIRouter(prefix="/management/client-register", tags=["Management Client Register"])

# The two authoritative management logins. This is enforced server-side, not only in the sidebar.
MANAGEMENT_EMAILS = frozenset({"vinod@nakshatech.com", "chethan@nakshatech.com"})


def _management_only(auth: CurrentAuth) -> None:
    role = str(auth.effective_role or "").strip().lower()
    email = str(auth.user.email or "").strip().lower()
    if role != "management" or email not in MANAGEMENT_EMAILS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Management client register access denied")


def _check_code(db: Session, client_code: str, exclude_id: int | None = None) -> None:
    existing = db.scalar(select(ManagementClientIntake.id).where(ManagementClientIntake.client_code == client_code))
    if existing is not None and existing != exclude_id:
        raise HTTPException(status_code=409, detail="Client ID is already registered in Management")
    # Avoid an identifier collision when Finance later converts this intake into the Client Master.
    finance_existing = db.scalar(select(FinanceClient).where(FinanceClient.client_code == client_code))
    # Finance creates a linked management-sourced FinanceClient on the first project.
    # That linked copy must not block normal edits to the ORIGINAL management intake.
    same_intake = db.get(ManagementClientIntake, exclude_id) if exclude_id is not None else None
    if finance_existing is not None and not (
        same_intake is not None and same_intake.client_code == client_code
        and finance_existing.source_team == "management"
    ):
        raise HTTPException(status_code=409, detail="Client ID already exists in the Finance Client Master")


def _values(payload: ManagementClientInput) -> dict:
    return payload.model_dump()


@router.get("", response_model=list[ManagementClientResponse])
def list_management_clients(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _management_only(auth)
    return db.scalars(
        select(ManagementClientIntake).order_by(
            ManagementClientIntake.created_at.desc(), ManagementClientIntake.id.desc()
        )
    ).all()


@router.post("", response_model=ManagementClientResponse, status_code=status.HTTP_201_CREATED)
def create_management_client(
    payload: ManagementClientInput, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _management_only(auth)
    _check_code(db, payload.client_code)
    row = ManagementClientIntake(
        **_values(payload),
        source_person_name=auth.user.full_name,
        created_by_id=auth.user.id,
        updated_by_id=auth.user.id,
        is_active=True,
    )
    try:
        db.add(row)
        db.flush()
        record_audit(
            db, event_type="MANAGEMENT_CLIENT_REGISTERED", request=request, user=auth.user,
            module="management", target_type="management_client_intake", target_id=str(row.id),
            details={"client_code": row.client_code, "source_person_name": row.source_person_name},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Client ID already exists") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


@router.put("/{client_id}", response_model=ManagementClientResponse)
def update_management_client(
    client_id: int, payload: ManagementClientInput, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _management_only(auth)
    row = db.get(ManagementClientIntake, client_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Management client not found")
    _check_code(db, payload.client_code, exclude_id=row.id)
    linked_finance_client = db.scalar(select(FinanceClient).where(FinanceClient.client_code == row.client_code))
    if linked_finance_client is not None and linked_finance_client.source_team == "management":
        if payload.client_code != row.client_code:
            raise HTTPException(status_code=409, detail="Client ID cannot change after Finance has created a management project")
        # Keep the linked Finance invoice/client snapshot fields in sync without changing
        # the original management source, BD ownership or historical invoice records.
        linked_finance_client.client_name = payload.client_name
        linked_finance_client.client_email = payload.client_email
        linked_finance_client.contact_person_name = payload.contact_person_name
        linked_finance_client.contact_person_phone = payload.contact_person_phone or "Not provided"
        linked_finance_client.address = payload.address
        linked_finance_client.country = payload.country
        linked_finance_client.gst_number = payload.gst_number
        linked_finance_client.description = payload.work_description
        linked_finance_client.updated_by_id = auth.user.id
        if linked_finance_client.master_profile is not None:
            linked_finance_client.master_profile.organization_email = payload.organization_email
            linked_finance_client.master_profile.contact_person_email = payload.contact_person_email
            linked_finance_client.master_profile.task = payload.work_description
            linked_finance_client.master_profile.updated_by_id = auth.user.id
    for field, value in _values(payload).items():
        setattr(row, field, value)
    row.updated_by_id = auth.user.id
    try:
        record_audit(
            db, event_type="MANAGEMENT_CLIENT_UPDATED", request=request, user=auth.user,
            module="management", target_type="management_client_intake", target_id=str(row.id),
            details={"client_code": row.client_code, "source_person_name": row.source_person_name},
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Client ID already exists") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return row


def _approval_flags(
    db: Session, *, link: ManagementProjectLink, workflow_status: str,
    summary: dict, viewer_user_id: int,
) -> dict:
    intake = db.get(ManagementClientIntake, link.management_client_id)
    workflow = db.get(ProjectWorkflow, link.project_id)
    approved = management_source_approval_event(db, link.project_id) is not None
    fully_delivered = (
        summary["work_units"] > 0 and summary["rework_count"] == 0
        and all(summary["stages"][stage]["completed"] == summary["work_units"]
                for stage in ("production", "qc", "qa", "delivery"))
    )
    return {
        "source_approved": approved,
        "can_approve": bool(
            intake is not None and intake.created_by_id == viewer_user_id
            and workflow is not None and workflow.operational_completed_at is not None
            and workflow_status == APPROVAL_PENDING and fully_delivered and not approved
        ),
    }


@router.post("/projects/{project_id}/approve")
def approve_management_project(
    project_id: int, request: Request,
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    """Only the original source may approve a fully delivered Management project."""
    _management_only(auth)
    link = db.get(ManagementProjectLink, project_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Management project not found")
    intake = db.get(ManagementClientIntake, link.management_client_id)
    if intake is None or intake.created_by_id != auth.user.id:
        raise HTTPException(status_code=403, detail="Only the original Management source may approve this project")
    try:
        workflow = db.scalar(select(ProjectWorkflow).where(
            ProjectWorkflow.project_id == project_id,
        ).with_for_update())
        if workflow is None:
            raise HTTPException(status_code=404, detail="Project workflow not found")
        if workflow.status not in {APPROVAL_PENDING, FEEDBACK_NOT_SENT, READY_FOR_BILLING}:
            raise HTTPException(status_code=409, detail="Project is not awaiting Management approval")
        if workflow.operational_completed_at is None:
            raise HTTPException(status_code=409, detail="Project has not completed operational delivery")
        if management_source_approval_event(db, project_id) is not None:
            raise HTTPException(status_code=409, detail="This project is already approved")
        if db.scalar(select(ProjectInvoice.id).where(ProjectInvoice.project_id == project_id).limit(1)) is not None:
            raise HTTPException(status_code=409, detail="Existing invoices require manual review before approval")
        packages = _project_packages(db, [project_id]).get(project_id, [])
        aggregates = file_aggregates_for_packages(db, [package.id for package in packages])
        summary = _tracking_rollup(packages, aggregates)
        if not _approval_flags(db, link=link, workflow_status=APPROVAL_PENDING,
                               summary=summary, viewer_user_id=auth.user.id)["can_approve"]:
            raise HTTPException(status_code=409, detail="Production, QC, QA and Delivery must all be completed")
        _transition(
            db, workflow=workflow, actor=auth.user, status=READY_FOR_BILLING,
            event_type=MANAGEMENT_SOURCE_APPROVED_EVENT,
            title="Original Management source approved project for billing",
            comments=f"Approved by {auth.user.full_name} after Production, QC, QA and Delivery.",
        )
        record_audit(
            db, event_type="MANAGEMENT_PROJECT_SOURCE_APPROVED", request=request, user=auth.user,
            module="management", target_type="finance_project", target_id=str(project_id),
            details={"project_code": db.get(FinanceProject, project_id).project_code,
                     "management_client_id": link.management_client_id,
                     "approved_by_user_id": auth.user.id},
        )
        db.commit()
        return {"project_id": project_id, "workflow_status": READY_FOR_BILLING,
                "approved_by_user_id": auth.user.id}
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


# Management tracking and project-specific source approval share the same records.
@router.get("/project-tracking")
def management_client_project_tracking(
    db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth),
):
    _management_only(auth)
    links = db.scalars(select(ManagementProjectLink).order_by(
        ManagementProjectLink.created_at.desc(), ManagementProjectLink.project_id.desc(),
    )).all()
    project_ids = [link.project_id for link in links]
    packages_by_project = _project_packages(db, project_ids)
    all_packages = [package for packages in packages_by_project.values() for package in packages]
    aggregates = file_aggregates_for_packages(db, [package.id for package in all_packages])
    last_activities = {}
    if project_ids:
        last_activities = dict(db.execute(select(
            WorkPackageItemActivity.project_id, func.max(WorkPackageItemActivity.updated_at),
        ).where(WorkPackageItemActivity.project_id.in_(project_ids)).group_by(
            WorkPackageItemActivity.project_id,
        )).all())

    projects = []
    by_client = {}
    for link in links:
        project = _project_payload(db, link)
        summary = _tracking_rollup(
            packages_by_project[link.project_id], aggregates,
            last_activities.get(link.project_id),
        )
        projects.append({**project, "tracking": summary, **_approval_flags(
            db, link=link, workflow_status=project["workflow_status"],
            summary=summary, viewer_user_id=auth.user.id,
        )})
        by_client.setdefault(link.management_client_id, []).append(summary)

    clients = {}
    for client_id, summaries in by_client.items():
        work_units = sum(item["work_units"] for item in summaries)
        stage_completed = sum(
            item["stages"][stage]["completed"]
            for item in summaries for stage in ("production", "qc", "qa", "delivery")
        )
        clients[str(client_id)] = {
            "project_count": len(summaries),
            "active_projects": sum(
                item["work_units"] == 0 or
                item["stages"]["delivery"]["completed"] < item["work_units"]
                for item in summaries
            ),
            "completed_projects": sum(
                item["work_units"] > 0 and
                item["stages"]["delivery"]["completed"] == item["work_units"]
                for item in summaries
            ),
            "overall_percent": round(100 * stage_completed / (4 * work_units), 1)
            if work_units else 0.0,
            "work_units": work_units,
        }
    return {"as_of": utc_now().isoformat(), "projects": projects, "clients": clients}


@router.get("/project-tracking/{project_id}")
def management_client_project_tracking_detail(
    project_id: int, db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _management_only(auth)
    link = db.get(ManagementProjectLink, project_id)
    if link is None:
        raise HTTPException(status_code=404, detail="Management project not found")
    packages = _project_packages(db, [project_id]).get(project_id, [])
    package_ids = [package.id for package in packages]
    aggregates = file_aggregates_for_packages(db, package_ids)
    rows = build_item_rows(db, package_ids)
    active_packages = {row["work_package_id"] for row in rows if row["is_active"]}
    package_by_id = {package.id: package for package in packages}
    file_rows = []
    for row in rows:
        package = package_by_id[row["work_package_id"]]
        file_rows.append({
            "work_package_item_id": row["work_package_item_id"],
            "package_code": package.package_code,
            "item_number": row["item_number"], "item_name": row.get("item_name"),
            "is_active": row["is_active"], "tracking_basis": "file_activity",
            "production": "rework" if row.get("production_rework_pending") else row["production_status"],
            "qc": row["qc_status"], "qa": row["qa_status"],
            "delivery": row["delivery_status"],
            "production_completed_at": row.get("production_completed_at"),
            "qc_completed_at": row.get("qc_end"),
            "qa_completed_at": row.get("qa_end"),
            "delivered_at": row.get("delivery_at"),
            "production_employee": row.get("production_employee"),
            "qc_employee": row.get("qc_employee"),
            "qa_employee": row.get("qa_employee"),
        })
    for package in packages:
        if package.id in active_packages:
            continue
        # Area-only legacy work is counted once; inactive-only files are not.
        if any(row["work_package_id"] == package.id for row in rows):
            continue
        stage = (package.current_stage or "").lower()
        legacy = _legacy_stage_counts(package)
        file_rows.append({
            "work_package_item_id": None,
            "package_code": package.package_code,
            "item_number": package.package_code,
            "item_name": package.package_name,
            "is_active": True, "tracking_basis": "legacy_area",
            "production": "rework" if stage == "production_rework" else
                ("completed" if legacy["production"] else package.production_state),
            "qc": "passed" if legacy["qc"] else package.qc_state,
            "qa": "passed" if legacy["qa"] else package.qa_state,
            "delivery": "delivered" if legacy["delivery"] else "pending",
            "production_completed_at": package.production_completed_at.isoformat()
                if package.production_completed_at else None,
            "qc_completed_at": package.qc_submitted_at.isoformat()
                if package.qc_submitted_at else None,
            "qa_completed_at": package.qa_submitted_at.isoformat()
                if package.qa_submitted_at else None,
            "delivered_at": package.delivered_at.isoformat() if package.delivered_at else None,
            "production_employee": None, "qc_employee": None, "qa_employee": None,
        })
    activity_at = db.scalar(select(func.max(WorkPackageItemActivity.updated_at)).where(
        WorkPackageItemActivity.project_id == project_id,
    ))
    project = _project_payload(db, link)
    summary = _tracking_rollup(packages, aggregates, activity_at)
    return {
        "project_id": project_id,
        "as_of": utc_now().isoformat(),
        "project": {**project, **_approval_flags(
            db, link=link, workflow_status=project["workflow_status"],
            summary=summary, viewer_user_id=auth.user.id,
        )},
        "summary": summary,
        "files": file_rows,
    }
