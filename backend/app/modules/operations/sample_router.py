from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.employee_portal.service import record_audit
from app.modules.operations.models import BDOpportunity
from app.modules.operations.sample_models import TechnicalSampleRequest
from app.modules.operations.sample_schemas import (
    TechnicalSampleClientDecision,
    TechnicalSampleRequestCreate,
    TechnicalSampleSubmit,
)
from app.modules.operations.sample_service import (
    create_bd_sample_submission_notification,
    create_finance_client_approved_notifications,
    create_revision_team_notifications,
    create_sample_request,
    create_sample_team_notifications,
    deliver_finance_client_approved_emails,
    deliver_revision_team_emails,
    deliver_sample_team_emails,
    record_sample_client_decision,
    sample_dashboard_payload,
    sample_request_payload,
    send_sample_to_client_review,
    start_sample_department,
    submit_sample_department,
)

router = APIRouter(tags=["BD Multi-Team Technical Samples"])
TECHNICAL_ROLES = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _exact_roles(auth: CurrentAuth, *roles: str) -> None:
    if _role(auth) not in set(roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permission for this Sample Workflow action")


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
    target_id: int | None = None,
    details: dict | None = None,
) -> None:
    record_audit(
        db,
        event_type=event_type,
        request=request,
        user=auth.user,
        module="operations_sample_workflow",
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details or {},
    )


@router.get("/samples/dashboard")
def technical_sample_dashboard(
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd", *sorted(TECHNICAL_ROLES), "management", "admin")
    try:
        return sample_dashboard_payload(db, actor=auth.user, effective_role=_role(auth))
    except Exception as exc:
        raise _write_error(exc) from exc


@router.post("/bd/opportunities/{opportunity_id}/samples")
def bd_create_multi_team_sample_request(
    opportunity_id: int,
    payload: TechnicalSampleRequestCreate,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    opportunity = db.get(BDOpportunity, opportunity_id)
    if opportunity is None or opportunity.owner_user_id != auth.user.id:
        raise HTTPException(status_code=404, detail="BD opportunity not found")
    try:
        sample = create_sample_request(db, opportunity=opportunity, actor=auth.user, payload=payload)
        _audit(
            request,
            db,
            auth,
            "BD_MULTI_TEAM_SAMPLE_REQUESTED",
            "technical_sample_request",
            sample.id,
            {"opportunity_id": opportunity.id, "departments": payload.department_codes},
        )
        sample_id = sample.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    # Notifications and email are deliberately post-commit. They can never roll
    # back the sample request or its selected department rows.
    notification_count = 0
    try:
        notification_count = create_sample_team_notifications(db, sample_request_id=sample_id)
        db.commit()
    except Exception:
        db.rollback()
    try:
        email_sent, email_failed = deliver_sample_team_emails(db, sample_request_id=sample_id)
    except Exception:
        email_sent, email_failed = 0, 0

    saved = db.get(TechnicalSampleRequest, sample_id)
    from app.modules.operations.technical_routing_service import current_routing_mode, live_routing_enabled
    live = live_routing_enabled(db)
    return {
        "sample_request": sample_request_payload(db, saved, role="bd") if saved else None,
        "technical_notifications_created": notification_count,
        "technical_email_sent": email_sent,
        "technical_email_failed": email_failed,
        "routing_mode": current_routing_mode(db),
        "demo_notifications_created": notification_count if not live else 0,
        "demo_email_sent": email_sent if not live else 0,
        "demo_email_failed": email_failed if not live else 0,
    }


@router.post("/samples/{sample_request_id}/start")
def technical_team_start_sample(
    sample_request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    sample = db.get(TechnicalSampleRequest, sample_request_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    try:
        department = start_sample_department(db, sample_request=sample, actor=auth.user, effective_role=_role(auth))
        _audit(
            request,
            db,
            auth,
            "TECHNICAL_SAMPLE_STARTED",
            "technical_sample_request",
            sample.id,
            {"department_code": department.department_code},
        )
        db.commit()
        saved = db.get(TechnicalSampleRequest, sample.id)
        return sample_request_payload(db, saved, role=_role(auth)) if saved else {"id": sample.id}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/samples/{sample_request_id}/submit")
def technical_team_submit_sample(
    sample_request_id: int,
    payload: TechnicalSampleSubmit,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, *sorted(TECHNICAL_ROLES))
    sample = db.get(TechnicalSampleRequest, sample_request_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    try:
        submission = submit_sample_department(
            db,
            sample_request=sample,
            actor=auth.user,
            effective_role=_role(auth),
            payload=payload,
        )
        department_code = submission.department.department_code
        attempt_no = submission.attempt_no
        _audit(
            request,
            db,
            auth,
            "TECHNICAL_SAMPLE_SUBMITTED",
            "technical_sample_request",
            sample.id,
            {"department_code": department_code, "attempt_no": attempt_no},
        )
        sample_id = sample.id
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    bd_notifications = 0
    try:
        bd_notifications = create_bd_sample_submission_notification(
            db,
            sample_request_id=sample_id,
            department_code=department_code,
            attempt_no=attempt_no,
        )
        db.commit()
    except Exception:
        db.rollback()
    saved = db.get(TechnicalSampleRequest, sample_id)
    return {
        "sample_request": sample_request_payload(db, saved, role=_role(auth)) if saved else None,
        "bd_notifications_created": bd_notifications,
    }


@router.post("/samples/{sample_request_id}/client-review")
def bd_send_sample_to_client(
    sample_request_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    sample = db.get(TechnicalSampleRequest, sample_request_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    try:
        sample = send_sample_to_client_review(db, sample_request=sample, actor=auth.user)
        _audit(
            request,
            db,
            auth,
            "BD_SAMPLE_SENT_TO_CLIENT_REVIEW",
            "technical_sample_request",
            sample.id,
            {"status": sample.status},
        )
        db.commit()
        saved = db.get(TechnicalSampleRequest, sample.id)
        return sample_request_payload(db, saved, role="bd") if saved else {"id": sample.id}
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc


@router.post("/samples/{sample_request_id}/client-decision")
def bd_record_client_sample_decision(
    sample_request_id: int,
    payload: TechnicalSampleClientDecision,
    request: Request,
    db: Session = Depends(get_db),
    auth: CurrentAuth = Depends(get_current_auth),
):
    _exact_roles(auth, "bd")
    sample = db.get(TechnicalSampleRequest, sample_request_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample request not found")
    try:
        sample = record_sample_client_decision(db, sample_request=sample, actor=auth.user, payload=payload)
        sample_id = sample.id
        decision = payload.decision
        _audit(
            request,
            db,
            auth,
            "BD_SAMPLE_CLIENT_APPROVED" if decision == "approved" else "BD_SAMPLE_CLIENT_REVISION",
            "technical_sample_request",
            sample.id,
            {"decision": decision, "revision_departments": payload.revision_department_codes},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        raise _write_error(exc) from exc

    response_meta = {
        "revision_notifications_created": 0,
        "revision_email_sent": 0,
        "revision_email_failed": 0,
        "finance_notifications_created": 0,
        "finance_email_sent": 0,
        "finance_email_failed": 0,
    }
    if decision == "revision":
        try:
            response_meta["revision_notifications_created"] = create_revision_team_notifications(
                db, sample_request_id=sample_id
            )
            db.commit()
        except Exception:
            db.rollback()
        try:
            sent, failed = deliver_revision_team_emails(db, sample_request_id=sample_id)
            response_meta["revision_email_sent"] = sent
            response_meta["revision_email_failed"] = failed
        except Exception:
            pass
    else:
        # Finance is notified only after the client approves the technical sample.
        # This replaces the earlier V7.0.14 proof-of-concept notification timing.
        try:
            response_meta["finance_notifications_created"] = create_finance_client_approved_notifications(
                db, sample_request_id=sample_id
            )
            db.commit()
        except Exception:
            db.rollback()
        try:
            sent, failed = deliver_finance_client_approved_emails(db, sample_request_id=sample_id)
            response_meta["finance_email_sent"] = sent
            response_meta["finance_email_failed"] = failed
        except Exception:
            pass

    saved = db.get(TechnicalSampleRequest, sample_id)
    return {
        "sample_request": sample_request_payload(db, saved, role="bd") if saved else None,
        **response_meta,
    }
