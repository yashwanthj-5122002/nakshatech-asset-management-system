from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.employee_portal.service import send_email
from app.modules.notifications.service import create_global_notification, resolve_recipient_users
from app.modules.operations.models import BDOpportunity, BDOpportunityEvent
from app.modules.operations.sample_models import (
    TechnicalSampleDepartment,
    TechnicalSampleRequest,
    TechnicalSampleSubmission,
)
from app.modules.operations.sample_schemas import (
    TechnicalSampleClientDecision,
    TechnicalSampleRequestCreate,
    TechnicalSampleSubmit,
)
from app.modules.operations.service import (
    TECHNICAL_DEPARTMENT_LABELS,
    TECHNICAL_DEPARTMENT_ROLE_MAP,
    TECHNICAL_ROLE_DEPARTMENT_MAP,
    normalize_role,
)
from app.modules.operations.technical_routing_service import (
    current_routing_mode,
    is_real_department_member,
    live_routing_enabled,
    real_department_users,
)

logger = logging.getLogger(__name__)

SAMPLE_REQUEST_STATUSES = {
    "requested",
    "in_progress",
    "ready_for_client_review",
    "client_review",
    "revision_requested",
    "client_approved",
}
SAMPLE_DEPARTMENT_STATUSES = {
    "requested",
    "in_progress",
    "submitted",
    "revision_requested",
    "client_approved",
}

# V7.0.16 Phase 2 intentionally uses only the reserved local/UAT demo technical
# accounts. Real team email addresses are integrated only after the workflow is
# completely validated and explicitly approved for production use.
DEMO_DEPARTMENT_EMAILS = {
    "ortho": "ortho.demo@nakshatech.com",
    "lidar": "lidar.demo@nakshatech.com",
    "civil": "civil.demo@nakshatech.com",
    "laser_scanning": "laser.scanning.demo@nakshatech.com",
    "bim": "bim.demo@nakshatech.com",
    "mobile_mapping": "mobile.mapping.demo@nakshatech.com",
}
DEMO_EMPLOYEE_IDS = {
    "ortho": "DEMO-V715-ORTHO-PM",
    "lidar": "DEMO-V715-LIDAR-PM",
    "civil": "DEMO-V715-CIVIL-PM",
    "laser_scanning": "DEMO-V715-LASER-PM",
    "bim": "DEMO-V715-BIM-PM",
    "mobile_mapping": "DEMO-V715-MOBILE-PM",
}


def _sample_code(db: Session) -> str:
    year = utc_now().year
    prefix = f"SMP-{year}-"
    codes = list(db.scalars(select(TechnicalSampleRequest.request_code).where(
        TechnicalSampleRequest.request_code.like(f"{prefix}%")
    )).all())
    highest = 0
    for code in codes:
        match = re.search(r"(\d+)$", code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{prefix}{highest + 1:04d}"


def _demo_user_for_department(db: Session, department_code: str) -> User:
    email = DEMO_DEPARTMENT_EMAILS.get(department_code)
    employee_id = DEMO_EMPLOYEE_IDS.get(department_code)
    expected_role = TECHNICAL_DEPARTMENT_ROLE_MAP.get(department_code)
    if not email or not employee_id or not expected_role:
        raise ValueError(f"Unsupported technical department: {department_code}")
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if (
        user is None
        or user.employee_id != employee_id
        or normalize_role(user.role) != expected_role
        or not user.is_active
        or user.account_status != "active"
    ):
        raise ValueError(
            f"Phase 2 demo account for {TECHNICAL_DEPARTMENT_LABELS[department_code]} is missing or inactive: {email}"
        )
    return user


def _sample_recipients(db: Session, department_code: str) -> list[User]:
    if live_routing_enabled(db):
        users = real_department_users(db, department_code=department_code, purpose="sample")
        if not users:
            raise ValueError(
                f"No live Sample recipient is configured for {TECHNICAL_DEPARTMENT_LABELS[department_code]}"
            )
        return users
    return [_demo_user_for_department(db, department_code)]


def _assert_sample_actor(db: Session, *, department_code: str, actor: User) -> None:
    if live_routing_enabled(db):
        if not is_real_department_member(
            db, department_code=department_code, user_id=actor.id, purpose="sample"
        ):
            raise PermissionError(
                f"Only an active Phase 7 {TECHNICAL_DEPARTMENT_LABELS[department_code]} Sample-responsible directory member can work on this sample"
            )
        return
    expected_demo = _demo_user_for_department(db, department_code)
    if actor.id != expected_demo.id:
        raise PermissionError("Phase 2 UAT sample actions are restricted to the reserved demo technical account")


def _sample_routing_line(db: Session, department_code: str) -> str:
    if live_routing_enabled(db):
        recipients = _sample_recipients(db, department_code)
        return "Phase 7 production routing: " + ", ".join(user.email for user in recipients)
    return "Phase 2 UAT: this request is routed only to the reserved demo technical account."


def _ensure_bd_owner(opportunity: BDOpportunity, actor: User) -> None:
    if opportunity.owner_user_id != actor.id:
        raise PermissionError("Only the BD owner can manage this opportunity's sample workflow")


def _department_for_role(sample_request: TechnicalSampleRequest, role: str) -> TechnicalSampleDepartment | None:
    department_code = TECHNICAL_ROLE_DEPARTMENT_MAP.get(normalize_role(role))
    if not department_code:
        return None
    return next((row for row in sample_request.departments if row.department_code == department_code), None)


def create_sample_request(
    db: Session,
    *,
    opportunity: BDOpportunity,
    actor: User,
    payload: TechnicalSampleRequestCreate,
) -> TechnicalSampleRequest:
    _ensure_bd_owner(opportunity, actor)
    if opportunity.linked_project_id is not None:
        raise ValueError("Sample requests belong to the pre-project phase and cannot be created after a Finance Project ID is linked")
    if opportunity.stage in {"finance_handoff", "project_linked", "production", "delivery_ready", "delivered", "closed"}:
        raise ValueError("This opportunity has already moved beyond the technical sample phase")
    existing = db.scalar(select(TechnicalSampleRequest).where(
        TechnicalSampleRequest.opportunity_id == opportunity.id
    ))
    if existing is not None:
        raise ValueError("This opportunity already has a technical sample request; use the existing request and revision cycle")

    # Validate routing availability before creating any business rows. In demo mode
    # this confirms the reserved account; after Phase 7 activation it confirms at
    # least one real Sample-responsible directory member for every selected team.
    for department_code in payload.department_codes:
        _sample_recipients(db, department_code)

    row = TechnicalSampleRequest(
        request_code=_sample_code(db),
        opportunity_id=opportunity.id,
        title=payload.title.strip(),
        instructions=payload.instructions.strip(),
        due_date=payload.due_date,
        status="requested",
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    for department_code in payload.department_codes:
        db.add(TechnicalSampleDepartment(
            sample_request_id=row.id,
            department_code=department_code,
            status="requested",
        ))
    opportunity.stage = "technical_sample"
    opportunity.updated_at = utc_now()
    db.add(BDOpportunityEvent(
        opportunity_id=opportunity.id,
        action="multi_team_sample_requested",
        from_stage="opportunity",
        to_stage="technical_sample",
        comments="Sample requested from: " + ", ".join(
            TECHNICAL_DEPARTMENT_LABELS[code] for code in payload.department_codes
        ),
        actor_user_id=actor.id,
    ))
    db.flush()
    return row


def _sample_request_message(db: Session, row: TechnicalSampleRequest, department_code: str) -> str:
    opportunity = db.get(BDOpportunity, row.opportunity_id)
    return "\n".join([
        f"Sample Request: {row.request_code} - {row.title}",
        f"Opportunity: {opportunity.opportunity_code if opportunity else row.opportunity_id}",
        f"Prospect / Client: {(opportunity.client_name_snapshot if opportunity else None) or 'Not specified'}",
        f"Department: {TECHNICAL_DEPARTMENT_LABELS[department_code]}",
        f"Requirement: {(opportunity.requirement if opportunity else 'Not available')}",
        f"Sample Instructions: {row.instructions}",
        f"Due Date: {row.due_date.isoformat() if row.due_date else 'Not specified'}",
        _sample_routing_line(db, department_code),
    ])


def create_sample_team_notifications(db: Session, *, sample_request_id: int) -> int:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0
    created = 0
    for department in row.departments:
        for user in _sample_recipients(db, department.department_code):
            created += len(create_global_notification(
                db,
                event_type="technical.sample.requested",
                title=f"Technical sample requested: {row.request_code}",
                message=_sample_request_message(db, row, department.department_code),
                category="system",
                target_url="/sample-requests",
                recipient_user_ids=[user.id],
                dedupe_key=f"technical.sample.requested.{row.id}.{department.department_code}.{user.id}",
            ))
    return created


def deliver_sample_team_emails(db: Session, *, sample_request_id: int) -> tuple[int, int]:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0, 0
    sent = 0
    failed = 0
    for department in row.departments:
        for user in _sample_recipients(db, department.department_code):
            body = (
                f"Hello {user.full_name or 'Technical Team'},\n\n"
                + _sample_request_message(db, row, department.department_code)
                + f"\n\nERP Sample Requests: {settings.app_public_url.rstrip('/')}/sample-requests\n\nNakshaTech ERP"
            )
            try:
                send_email(
                    recipient=user.email,
                    subject=f"[{row.request_code}] Technical sample request - {TECHNICAL_DEPARTMENT_LABELS[department.department_code]}",
                    body=body,
                    from_name="NakshaTech BD Sample Coordination",
                )
                sent += 1
            except Exception:
                failed += 1
                logger.exception("Could not send technical sample email to user %s", user.id)
    return sent, failed


def start_sample_department(
    db: Session,
    *,
    sample_request: TechnicalSampleRequest,
    actor: User,
    effective_role: str,
) -> TechnicalSampleDepartment:
    department = _department_for_role(sample_request, effective_role)
    if department is None:
        raise PermissionError("This sample request is not assigned to your technical department")
    _assert_sample_actor(db, department_code=department.department_code, actor=actor)
    if department.status not in {"requested", "revision_requested"}:
        raise ValueError("This sample department cannot be started from its current status")
    department.status = "in_progress"
    department.started_by_id = actor.id
    department.started_at = department.started_at or utc_now()
    department.updated_at = utc_now()
    if sample_request.status in {"requested", "revision_requested"}:
        sample_request.status = "in_progress"
        sample_request.updated_at = utc_now()
    db.flush()
    return department


def _refresh_sample_ready_status(sample_request: TechnicalSampleRequest) -> None:
    statuses = {row.status for row in sample_request.departments}
    if statuses and statuses.issubset({"submitted"}):
        sample_request.status = "ready_for_client_review"
    elif "revision_requested" in statuses:
        sample_request.status = "revision_requested"
    elif "in_progress" in statuses or "submitted" in statuses:
        sample_request.status = "in_progress"
    else:
        sample_request.status = "requested"
    sample_request.updated_at = utc_now()


def submit_sample_department(
    db: Session,
    *,
    sample_request: TechnicalSampleRequest,
    actor: User,
    effective_role: str,
    payload: TechnicalSampleSubmit,
) -> TechnicalSampleSubmission:
    department = _department_for_role(sample_request, effective_role)
    if department is None:
        raise PermissionError("This sample request is not assigned to your technical department")
    _assert_sample_actor(db, department_code=department.department_code, actor=actor)
    if department.status not in {"requested", "in_progress", "revision_requested"}:
        raise ValueError("This sample department cannot be submitted from its current status")
    attempt_no = len(department.submissions) + 1
    submission = TechnicalSampleSubmission(
        department=department,
        attempt_no=attempt_no,
        sample_reference=payload.sample_reference.strip(),
        notes=(payload.notes or "").strip() or None,
        submitted_by_id=actor.id,
    )
    db.add(submission)
    db.flush()
    department.status = "submitted"
    department.revision_feedback = None
    department.last_submitted_by_id = actor.id
    department.last_submitted_at = submission.submitted_at
    department.updated_at = utc_now()
    _refresh_sample_ready_status(sample_request)
    db.flush()
    return submission


def create_bd_sample_submission_notification(
    db: Session,
    *,
    sample_request_id: int,
    department_code: str,
    attempt_no: int,
) -> int:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0
    opportunity = db.get(BDOpportunity, row.opportunity_id)
    if opportunity is None:
        return 0
    created = create_global_notification(
        db,
        event_type="bd.sample.submitted",
        title=f"Sample submitted: {row.request_code} - {TECHNICAL_DEPARTMENT_LABELS[department_code]}",
        message=(
            f"{TECHNICAL_DEPARTMENT_LABELS[department_code]} submitted sample attempt {attempt_no} for "
            f"{row.request_code}. Review the submission in Sample Requests before sending it to the client."
        ),
        category="system",
        target_url="/sample-requests",
        recipient_user_ids=[opportunity.owner_user_id],
        dedupe_key=f"bd.sample.submitted.{row.id}.{department_code}.{attempt_no}",
    )
    return len(created)


def send_sample_to_client_review(
    db: Session,
    *,
    sample_request: TechnicalSampleRequest,
    actor: User,
) -> TechnicalSampleRequest:
    opportunity = db.get(BDOpportunity, sample_request.opportunity_id)
    if opportunity is None:
        raise ValueError("BD opportunity not found")
    _ensure_bd_owner(opportunity, actor)
    if not sample_request.departments or any(row.status != "submitted" for row in sample_request.departments):
        raise ValueError("Every selected technical department must submit its current sample before client review")
    sample_request.status = "client_review"
    sample_request.client_review_sent_at = utc_now()
    sample_request.updated_at = utc_now()
    old_stage = opportunity.stage
    opportunity.stage = "client_review"
    opportunity.updated_at = utc_now()
    db.add(BDOpportunityEvent(
        opportunity_id=opportunity.id,
        action="sample_sent_to_client_review",
        from_stage=old_stage,
        to_stage="client_review",
        comments=f"{sample_request.request_code} sent to client review after all selected departments submitted.",
        actor_user_id=actor.id,
    ))
    db.flush()
    return sample_request


def record_sample_client_decision(
    db: Session,
    *,
    sample_request: TechnicalSampleRequest,
    actor: User,
    payload: TechnicalSampleClientDecision,
) -> TechnicalSampleRequest:
    opportunity = db.get(BDOpportunity, sample_request.opportunity_id)
    if opportunity is None:
        raise ValueError("BD opportunity not found")
    _ensure_bd_owner(opportunity, actor)
    if sample_request.status != "client_review":
        raise ValueError("Send the complete sample to Client Review before recording the client's decision")

    selected_codes = {row.department_code for row in sample_request.departments}
    if payload.decision == "revision":
        requested = set(payload.revision_department_codes)
        invalid = requested.difference(selected_codes)
        if invalid:
            raise ValueError("Revision can be requested only from departments selected in this sample request")
        feedback = (payload.feedback or "").strip()
        if not feedback:
            raise ValueError("Client revision feedback is required")
        for row in sample_request.departments:
            if row.department_code in requested:
                row.status = "revision_requested"
                row.revision_feedback = feedback
                row.updated_at = utc_now()
        sample_request.status = "revision_requested"
        sample_request.client_feedback = feedback
        sample_request.updated_at = utc_now()
        old_stage = opportunity.stage
        opportunity.stage = "revision"
        opportunity.client_feedback = feedback
        opportunity.updated_at = utc_now()
        db.add(BDOpportunityEvent(
            opportunity_id=opportunity.id,
            action="client_sample_revision_requested",
            from_stage=old_stage,
            to_stage="revision",
            comments=(
                f"Client requested sample revision from: {', '.join(TECHNICAL_DEPARTMENT_LABELS[code] for code in sorted(requested))}. "
                f"Feedback: {feedback}"
            ),
            actor_user_id=actor.id,
        ))
    else:
        if any(row.status != "submitted" for row in sample_request.departments):
            raise ValueError("All selected technical departments must have a submitted sample before client approval")
        feedback = (payload.feedback or "").strip() or None
        now = utc_now()
        for row in sample_request.departments:
            row.status = "client_approved"
            row.revision_feedback = None
            row.updated_at = now
        sample_request.status = "client_approved"
        sample_request.client_feedback = feedback
        sample_request.client_approved_at = now
        sample_request.updated_at = now
        old_stage = opportunity.stage
        opportunity.stage = "finance_handoff"
        opportunity.accepted_at = opportunity.accepted_at or now
        opportunity.finance_handoff_at = now
        opportunity.client_feedback = feedback
        opportunity.updated_at = now
        db.add(BDOpportunityEvent(
            opportunity_id=opportunity.id,
            action="client_sample_approved_finance_handoff",
            from_stage=old_stage,
            to_stage="finance_handoff",
            comments=(feedback or "Client approved the multi-team technical sample. Finance Client ID and Project ID are now required."),
            actor_user_id=actor.id,
        ))
    db.flush()
    return sample_request


def create_revision_team_notifications(db: Session, *, sample_request_id: int) -> int:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0
    created = 0
    for department in row.departments:
        if department.status != "revision_requested":
            continue
        for user in _sample_recipients(db, department.department_code):
            created += len(create_global_notification(
                db,
                event_type="technical.sample.revision_requested",
                title=f"Client revision requested: {row.request_code}",
                message=(
                    f"Client requested a revision from {TECHNICAL_DEPARTMENT_LABELS[department.department_code]}.\n"
                    f"Feedback: {department.revision_feedback or 'See BD feedback'}\n"
                    "Open Sample Requests, start the revision and submit a new attempt."
                ),
                category="system",
                target_url="/sample-requests",
                recipient_user_ids=[user.id],
                dedupe_key=f"technical.sample.revision.{row.id}.{department.department_code}.{len(department.submissions) + 1}.{user.id}",
            ))
    return created


def deliver_revision_team_emails(db: Session, *, sample_request_id: int) -> tuple[int, int]:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0, 0
    sent = 0
    failed = 0
    for department in row.departments:
        if department.status != "revision_requested":
            continue
        for user in _sample_recipients(db, department.department_code):
            try:
                send_email(
                    recipient=user.email,
                    subject=f"[{row.request_code}] Client revision - {TECHNICAL_DEPARTMENT_LABELS[department.department_code]}",
                    body=(
                        f"Hello {user.full_name or 'Technical Team'},\n\n"
                        f"The client requested a revision for {row.request_code}.\n"
                        f"Department: {TECHNICAL_DEPARTMENT_LABELS[department.department_code]}\n"
                        f"Feedback: {department.revision_feedback or 'See ERP'}\n\n"
                        f"ERP Sample Requests: {settings.app_public_url.rstrip('/')}/sample-requests\n\nNakshaTech ERP"
                    ),
                    from_name="NakshaTech BD Sample Coordination",
                )
                sent += 1
            except Exception:
                failed += 1
                logger.exception("Could not send technical sample revision email to user %s", user.id)
    return sent, failed


def _finance_handoff_message(db: Session, row: TechnicalSampleRequest) -> tuple[str, BDOpportunity | None]:
    opportunity = db.get(BDOpportunity, row.opportunity_id)
    if opportunity is None:
        return "Client-approved sample is ready for Finance handoff.", None
    owner = db.get(User, opportunity.owner_user_id)
    departments = ", ".join(
        TECHNICAL_DEPARTMENT_LABELS[item.department_code] for item in row.departments
    )
    message = "\n".join([
        f"Opportunity: {opportunity.opportunity_code} - {opportunity.title}",
        f"Prospect / Client: {opportunity.client_name_snapshot or 'Not specified'}",
        f"Requirement / Scope: {opportunity.requirement}",
        f"Technical Sample: {row.request_code} - CLIENT APPROVED",
        f"Sample Departments: {departments}",
        f"BD Owner: {owner.full_name if owner else 'Not available'}",
        "Finance action: create/confirm the official Client ID and Project ID. Finance does not select technical departments or Project Managers.",
    ])
    return message, opportunity


def create_finance_client_approved_notifications(db: Session, *, sample_request_id: int) -> int:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0
    message, opportunity = _finance_handoff_message(db, row)
    if opportunity is None:
        return 0
    created = create_global_notification(
        db,
        event_type="finance.bd_opportunity.client_approved",
        title=f"Client approved - create Client/Project IDs: {opportunity.opportunity_code}",
        message=message,
        category="system",
        target_url="/finance",
        recipient_roles=["finance"],
        dedupe_key=f"finance.bd_opportunity.client_approved.{opportunity.id}",
    )
    return len(created)


def deliver_finance_client_approved_emails(db: Session, *, sample_request_id: int) -> tuple[int, int]:
    row = db.get(TechnicalSampleRequest, sample_request_id)
    if row is None:
        return 0, 0
    message, opportunity = _finance_handoff_message(db, row)
    if opportunity is None:
        return 0, 0
    sent = 0
    failed = 0
    recipients = resolve_recipient_users(db, recipient_roles=["finance"])
    for recipient in recipients:
        try:
            send_email(
                recipient=recipient.email,
                subject=f"[{opportunity.opportunity_code}] Client approved - create Client ID and Project ID",
                body=(
                    "Hello Finance Team,\n\n"
                    "The client has approved the technical sample coordinated by BD.\n\n"
                    + message
                    + f"\n\nERP Finance Dashboard: {settings.app_public_url.rstrip('/')}/finance\n\nNakshaTech ERP"
                ),
                from_name="NakshaTech BD -> Finance",
            )
            sent += 1
        except Exception:
            failed += 1
            logger.exception("Could not send client-approved Finance handoff email to user %s", recipient.id)
    return sent, failed


def sample_department_payload(db: Session, row: TechnicalSampleDepartment) -> dict:
    latest = row.submissions[-1] if row.submissions else None
    submitter = db.get(User, latest.submitted_by_id) if latest else None
    return {
        "id": row.id,
        "department_code": row.department_code,
        "department_label": TECHNICAL_DEPARTMENT_LABELS.get(row.department_code, row.department_code),
        "status": row.status,
        "revision_feedback": row.revision_feedback,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "last_submitted_at": row.last_submitted_at.isoformat() if row.last_submitted_at else None,
        "attempt_count": len(row.submissions),
        "latest_submission": None if latest is None else {
            "id": latest.id,
            "attempt_no": latest.attempt_no,
            "sample_reference": latest.sample_reference,
            "notes": latest.notes,
            "submitted_by_id": latest.submitted_by_id,
            "submitted_by_name": submitter.full_name if submitter else None,
            "submitted_at": latest.submitted_at.isoformat(),
        },
    }


def sample_request_payload(db: Session, row: TechnicalSampleRequest, *, role: str) -> dict:
    opportunity = db.get(BDOpportunity, row.opportunity_id)
    normalized_role = normalize_role(role)
    department_code = TECHNICAL_ROLE_DEPARTMENT_MAP.get(normalized_role)
    departments = row.departments
    if department_code:
        departments = [item for item in departments if item.department_code == department_code]
    return {
        "id": row.id,
        "request_code": row.request_code,
        "opportunity_id": row.opportunity_id,
        "opportunity_code": opportunity.opportunity_code if opportunity else None,
        "opportunity_title": opportunity.title if opportunity else None,
        "client_name": opportunity.client_name_snapshot if opportunity else None,
        "requirement": opportunity.requirement if opportunity else None,
        "title": row.title,
        "instructions": row.instructions,
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "status": row.status,
        "client_feedback": row.client_feedback,
        "client_review_sent_at": row.client_review_sent_at.isoformat() if row.client_review_sent_at else None,
        "client_approved_at": row.client_approved_at.isoformat() if row.client_approved_at else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "departments": [sample_department_payload(db, item) for item in departments],
    }


def sample_dashboard_payload(db: Session, *, actor: User, effective_role: str) -> dict:
    role = normalize_role(effective_role)
    technical_role = role in TECHNICAL_ROLE_DEPARTMENT_MAP
    if role == "bd":
        owned_opportunities = list(db.scalars(select(BDOpportunity).where(
            BDOpportunity.owner_user_id == actor.id
        ).order_by(BDOpportunity.updated_at.desc())).all())
        opportunity_ids = {item.id for item in owned_opportunities}
        requests = list(db.scalars(select(TechnicalSampleRequest).where(
            TechnicalSampleRequest.opportunity_id.in_(opportunity_ids)
        ).order_by(TechnicalSampleRequest.updated_at.desc())).all()) if opportunity_ids else []
        opportunities = [
            item for item in owned_opportunities
            if item.linked_project_id is None
            and item.stage not in {"finance_handoff", "project_linked", "production", "delivery_ready", "delivered", "closed"}
        ]
        viewer_mode = "bd_editor"
    elif technical_role:
        department_code = TECHNICAL_ROLE_DEPARTMENT_MAP[role]
        rows = list(db.scalars(select(TechnicalSampleDepartment).where(
            TechnicalSampleDepartment.department_code == department_code
        )).all())
        request_ids = {item.sample_request_id for item in rows}
        requests = list(db.scalars(select(TechnicalSampleRequest).where(
            TechnicalSampleRequest.id.in_(request_ids)
        ).order_by(TechnicalSampleRequest.updated_at.desc())).all()) if request_ids else []
        opportunities = []
        viewer_mode = "department"
    elif role in {"management", "admin"}:
        requests = list(db.scalars(select(TechnicalSampleRequest).order_by(
            TechnicalSampleRequest.updated_at.desc()
        )).all())
        opportunities = []
        viewer_mode = "read_only"
    else:
        raise PermissionError("Sample Requests dashboard is not available for this role")

    live = live_routing_enabled(db)
    recipient_emails = {}
    if role == "bd":
        for code in TECHNICAL_DEPARTMENT_ROLE_MAP:
            if live:
                recipient_emails[code] = [user.email for user in real_department_users(db, department_code=code, purpose="sample")]
            else:
                recipient_emails[code] = [DEMO_DEPARTMENT_EMAILS[code]]
    return {
        "viewer_mode": viewer_mode,
        "current_role": role,
        "current_department_code": TECHNICAL_ROLE_DEPARTMENT_MAP.get(role),
        "demo_mode": not live,
        "routing_mode": current_routing_mode(db),
        "technical_recipient_emails": recipient_emails,
        "demo_recipient_emails": DEMO_DEPARTMENT_EMAILS if role == "bd" and not live else {},
        "technical_departments": [
            {"code": code, "label": TECHNICAL_DEPARTMENT_LABELS[code], "role": TECHNICAL_DEPARTMENT_ROLE_MAP[code]}
            for code in TECHNICAL_DEPARTMENT_ROLE_MAP
        ],
        "eligible_opportunities": [
            {
                "id": item.id,
                "opportunity_code": item.opportunity_code,
                "title": item.title,
                "client_name": item.client_name_snapshot,
                "requirement": item.requirement,
                "stage": item.stage,
            }
            for item in opportunities
            if db.scalar(select(TechnicalSampleRequest.id).where(TechnicalSampleRequest.opportunity_id == item.id)) is None
        ],
        "sample_requests": [sample_request_payload(db, item, role=role) for item in requests],
    }
