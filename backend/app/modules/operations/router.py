from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User
from app.modules.employee_portal.service import record_audit
from app.modules.operations.models import BDOpportunity, OrthoProjectMember, OrthoProjectProfile
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
    OrthoWorkActionRequest,
    OrthoWorkPackageAssignments,
    OrthoWorkPackageCreate,
)
from app.modules.operations.service import (
    ADMIN_ROLE,
    BD_ROLE,
    EMPLOYEE_ROLE,
    MANAGEMENT_ROLE,
    ORTHO_ROLE,
    activate_ortho_project,
    active_project_team_members,
    bd_dashboard_payload,
    bd_opportunity_payload,
    corporate_summary_payload,
    create_bd_opportunity,
    configure_project_team,
    create_work_package,
    finalize_delivery,
    get_visible_work_package,
    is_effective_pm,
    link_bd_project,
    normalize_role,
    ortho_dashboard_payload,
    project_payload,
    record_daily_update,
    review_package,
    send_ortho_assignment_email,
    submit_to_qc,
    sync_bd_progress_stage,
    update_bd_stage,
    update_package_assignments,
    upsert_project_member,
    work_action,
)

router = APIRouter(prefix="/operations", tags=["BD + Ortho/LiDAR Operations"])


def _role(auth: CurrentAuth) -> str:
    return normalize_role(auth.effective_role)


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this Operations action")


def _write_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _audit(request: Request, db: Session, auth: CurrentAuth, event_type: str, target_type: str, target_id: int | None = None, details: dict | None = None) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations",
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/bd/dashboard")
def bd_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, BD_ROLE, MANAGEMENT_ROLE, ADMIN_ROLE)
    return bd_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))


@router.post("/bd/opportunities")
def bd_create_opportunity(
    payload: BDOpportunityCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, BD_ROLE)
    try:
        row = create_bd_opportunity(db, actor=auth.user, payload=payload)
        _audit(request, db, auth, "BD_OPPORTUNITY_CREATED", "bd_opportunity", row.id, {"code": row.opportunity_code})
        db.commit()
        db.refresh(row)
        return bd_opportunity_payload(db, row)
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.patch("/bd/opportunities/{opportunity_id}/stage")
def bd_change_stage(
    opportunity_id: int,
    payload: BDStageUpdate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, BD_ROLE)
    row = db.get(BDOpportunity, opportunity_id)
    if row is None or row.owner_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="BD opportunity not found")
    try:
        old = row.stage
        row = update_bd_stage(db, opportunity=row, actor=auth.user, payload=payload)
        _audit(request, db, auth, "BD_OPPORTUNITY_STAGE_CHANGED", "bd_opportunity", row.id, {"from": old, "to": row.stage})
        db.commit()
        db.refresh(row)
        return bd_opportunity_payload(db, row)
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/bd/opportunities/{opportunity_id}/link-project")
def bd_link_project(
    opportunity_id: int,
    payload: BDProjectLink,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, BD_ROLE)
    row = db.get(BDOpportunity, opportunity_id)
    if row is None or row.owner_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="BD opportunity not found")
    try:
        row, profile = link_bd_project(db, opportunity=row, actor=auth.user, payload=payload)
        _audit(request, db, auth, "BD_FINANCE_PROJECT_LINKED", "bd_opportunity", row.id, {"project_id": profile.project_id})
        db.commit()
        db.refresh(row)
        return {"opportunity": bd_opportunity_payload(db, row), "ortho_project_id": profile.project_id}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.get("/ortho/dashboard")
def ortho_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE, MANAGEMENT_ROLE, ADMIN_ROLE)
    return ortho_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))


@router.get("/ortho/projects")
def ortho_projects(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE, MANAGEMENT_ROLE, ADMIN_ROLE)
    return ortho_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))["projects"]


@router.post("/ortho/projects/activate")
def ortho_activate_project(
    payload: OrthoProjectActivate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    try:
        profile = activate_ortho_project(db, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_PROJECT_ACTIVATED", "ortho_project", profile.project_id)
        db.commit()
        full = db.get(OrthoProjectProfile, profile.project_id)
        return project_payload(db, full, viewer=auth.user) if full else {"project_id": profile.project_id}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/projects/{project_id}/members")
def ortho_upsert_member(
    project_id: int,
    payload: OrthoMemberUpsert,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    """Compatibility endpoint: save the assignment first; email is best-effort only.

    V7.0.13 intentionally separates operational assignment from SMTP delivery so a mail
    outage can never roll back the employee's Ortho responsibility.
    """
    _exact_roles(auth, ORTHO_ROLE)
    if db.get(OrthoProjectProfile, project_id) is None:
        raise HTTPException(status_code=404, detail="Ortho project not found")
    try:
        row = upsert_project_member(db, project_id=project_id, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_PROJECT_MEMBER_UPDATED", "ortho_project", project_id, {"user_id": row.user_id, "member_role": payload.member_role, "is_active": payload.is_active, "assignment_email_requested": bool(payload.send_email and row.is_active)})
        db.commit()
        row_id = row.id
        row_user_id = row.user_id
        row_role = row.member_role
        row_active = bool(row.is_active)
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    email_sent = False
    email_warning = None
    if payload.send_email and row_active:
        try:
            persisted = db.get(OrthoProjectMember, row_id)
            if persisted is not None:
                send_ortho_assignment_email(db, project_id=project_id, member=persisted)
                email_sent = True
        except Exception:
            db.rollback()
            email_warning = "Assignment saved, but the email could not be sent. Check the ERP SMTP configuration and use Send Assignment Emails to retry."

    assigned_user = db.get(User, row_user_id)
    return {
        "id": row_id,
        "project_id": project_id,
        "user_id": row_user_id,
        "user_name": assigned_user.full_name if assigned_user else None,
        "user_email": assigned_user.email if assigned_user else None,
        "member_role": row_role,
        "is_active": row_active,
        "email_sent": email_sent,
        "email_warning": email_warning,
    }


@router.put("/ortho/projects/{project_id}/team")
def ortho_configure_team(
    project_id: int,
    payload: OrthoTeamSetup,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    profile = db.get(OrthoProjectProfile, project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Ortho project not found")
    try:
        rows = configure_project_team(db, project_id=project_id, actor=auth.user, payload=payload)
        details = {row.member_role: row.user_id for row in rows}
        details["apply_to_unassigned_packages"] = payload.apply_to_unassigned_packages
        _audit(request, db, auth, "ORTHO_PROJECT_TEAM_CONFIGURED", "ortho_project", project_id, details)
        db.commit()
        full = db.get(OrthoProjectProfile, project_id)
        return {
            "message": "Project team saved. Email delivery is separate and cannot block these assignments.",
            "project": project_payload(db, full, viewer=auth.user) if full else None,
        }
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/projects/{project_id}/team/emails")
def ortho_send_team_emails(
    project_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    if db.get(OrthoProjectProfile, project_id) is None:
        raise HTTPException(status_code=404, detail="Ortho project not found")
    if not is_effective_pm(db, project_id=project_id, user_id=auth.user.id):
        raise HTTPException(status_code=403, detail="Only this project's Ortho Project Manager can send team assignment emails")

    members = active_project_team_members(db, project_id=project_id)
    if not members:
        raise HTTPException(status_code=422, detail="Save the Project Team before sending assignment emails")

    sent_roles: list[str] = []
    failed_roles: list[str] = []
    for member in members:
        role = member.member_role
        try:
            send_ortho_assignment_email(db, project_id=project_id, member=member)
            sent_roles.append(role)
        except Exception:
            db.rollback()
            failed_roles.append(role)

    try:
        _audit(request, db, auth, "ORTHO_PROJECT_TEAM_EMAILS_REQUESTED", "ortho_project", project_id, {"sent_roles": sent_roles, "failed_roles": failed_roles})
        db.commit()
    except Exception:
        db.rollback()

    return {
        "sent": len(sent_roles),
        "failed": len(failed_roles),
        "sent_roles": sent_roles,
        "failed_roles": failed_roles,
        "message": (
            "Assignment emails sent."
            if not failed_roles
            else "Project team remains saved. One or more emails could not be sent; check the ERP SMTP configuration and retry later."
        ),
    }


@router.post("/ortho/projects/{project_id}/work-packages")
def ortho_create_work_package(
    project_id: int,
    payload: OrthoWorkPackageCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    try:
        row = create_work_package(db, project_id=project_id, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_WORK_PACKAGE_CREATED", "ortho_work_package", row.id, {"project_id": project_id, "package_code": row.package_code})
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "package_code": row.package_code, "current_stage": row.current_stage}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.patch("/ortho/work-packages/{work_package_id}/assignments")
def ortho_update_assignments(
    work_package_id: int,
    payload: OrthoWorkPackageAssignments,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        row = update_package_assignments(db, work_package=row, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_WORK_PACKAGE_ASSIGNMENTS_UPDATED", "ortho_work_package", row.id)
        db.commit()
        return {"id": row.id, "project_id": row.project_id, "current_stage": row.current_stage}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/daily-update")
def ortho_daily_update(
    work_package_id: int,
    payload: OrthoDailyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        update = record_daily_update(db, work_package=row, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_DAILY_UPDATE_RECORDED", "ortho_work_package", row.id, {"daily_update_id": update.id, "update_date": update.update_date.isoformat(), "status": update.status})
        db.commit()
        return {
            "id": update.id,
            "work_package_id": update.work_package_id,
            "update_date": update.update_date.isoformat(),
            "achieved_area": float(update.achieved_area) if update.achieved_area is not None else None,
            "progress_percent": float(update.progress_percent) if update.progress_percent is not None else None,
            "hours_spent": float(update.hours_spent) if update.hours_spent is not None else None,
            "status": update.status,
            "blockers": update.blockers,
            "remarks": update.remarks,
            "updated_by_id": update.updated_by_id,
        }
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/work-action")
def ortho_work_action(
    work_package_id: int,
    payload: OrthoWorkActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        row = work_action(db, work_package=row, actor=auth.user, action=payload.action)
        _audit(request, db, auth, f"ORTHO_WORK_{payload.action.upper()}", "ortho_work_package", row.id)
        db.commit()
        return {"id": row.id, "current_stage": row.current_stage, "production_state": row.production_state}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/submit-qc")
def ortho_submit_qc(
    work_package_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        row = submit_to_qc(db, work_package=row, actor=auth.user)
        sync_bd_progress_stage(db, row.project_id)
        _audit(request, db, auth, "ORTHO_SUBMITTED_TO_QC", "ortho_work_package", row.id)
        db.commit()
        return {"id": row.id, "current_stage": row.current_stage, "qc_state": row.qc_state}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/qc")
def ortho_qc_review(
    work_package_id: int,
    payload: OrthoReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        row = review_package(db, work_package=row, actor=auth.user, review_type="qc", payload=payload)
        sync_bd_progress_stage(db, row.project_id)
        _audit(request, db, auth, f"ORTHO_QC_{payload.decision.upper()}", "ortho_work_package", row.id)
        db.commit()
        return {"id": row.id, "current_stage": row.current_stage, "qc_state": row.qc_state, "qa_state": row.qa_state}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/work-packages/{work_package_id}/qa")
def ortho_qa_review(
    work_package_id: int,
    payload: OrthoReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE, EMPLOYEE_ROLE)
    row = get_visible_work_package(db, work_package_id=work_package_id, actor=auth.user, effective_role=_role(auth))
    if row is None:
        raise HTTPException(status_code=404, detail="Work package not found")
    try:
        row = review_package(db, work_package=row, actor=auth.user, review_type="qa", payload=payload)
        sync_bd_progress_stage(db, row.project_id)
        _audit(request, db, auth, f"ORTHO_QA_{payload.decision.upper()}", "ortho_work_package", row.id)
        db.commit()
        return {"id": row.id, "current_stage": row.current_stage, "qa_state": row.qa_state}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/ortho/projects/{project_id}/final-delivery")
def ortho_final_delivery(
    project_id: int,
    payload: OrthoDeliveryRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, ORTHO_ROLE)
    profile = db.get(OrthoProjectProfile, project_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Ortho project not found")
    try:
        delivery = finalize_delivery(db, profile=profile, actor=auth.user, payload=payload)
        _audit(request, db, auth, "ORTHO_FINAL_DELIVERY", "ortho_project", project_id, {"delivery_id": delivery.id, "package_count": delivery.package_count})
        db.commit()
        return {"project_id": project_id, "delivery_id": delivery.id, "package_count": delivery.package_count, "delivered_at": delivery.delivered_at.isoformat()}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.get("/corporate-summary")
def corporate_summary(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, MANAGEMENT_ROLE, ADMIN_ROLE)
    return corporate_summary_payload(db)
