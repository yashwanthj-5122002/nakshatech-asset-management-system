from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
import hashlib
import logging
import secrets
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.entities import Asset, User, utc_now
from app.modules.drone.models import DroneProject
from app.modules.employee_portal.models import SupportTicket
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.notifications.service import create_global_notification
from app.modules.operations.lifecycle_models import (
    ProjectChangeRequest,
    ProjectDeliveryVersion,
    ProjectFeedbackAttachment,
    ProjectFeedbackRequest,
    ProjectFeedbackResponse,
    ProjectInvoice,
    ProjectInvoicePayment,
    ProjectMessage,
    ProjectReworkCycle,
    ProjectTimelineEvent,
)
from app.modules.operations.lifecycle_schemas import (
    ChangeRequestDecision,
    DeemedAcceptanceCreate,
    FeedbackClassification,
    FeedbackRequestCreate,
    FeedbackResponseCreate,
    InvoiceClose,
    InvoiceDraftCreate,
    InvoicePaymentCreate,
    InvoiceRaise,
    NoFeedbackRecommendation,
    ProjectMessageCreate,
    ReworkStageUpdate,
)
from app.modules.operations.models import (
    OrthoProjectMember,
    OrthoWorkPackage,
    ProjectWorkflow,
    ProjectWorkflowEvent,
)

logger = logging.getLogger(__name__)

OPERATIONAL_COMPLETE = "OPERATIONAL_COMPLETE"
FEEDBACK_NOT_SENT = "FEEDBACK_NOT_SENT"
FEEDBACK_REQUESTED = "FEEDBACK_REQUESTED"
FEEDBACK_REMINDER_SENT = "FEEDBACK_REMINDER_SENT"
AWAITING_CLIENT_FEEDBACK = "AWAITING_CLIENT_FEEDBACK"
FEEDBACK_NEGATIVE = "FEEDBACK_NEGATIVE"
REWORK_OPEN = "REWORK_OPEN"
REWORK_PRODUCTION = "REWORK_PRODUCTION"
REWORK_QC = "REWORK_QC"
REWORK_QA = "REWORK_QA"
REWORK_DELIVERED = "REWORK_DELIVERED"
REWORK_RESUBMITTED = "REWORK_RESUBMITTED"
CLIENT_ACCEPTED = "CLIENT_ACCEPTED"
NO_FEEDBACK_CLOSURE_RECOMMENDED = "NO_FEEDBACK_CLOSURE_RECOMMENDED"
DEEMED_ACCEPTED = "DEEMED_ACCEPTED"
CHANGE_REQUEST_PENDING = "CHANGE_REQUEST_PENDING"
READY_FOR_BILLING = "READY_FOR_BILLING"
INVOICE_DRAFT = "INVOICE_DRAFT"
INVOICE_RAISED = "INVOICE_RAISED"
PAYMENT_PENDING = "PAYMENT_PENDING"
PARTIALLY_PAID = "PARTIALLY_PAID"
PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
INVOICE_CLOSED = "INVOICE_CLOSED"
FINANCE_CLOSURE_PENDING = "FINANCE_CLOSURE_PENDING"
CLOSED = "CLOSED"

MANAGEMENT_ROLES = {"management", "admin"}
FINANCE_ROLES = {"finance", "admin"}
BD_ROLES = {"bd", "admin"}


def _project_query():
    return select(FinanceProject).options(
        selectinload(FinanceProject.client).selectinload(FinanceClient.master_profile),
        selectinload(FinanceProject.master_profile).selectinload(FinanceProjectMasterProfile.project_manager),
    )


def _project(db: Session, project_id: int) -> FinanceProject:
    project = db.scalar(_project_query().where(FinanceProject.id == project_id))
    if project is None:
        raise ValueError("Project not found")
    return project


def _workflow(db: Session, project_id: int) -> ProjectWorkflow:
    workflow = db.get(ProjectWorkflow, project_id)
    if workflow is None:
        raise ValueError("Project workflow not found")
    return workflow


def add_timeline_event(
    db: Session,
    *,
    project_id: int,
    event_type: str,
    title: str,
    status: str | None,
    actor_user_id: int | None,
    details: str | None = None,
    event_key: str | None = None,
) -> ProjectTimelineEvent:
    row = ProjectTimelineEvent(
        project_id=project_id,
        event_key=event_key or f"{event_type}:{uuid.uuid4().hex}",
        event_type=event_type,
        title=title,
        details=(details or "").strip() or None,
        status=status,
        actor_user_id=actor_user_id,
    )
    db.add(row)
    return row


def _transition(
    db: Session,
    *,
    workflow: ProjectWorkflow,
    actor: User,
    status: str,
    event_type: str,
    title: str,
    comments: str | None = None,
) -> None:
    previous = workflow.status
    workflow.status = status
    workflow.updated_by_id = actor.id
    workflow.updated_at = utc_now()
    db.add(ProjectWorkflowEvent(
        project_id=workflow.project_id,
        event_type=event_type,
        from_status=previous,
        to_status=status,
        comments=(comments or "").strip() or None,
        actor_user_id=actor.id,
    ))
    add_timeline_event(
        db,
        project_id=workflow.project_id,
        event_type=event_type,
        title=title,
        status=status,
        actor_user_id=actor.id,
        details=comments,
    )


def _client_email(project: FinanceProject) -> str:
    client = project.client
    profile = client.master_profile if client else None
    candidates = [
        profile.contact_person_email if profile else None,
        profile.organization_email if profile else None,
        client.client_email if client else None,
    ]
    for value in candidates:
        cleaned = (value or "").strip().lower()
        if cleaned and "@" in cleaned:
            return cleaned
    raise ValueError("Client Master does not contain a usable client/contact email address")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _request_by_token(db: Session, token: str) -> ProjectFeedbackRequest:
    cleaned = (token or "").strip()
    if len(cleaned) < 24:
        raise ValueError("Invalid feedback link")
    row = db.scalar(select(ProjectFeedbackRequest).where(ProjectFeedbackRequest.token_hash == _token_hash(cleaned)))
    if row is None:
        raise ValueError("Invalid feedback link")
    return row


def _notify(
    db: Session,
    *,
    project: FinanceProject,
    event_type: str,
    title: str,
    message: str,
    target_url: str,
    recipient_roles: list[str] | None = None,
    recipient_user_ids: list[int] | None = None,
    dedupe_key: str | None = None,
) -> None:
    create_global_notification(
        db,
        event_type=event_type,
        title=title,
        message=f"Project ID {project.project_code}: {message}",
        category="approval" if recipient_roles else "system",
        target_url=target_url,
        recipient_roles=recipient_roles,
        recipient_user_ids=recipient_user_ids,
        dedupe_key=dedupe_key,
    )


def enter_feedback_lifecycle(
    db: Session,
    *,
    actor: User,
    project: FinanceProject,
    workflow: ProjectWorkflow,
) -> None:
    """Move a newly operationally-complete project into feedback, never billing closure."""
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=OPERATIONAL_COMPLETE,
        event_type="pm_operational_completion",
        title="PM Operational Completion",
        comments=workflow.completion_remarks,
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=FEEDBACK_NOT_SENT,
        event_type="client_feedback_lifecycle_opened",
        title="Client feedback lifecycle opened",
        comments="Business Development must send the client feedback request before billing.",
    )
    next_version = int(db.scalar(select(func.max(ProjectDeliveryVersion.version_number)).where(
        ProjectDeliveryVersion.project_id == project.id
    )) or 0) + 1
    if workflow.final_delivery_reference:
        db.add(ProjectDeliveryVersion(
            project_id=project.id,
            version_number=next_version,
            delivery_reference=workflow.final_delivery_reference,
            notes=workflow.completion_remarks,
            delivered_by_id=actor.id,
            delivered_at=workflow.operational_completed_at or utc_now(),
        ))
    _notify(
        db,
        project=project,
        event_type="lifecycle.operational_completed",
        title=f"Operational completion: {project.project_code}",
        message="operational delivery is complete; client feedback must now be requested.",
        target_url="/bd/feedback",
        recipient_user_ids=[workflow.bd_owner_user_id],
        dedupe_key=f"lifecycle:operational-complete:{project.id}",
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.operational_completed_management",
        title=f"Operational completion: {project.project_code}",
        message="entered the client feedback lifecycle.",
        target_url="/management/project-360",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:operational-complete:management:{project.id}",
    )


def create_feedback_request(
    db: Session,
    *,
    actor: User,
    project_id: int,
    payload: FeedbackRequestCreate,
) -> tuple[ProjectFeedbackRequest, str, str]:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can send client feedback requests")
    allowed = {FEEDBACK_NOT_SENT, REWORK_RESUBMITTED, FEEDBACK_REMINDER_SENT, AWAITING_CLIENT_FEEDBACK}
    if workflow.status not in allowed:
        raise ValueError(f"Feedback request cannot be sent while project is {workflow.status}")
    open_request = db.scalar(select(ProjectFeedbackRequest).where(
        ProjectFeedbackRequest.project_id == project_id,
        ProjectFeedbackRequest.status == "sent",
    ))
    if open_request is not None:
        raise ValueError("An open feedback request already exists; send a reminder instead")

    cycle_number = int(db.scalar(select(func.max(ProjectFeedbackRequest.cycle_number)).where(
        ProjectFeedbackRequest.project_id == project_id
    )) or 0) + 1
    token = secrets.token_urlsafe(40)
    request_code = f"FBR-{project.project_code}-{cycle_number:02d}"
    row = ProjectFeedbackRequest(
        project_id=project_id,
        request_code=request_code,
        cycle_number=cycle_number,
        recipient_email=_client_email(project),
        token_hash=_token_hash(token),
        message_thread_id=f"NT-FEEDBACK-{project.id}-{uuid.uuid4().hex[:16]}",
        message=(payload.message or "").strip() or None,
        expires_at=utc_now() + timedelta(days=payload.expiry_days),
        sent_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=FEEDBACK_REQUESTED,
        event_type="client_feedback_requested",
        title="Client Feedback Request sent",
        comments=f"{request_code} sent to {row.recipient_email}",
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=AWAITING_CLIENT_FEEDBACK,
        event_type="awaiting_client_feedback",
        title="Awaiting Client Feedback",
        comments=f"Feedback link expires {row.expires_at.isoformat()} UTC",
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.feedback_requested",
        title=f"Feedback requested: {project.project_code}",
        message=f"client feedback request {request_code} was sent.",
        target_url="/management/project-360",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:feedback-request:{row.id}",
    )
    external_url = f"{settings.app_public_url.rstrip('/')}/client-feedback/{token}"
    return row, token, external_url


def send_feedback_request_email(db: Session, *, request_id: int, token: str, reminder: bool = False) -> None:
    row = db.get(ProjectFeedbackRequest, request_id)
    if row is None:
        return
    project = _project(db, row.project_id)
    link = f"{settings.app_public_url.rstrip('/')}/client-feedback/{token}"
    subject_prefix = "Reminder: " if reminder else ""
    body = (
        f"Hello,\n\n{subject_prefix}Nakshatech requests your feedback for the completed project.\n\n"
        f"Project ID: {project.project_code}\nProject: {project.project_name}\n"
        f"Feedback Request ID: {row.request_code}\nThread ID: {row.message_thread_id}\n"
        f"Secure feedback link: {link}\nLink expiry (UTC): {row.expires_at.isoformat()}\n\n"
        f"{row.message or 'Please confirm acceptance or describe any correction/additional scope.'}\n\n"
        "The secure link does not require an ERP login. Do not forward it.\n"
        "Nakshatech ERP"
    )
    try:
        send_email(
            recipient=row.recipient_email,
            subject=f"{subject_prefix}[{project.project_code}] Client feedback request {row.request_code}",
            body=body,
            from_name="Nakshatech Business Development",
        )
    except Exception:
        logger.exception("Feedback request email delivery failed for request %s", request_id)


def send_feedback_reminder(
    db: Session, *, actor: User, request_id: int
) -> tuple[ProjectFeedbackRequest, str, str]:
    row = db.get(ProjectFeedbackRequest, request_id)
    if row is None:
        raise ValueError("Feedback request not found")
    workflow = _workflow(db, row.project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can send feedback reminders")
    if row.status != "sent" or row.responded_at is not None:
        raise ValueError("Only an unanswered feedback request can be reminded")
    token = secrets.token_urlsafe(40)
    row.token_hash = _token_hash(token)
    row.expires_at = utc_now() + timedelta(days=7)
    row.reminder_count += 1
    row.last_reminder_at = utc_now()
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=FEEDBACK_REMINDER_SENT,
        event_type="client_feedback_reminder_sent",
        title="Client Feedback Reminder sent",
        comments=f"Reminder {row.reminder_count} for {row.request_code}",
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=AWAITING_CLIENT_FEEDBACK,
        event_type="awaiting_client_feedback_after_reminder",
        title="Awaiting Client Feedback after reminder",
    )
    return row, token, f"{settings.app_public_url.rstrip('/')}/client-feedback/{token}"


def public_feedback_payload(db: Session, *, token: str) -> dict:
    row = _request_by_token(db, token)
    project = _project(db, row.project_id)
    expired = row.expires_at < utc_now()
    return {
        "request_code": row.request_code,
        "project_id": project.project_code,
        "project_name": project.project_name,
        "cycle_number": row.cycle_number,
        "message": row.message,
        "expires_at": row.expires_at.isoformat(),
        "expired": expired,
        "responded": row.responded_at is not None,
        "thread_id": row.message_thread_id,
    }


def feedback_response_for_attachment_token(
    db: Session, *, token: str
) -> tuple[ProjectFeedbackRequest, ProjectFeedbackResponse]:
    request_row = _request_by_token(db, token)
    if request_row.expires_at < utc_now():
        raise ValueError("This feedback link has expired")
    response = db.scalar(select(ProjectFeedbackResponse).where(
        ProjectFeedbackResponse.feedback_request_id == request_row.id
    ).order_by(ProjectFeedbackResponse.id.desc()))
    if response is None:
        raise ValueError("Submit the feedback response before uploading attachments")
    return request_row, response


def submit_feedback_response(
    db: Session, *, token: str, payload: FeedbackResponseCreate
) -> ProjectFeedbackResponse:
    request_row = _request_by_token(db, token)
    if request_row.expires_at < utc_now():
        raise ValueError("This feedback link has expired; please contact Nakshatech for a new link")
    if request_row.responded_at is not None or request_row.status != "sent":
        raise ValueError("A response has already been submitted for this feedback request")
    project = _project(db, request_row.project_id)
    workflow = _workflow(db, request_row.project_id)
    actor = db.get(User, request_row.sent_by_id)
    if actor is None:
        raise ValueError("Feedback request owner no longer exists")

    positive = payload.response_type == "accepted"
    response = ProjectFeedbackResponse(
        project_id=request_row.project_id,
        feedback_request_id=request_row.id,
        response_type=payload.response_type,
        comments=(payload.comments or "").strip() or None,
        correction_description=(payload.correction_description or "").strip() or None,
        client_name=(payload.client_name or "").strip() or None,
        client_email=str(payload.client_email).strip().lower() if payload.client_email else None,
        external_message_id=(payload.external_message_id or "").strip() or None,
        classification_status="confirmed" if positive else "pending_bd",
        classified_as="accepted" if positive else None,
        classified_by_id=actor.id if positive else None,
        classified_at=utc_now() if positive else None,
    )
    db.add(response)
    db.flush()
    for attachment in payload.attachments:
        db.add(ProjectFeedbackAttachment(
            project_id=request_row.project_id,
            feedback_response_id=response.id,
            original_filename=attachment.original_filename.strip(),
            storage_key=attachment.storage_key.strip(),
            mime_type=(attachment.mime_type or "").strip() or None,
            file_size=attachment.file_size,
            content_sha256=(attachment.content_sha256 or "").strip().lower() or None,
        ))
    request_row.status = "responded"
    request_row.responded_at = utc_now()
    if positive:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=CLIENT_ACCEPTED,
            event_type="client_accepted",
            title="Client Accepted",
            comments=payload.comments,
        )
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=READY_FOR_BILLING,
            event_type="project_ready_for_billing",
            title="Ready For Billing",
            comments="Client acceptance received through the secure feedback request.",
        )
        _notify(
            db,
            project=project,
            event_type="lifecycle.client_accepted",
            title=f"Ready for billing: {project.project_code}",
            message="the client accepted the delivery. Finance can prepare the invoice.",
            target_url="/finance/billing",
            recipient_roles=["finance"],
            dedupe_key=f"lifecycle:client-accepted:{response.id}",
        )
    else:
        # Non-positive client responses (correction or additional scope) never create a
        # rework cycle or change request directly. Only the BD classification action
        # (classify_feedback_response) may open a rework cycle or change request, and
        # only after BD confirms the classification.
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=FEEDBACK_NEGATIVE,
            event_type="client_feedback_requires_classification",
            title="Client feedback requires BD classification",
            comments=payload.correction_description,
        )
        _notify(
            db,
            project=project,
            event_type="lifecycle.client_response_requires_bd",
            title=f"BD classification required: {project.project_code}",
            message="client feedback requires confirmation as correction/rework or additional scope.",
            target_url="/bd/feedback",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:classify-response:{response.id}",
        )
    return response


def _ensure_change_request(
    db: Session,
    *,
    response: ProjectFeedbackResponse,
    actor: User | None,
    commercial_impact: Decimal | None = None,
    currency: str = "INR",
) -> ProjectChangeRequest:
    existing = db.scalar(select(ProjectChangeRequest).where(
        ProjectChangeRequest.source_feedback_response_id == response.id
    ))
    if existing:
        if commercial_impact is not None:
            existing.commercial_impact = commercial_impact
            existing.currency = currency.upper()
        return existing
    number = int(db.scalar(select(func.count(ProjectChangeRequest.id)).where(
        ProjectChangeRequest.project_id == response.project_id
    )) or 0) + 1
    project = _project(db, response.project_id)
    row = ProjectChangeRequest(
        project_id=response.project_id,
        request_code=f"CR-{project.project_code}-{number:02d}",
        source_feedback_response_id=response.id,
        description=response.correction_description or response.comments or "Additional scope requested by client",
        commercial_impact=commercial_impact,
        currency=currency.upper(),
        created_by_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    return row


def classify_feedback_response(
    db: Session,
    *,
    actor: User,
    response_id: int,
    payload: FeedbackClassification,
) -> ProjectReworkCycle | ProjectChangeRequest:
    response = db.get(ProjectFeedbackResponse, response_id)
    if response is None:
        raise ValueError("Feedback response not found")
    workflow = _workflow(db, response.project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can confirm feedback classification")
    if response.classification_status == "confirmed":
        raise ValueError("This feedback response has already been classified")
    if workflow.status != FEEDBACK_NEGATIVE:
        raise ValueError("Project is not awaiting BD classification of a client response")
    response.classification_status = "confirmed"
    response.classified_as = payload.classification
    response.classified_by_id = actor.id
    response.classified_at = utc_now()
    project = _project(db, response.project_id)

    if payload.classification == "additional_scope":
        change_request = _ensure_change_request(
            db,
            response=response,
            actor=actor,
            commercial_impact=payload.commercial_impact,
            currency=payload.currency,
        )
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=CHANGE_REQUEST_PENDING,
            event_type="change_request_created",
            title="Additional Scope / Change Request created",
            comments=f"{change_request.request_code}: {payload.remarks or change_request.description}",
        )
        return change_request

    existing = db.scalar(select(ProjectReworkCycle).where(
        ProjectReworkCycle.source_feedback_response_id == response.id
    ))
    if existing:
        raise ValueError("A rework cycle already exists for this feedback response")
    cycle_number = int(db.scalar(select(func.max(ProjectReworkCycle.cycle_number)).where(
        ProjectReworkCycle.project_id == response.project_id
    )) or 0) + 1
    team_lead_id = db.scalar(select(OrthoProjectMember.user_id).where(
        OrthoProjectMember.project_id == response.project_id,
        OrthoProjectMember.member_role == "team_leader",
        OrthoProjectMember.is_active.is_(True),
    ).order_by(OrthoProjectMember.id.desc()))
    pm_id = project.master_profile.project_manager_id if project.master_profile else None
    rework = ProjectReworkCycle(
        project_id=response.project_id,
        cycle_number=cycle_number,
        source_feedback_response_id=response.id,
        cycle_type="CORRECTION_REWORK",
        correction_scope=response.correction_description or response.comments or payload.remarks or "Client correction",
        project_manager_user_id=pm_id,
        team_leader_user_id=team_lead_id,
        opened_by_id=actor.id,
    )
    db.add(rework)
    db.flush()
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=REWORK_OPEN,
        event_type="rework_cycle_opened",
        title=f"Rework Cycle {cycle_number} opened",
        comments=rework.correction_scope,
    )
    recipients = [uid for uid in {pm_id, team_lead_id} if uid]
    if recipients:
        _notify(
            db,
            project=project,
            event_type="lifecycle.rework_opened",
            title=f"Rework opened: {project.project_code}",
            message=f"rework cycle {cycle_number} is ready for Production.",
            target_url="/ortho",
            recipient_user_ids=recipients,
            dedupe_key=f"lifecycle:rework-opened:{rework.id}",
        )
    return rework


def _may_update_rework(db: Session, *, actor: User, cycle: ProjectReworkCycle, stage: str) -> bool:
    if actor.role == "admin" or actor.id in {cycle.project_manager_user_id, cycle.team_leader_user_id}:
        return True
    expected_role = {"production": "production", "qc": "qc", "qa": "qa", "delivered": "qa"}[stage]
    return db.scalar(select(OrthoProjectMember.id).where(
        OrthoProjectMember.project_id == cycle.project_id,
        OrthoProjectMember.user_id == actor.id,
        OrthoProjectMember.member_role == expected_role,
        OrthoProjectMember.is_active.is_(True),
    )) is not None


# The rework pipeline, in order. A rework cycle's status is always one of these while it is in flight.
_REWORK_STAGE_ORDER = [REWORK_PRODUCTION, REWORK_QC, REWORK_QA, REWORK_DELIVERED]
_REWORK_NEXT_STAGE = ("qc", "qa", "delivered")          # stage that follows _REWORK_STAGE_ORDER[i]
# Where each work-package stage sits in that pipeline (0 = Production ... 4 = Delivered).
_PACKAGE_STAGE_RANK = {"not_started": 0, "production": 0, "production_rework": 0, "qc": 1, "qa": 2, "delivery_ready": 3, "delivered": 4}
# Package rank -> index into _REWORK_STAGE_ORDER ("ready for delivery" is still the cycle's QA stage).
_RANK_TO_CYCLE_INDEX = {0: 0, 1: 1, 2: 2, 3: 2, 4: 3}


def advance_rework(
    db: Session, *, actor: User, cycle_id: int, payload: ReworkStageUpdate
) -> ProjectReworkCycle:
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise ValueError("Rework cycle not found")
    if not _may_update_rework(db, actor=actor, cycle=cycle, stage=payload.stage):
        raise PermissionError("Only the assigned PM, Team Lead, or stage employee can update this rework")
    return _apply_rework_stage(db, actor=actor, cycle=cycle, payload=payload)


def _apply_rework_stage(
    db: Session, *, actor: User, cycle: ProjectReworkCycle, payload: ReworkStageUpdate
) -> ProjectReworkCycle:
    """The one place a rework cycle changes stage (used by the manual endpoint and by package-driven sync)."""
    target = {
        "production": REWORK_PRODUCTION,
        "qc": REWORK_QC,
        "qa": REWORK_QA,
        "delivered": REWORK_DELIVERED,
    }[payload.stage]
    allowed_from = {
        # REWORK_QC / REWORK_QA -> REWORK_PRODUCTION is a QC / QA rejection: the SAME cycle goes back for correction.
        REWORK_PRODUCTION: {REWORK_OPEN, REWORK_QC, REWORK_QA},
        REWORK_QC: {REWORK_PRODUCTION},
        REWORK_QA: {REWORK_QC},
        REWORK_DELIVERED: {REWORK_QA},
    }
    if cycle.status not in allowed_from[target]:
        raise ValueError(f"Rework cannot move from {cycle.status} to {target}")
    returned = target == REWORK_PRODUCTION and cycle.status in {REWORK_QC, REWORK_QA}
    cycle.status = target
    cycle.updated_at = utc_now()
    if target == REWORK_DELIVERED:
        cycle.delivered_at = utc_now()
        version_number = int(db.scalar(select(func.max(ProjectDeliveryVersion.version_number)).where(
            ProjectDeliveryVersion.project_id == cycle.project_id
        )) or 0) + 1
        db.add(ProjectDeliveryVersion(
            project_id=cycle.project_id,
            rework_cycle_id=cycle.id,
            version_number=version_number,
            delivery_reference=(payload.delivery_reference or "").strip(),
            notes=(payload.comments or "").strip() or None,
            delivered_by_id=actor.id,
        ))
    workflow = _workflow(db, cycle.project_id)
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=target,
        event_type="rework_returned_to_production" if returned else f"rework_{payload.stage}",
        title=(f"Rework Cycle {cycle.cycle_number}: returned to Production" if returned else f"Rework Cycle {cycle.cycle_number}: {payload.stage.title()}"),
        comments=payload.comments,
    )
    project = _project(db, cycle.project_id)
    if target == REWORK_DELIVERED:
        _notify(
            db,
            project=project,
            event_type="lifecycle.rework_delivered",
            title=f"Rework delivered: {project.project_code}",
            message=f"rework cycle {cycle.cycle_number} is ready for BD resubmission.",
            target_url="/bd/feedback",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:rework-delivered:{cycle.id}",
        )
    return cycle


def _rework_cycle_packages(db: Session, cycle_id: int) -> list[OrthoWorkPackage]:
    return list(db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.rework_cycle_id == cycle_id
    ).order_by(OrthoWorkPackage.id.asc())).all())


def _expected_rework_status(db: Session, cycle: ProjectReworkCycle) -> str | None:
    """The status a rework cycle must have, given where its rework work packages actually are.

    The cycle sits at the LEAST advanced of its rework packages (all Production done -> QC, all QC approved -> QA,
    all delivered -> Delivered; a package sent back by QC/QA pulls the cycle back to Production). None when the
    cycle is not in flight (not confirmed yet / already resubmitted / closed) or has no rework packages.
    """
    if cycle.status not in _REWORK_STAGE_ORDER or cycle.closed_at is not None:
        return None
    packages = _rework_cycle_packages(db, cycle.id)
    if not packages:
        return None
    lowest = min(_PACKAGE_STAGE_RANK.get(pkg.current_stage, 0) for pkg in packages)
    return _REWORK_STAGE_ORDER[_RANK_TO_CYCLE_INDEX[lowest]]


def _rework_delivery_notes(db: Session, cycle: ProjectReworkCycle, packages: list[OrthoWorkPackage], note: str | None) -> str:
    """Delivery-version notes: the links a rework delivery must keep (cycle, source package, feedback / change request)."""
    source_ids = {pkg.rework_of_package_id for pkg in packages if pkg.rework_of_package_id}
    sources = {row.id: row.package_code for row in db.scalars(select(OrthoWorkPackage).where(OrthoWorkPackage.id.in_(source_ids))).all()} if source_ids else {}
    work = "; ".join(pkg.package_code + (f" (rework of {sources[pkg.rework_of_package_id]})" if pkg.rework_of_package_id in sources else "") for pkg in packages)
    change_request = db.get(ProjectChangeRequest, cycle.source_change_request_id) if cycle.source_change_request_id else None
    origin = f"change request {change_request.request_code}" if change_request else f"client feedback response #{cycle.source_feedback_response_id}"
    return f"{(note or '').strip()} · Rework Cycle {cycle.cycle_number} for {origin} · Rework work: {work}".strip(" ·")


def sync_rework_cycle_with_packages(
    db: Session, *, actor: User, cycle_id: int, note: str | None = None, delivery_reference: str | None = None
) -> ProjectReworkCycle:
    """Bring a rework cycle (and the project workflow status) in step with its work packages.

    Idempotent. Every move goes through ``_apply_rework_stage`` (the authoritative transition), so history, notifications
    and the delivery version are produced exactly once per real change. Nothing else is created or rewritten.
    """
    cycle = db.get(ProjectReworkCycle, cycle_id, with_for_update=True)   # serialise concurrent package events
    if cycle is None:
        raise ValueError("Rework cycle not found")
    db.flush()
    while True:
        expected = _expected_rework_status(db, cycle)
        if expected is None or expected == cycle.status:
            break
        current_index, expected_index = _REWORK_STAGE_ORDER.index(cycle.status), _REWORK_STAGE_ORDER.index(expected)
        if expected_index > current_index:
            stage = _REWORK_NEXT_STAGE[current_index]
            comments = note
            reference = None
            if stage == "delivered":
                packages = _rework_cycle_packages(db, cycle.id)
                reference = (delivery_reference or "").strip() or f"Rework Cycle {cycle.cycle_number} delivery: {', '.join(pkg.package_code for pkg in packages)}"[:255]
                comments = _rework_delivery_notes(db, cycle, packages, note)
            payload = ReworkStageUpdate(stage=stage, comments=comments, delivery_reference=reference)
        elif expected_index == 0 and cycle.status in {REWORK_QC, REWORK_QA}:
            payload = ReworkStageUpdate(stage="production", comments=note)
        else:
            break
        _apply_rework_stage(db, actor=actor, cycle=cycle, payload=payload)
    return cycle


def reconcile_rework_cycle(db: Session, *, actor: User, cycle_id: int) -> tuple[ProjectReworkCycle, str, str]:
    """Idempotent repair for a cycle that is behind its work packages (e.g. work finished before automatic sync existed)."""
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise ValueError("Rework cycle not found")
    workflow = _workflow(db, cycle.project_id)
    project = _project(db, cycle.project_id)
    pm_id = project.master_profile.project_manager_id if project.master_profile else None
    if not (actor.role == "admin" or actor.id in {cycle.project_manager_user_id, cycle.team_leader_user_id, workflow.bd_owner_user_id, pm_id}):
        raise PermissionError("Only the assigned PM, Team Lead, BD owner or an Admin can reconcile this rework cycle")
    before = cycle.status
    sync_rework_cycle_with_packages(db, actor=actor, cycle_id=cycle_id, note="Reconciled from work-package state")
    return cycle, before, cycle.status


def resubmit_rework(
    db: Session,
    *,
    actor: User,
    cycle_id: int,
    payload: FeedbackRequestCreate,
) -> tuple[ProjectReworkCycle, ProjectFeedbackRequest, str, str]:
    cycle = db.get(ProjectReworkCycle, cycle_id)
    if cycle is None:
        raise ValueError("Rework cycle not found")
    workflow = _workflow(db, cycle.project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can resubmit a rework delivery")
    if cycle.status != REWORK_DELIVERED:
        raise ValueError("The rework must be delivered before client resubmission")
    cycle.status = REWORK_RESUBMITTED
    cycle.resubmitted_at = utc_now()
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=REWORK_RESUBMITTED,
        event_type="rework_resubmitted_to_client",
        title=f"Rework Cycle {cycle.cycle_number} resubmitted to client",
    )
    request_row, token, url = create_feedback_request(db, actor=actor, project_id=cycle.project_id, payload=payload)
    return cycle, request_row, token, url


def recommend_no_feedback_closure(
    db: Session, *, actor: User, request_id: int, payload: NoFeedbackRecommendation
) -> ProjectFeedbackRequest:
    row = db.get(ProjectFeedbackRequest, request_id)
    if row is None:
        raise ValueError("Feedback request not found")
    workflow = _workflow(db, row.project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can recommend no-feedback closure")
    if row.status != "sent" or row.responded_at is not None:
        raise ValueError("No-feedback closure requires an unanswered request")
    if row.reminder_count < 1:
        raise ValueError("Send at least one client reminder before recommending no-feedback closure")
    if row.expires_at > utc_now():
        raise ValueError("The latest client feedback link must expire before no-feedback closure is recommended")
    row.status = "closure_recommended"
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=NO_FEEDBACK_CLOSURE_RECOMMENDED,
        event_type="no_feedback_closure_recommended",
        title="BD recommended No-Feedback Closure",
        comments=payload.remarks,
    )
    project = _project(db, row.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.no_feedback_authorization_required",
        title=f"No-feedback decision required: {project.project_code}",
        message="BD recommends contractual deemed acceptance; authorized confirmation is required.",
        target_url="/management/project-360",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:no-feedback-recommendation:{row.id}",
    )
    return row


def authorize_deemed_acceptance(
    db: Session, *, actor: User, request_id: int, payload: DeemedAcceptanceCreate
) -> ProjectFeedbackRequest:
    if actor.role not in MANAGEMENT_ROLES:
        raise PermissionError("Only Management or Admin can authorize deemed acceptance")
    row = db.get(ProjectFeedbackRequest, request_id)
    if row is None:
        raise ValueError("Feedback request not found")
    if row.status != "closure_recommended":
        raise ValueError("BD no-feedback closure recommendation is required")
    workflow = _workflow(db, row.project_id)
    row.status = "deemed_accepted"
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=DEEMED_ACCEPTED,
        event_type="contractual_deemed_acceptance_authorized",
        title="Authorized / Contractual Deemed Acceptance",
        comments=payload.authority_basis,
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=READY_FOR_BILLING,
        event_type="project_ready_for_billing_deemed_acceptance",
        title="Ready For Billing",
        comments="Authorized no-feedback closure completed.",
    )
    project = _project(db, row.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.deemed_accepted",
        title=f"Ready for billing: {project.project_code}",
        message="authorized deemed acceptance was recorded.",
        target_url="/finance/billing",
        recipient_roles=["finance"],
        dedupe_key=f"lifecycle:deemed-accepted:{row.id}",
    )
    return row


def decide_change_request(
    db: Session, *, actor: User, change_request_id: int, payload: ChangeRequestDecision
) -> ProjectChangeRequest:
    if actor.role not in (MANAGEMENT_ROLES | BD_ROLES | FINANCE_ROLES):
        raise PermissionError("Only Management, BD, Finance or Admin can decide a change request")
    row = db.get(ProjectChangeRequest, change_request_id)
    if row is None:
        raise ValueError("Change request not found")
    if row.status != "pending":
        raise ValueError("Change request has already been decided")
    workflow = _workflow(db, row.project_id)
    if workflow.status != CHANGE_REQUEST_PENDING:
        raise ValueError("Project workflow is not awaiting a change request decision")
    row.status = payload.decision
    row.commercial_impact = payload.commercial_impact
    row.currency = payload.currency.upper()
    row.decided_by_id = actor.id
    row.decision_comments = payload.comments.strip()
    row.decided_at = utc_now()
    project = _project(db, row.project_id)

    if payload.decision == "approved":
        # Route the approved additional scope through the same Production / QC / QA /
        # delivery cycle used for corrections, then resubmit to the client for reconfirmation.
        existing_rework = db.scalar(select(ProjectReworkCycle).where(
            ProjectReworkCycle.source_feedback_response_id == row.source_feedback_response_id
        ))
        if existing_rework is not None:
            raise ValueError("A rework cycle already exists for this change request")
        cycle_number = int(db.scalar(select(func.max(ProjectReworkCycle.cycle_number)).where(
            ProjectReworkCycle.project_id == row.project_id
        )) or 0) + 1
        team_lead_id = db.scalar(select(OrthoProjectMember.user_id).where(
            OrthoProjectMember.project_id == row.project_id,
            OrthoProjectMember.member_role == "team_leader",
            OrthoProjectMember.is_active.is_(True),
        ).order_by(OrthoProjectMember.id.desc()))
        pm_id = project.master_profile.project_manager_id if project.master_profile else None
        rework = ProjectReworkCycle(
            project_id=row.project_id,
            cycle_number=cycle_number,
            source_feedback_response_id=row.source_feedback_response_id,
            cycle_type="APPROVED_CHANGE_REQUEST",
            source_change_request_id=row.id,
            correction_scope=f"Approved additional scope ({row.request_code}): {row.description}",
            project_manager_user_id=pm_id,
            team_leader_user_id=team_lead_id,
            opened_by_id=actor.id,
        )
        db.add(rework)
        db.flush()
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=REWORK_OPEN,
            event_type="change_request_approved",
            title=f"Change Request {row.request_code} Approved",
            comments=payload.comments,
        )
        recipients = [uid for uid in {pm_id, team_lead_id} if uid]
        if recipients:
            _notify(
                db,
                project=project,
                event_type="lifecycle.change_request_approved",
                title=f"Additional scope approved: {project.project_code}",
                message=f"{row.request_code} was approved; rework cycle {cycle_number} is ready for Production.",
                target_url="/ortho",
                recipient_user_ids=recipients,
                dedupe_key=f"lifecycle:change-request-approved:{row.id}",
            )
    else:
        # Rejecting the additional-scope ask does NOT prove the client accepted the
        # original delivery -- the client's response was "additional_scope", never
        # "accepted". Route back to an explicit acceptance-waiting state: BD must
        # send a fresh feedback request and obtain an explicit client acceptance
        # (or an authorized no-feedback / deemed-acceptance decision) before the
        # project can proceed to billing.
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=FEEDBACK_NOT_SENT,
            event_type="change_request_rejected_awaiting_acceptance",
            title=f"Change Request {row.request_code} Rejected",
            comments=(payload.comments or "") + " Original delivery still requires explicit client acceptance before billing.",
        )
        _notify(
            db,
            project=project,
            event_type="lifecycle.change_request_rejected",
            title=f"Additional scope rejected: {project.project_code}",
            message=f"{row.request_code} was rejected. Send a client feedback request to obtain explicit acceptance before billing.",
            target_url="/bd/feedback",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:change-request-rejected:{row.id}",
        )
    return row


def create_invoice_draft(
    db: Session, *, actor: User, project_id: int, payload: InvoiceDraftCreate
) -> ProjectInvoice:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if workflow.status not in {READY_FOR_BILLING, INVOICE_DRAFT}:
        raise ValueError("Client acceptance and Ready For Billing are required before invoice drafting")
    invoice_number = payload.invoice_number.strip()
    if db.scalar(select(ProjectInvoice.id).where(ProjectInvoice.invoice_number == invoice_number)) is not None:
        raise ValueError("Invoice number already exists")
    tax_percent = payload.tax_percent
    if tax_percent is None:
        tax_percent = ((Decimal(payload.tax_amount) / Decimal(payload.amount)) * Decimal("100")).quantize(Decimal("0.01"))
    invoice = ProjectInvoice(
        project_id=project_id,
        invoice_number=invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        amount=payload.amount,
        tax_amount=payload.tax_amount,
        tax_percent=tax_percent,
        currency=payload.currency.upper(),
        payment_terms=(payload.payment_terms or "").strip() or None,
        po_wo_reference=(payload.po_wo_reference or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
        created_by_id=actor.id,
    )
    from app.modules.commercial.service import apply_invoice_billing_links, prepare_client_invoice_fx

    # Validate the approved-basis / PM-basis links BEFORE the row is added, so a rejected link leaves nothing behind.
    apply_invoice_billing_links(
        db,
        invoice=invoice,
        estimate_revision_id=payload.estimate_revision_id,
        billing_basis_id=payload.billing_basis_id,
        billed_quantity=payload.billed_quantity,
        billed_milestone_id=payload.billed_milestone_id,
    )
    db.add(invoice)
    db.flush()
    prepare_client_invoice_fx(
        db,
        actor=actor,
        invoice=invoice,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=INVOICE_DRAFT,
        event_type="invoice_draft_created",
        title=f"Invoice Draft {invoice.invoice_number}",
        comments=f"{invoice.currency} {invoice.amount + invoice.tax_amount}",
    )
    return invoice


def raise_invoice(
    db: Session, *, actor: User, invoice_id: int, payload: InvoiceRaise
) -> ProjectInvoice:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    if invoice.status != INVOICE_DRAFT:
        raise ValueError("Only a draft invoice can be raised")
    from app.modules.commercial.service import lock_client_invoice_fx

    lock_client_invoice_fx(
        db,
        actor=actor,
        invoice=invoice,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
    )
    invoice.status = INVOICE_RAISED
    invoice.raised_by_id = actor.id
    invoice.raised_at = utc_now()
    if payload.notes:
        invoice.notes = payload.notes.strip()
    workflow = _workflow(db, invoice.project_id)
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=INVOICE_RAISED,
        event_type="invoice_raised",
        title=f"Invoice Raised {invoice.invoice_number}",
        comments=f"Due {invoice.due_date.isoformat()}",
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=PAYMENT_PENDING,
        event_type="invoice_payment_pending",
        title="Payment Pending",
        comments=f"Invoice {invoice.invoice_number}",
    )
    project = _project(db, invoice.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.invoice_raised",
        title=f"Invoice raised: {project.project_code}",
        message=f"invoice {invoice.invoice_number} is due {invoice.due_date.isoformat()}.",
        target_url="/management/project-360",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:invoice-raised:{invoice.id}",
    )
    return invoice


def _payment_total(db: Session, invoice_id: int) -> Decimal:
    return Decimal(db.scalar(select(func.coalesce(func.sum(ProjectInvoicePayment.amount), 0)).where(
        ProjectInvoicePayment.invoice_id == invoice_id
    )) or 0)


def record_invoice_payment(
    db: Session, *, actor: User, invoice_id: int, payload: InvoicePaymentCreate
) -> ProjectInvoicePayment:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    if invoice.status not in {INVOICE_RAISED, PAYMENT_PENDING, PARTIALLY_PAID, PAYMENT_OVERDUE}:
        raise ValueError("Payments can only be recorded against an open raised invoice")
    total_due = Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0)
    paid_before = _payment_total(db, invoice.id)
    if paid_before + payload.amount > total_due:
        raise ValueError("Payment exceeds the outstanding invoice balance")
    payment = ProjectInvoicePayment(
        project_id=invoice.project_id,
        invoice_id=invoice.id,
        payment_reference=payload.payment_reference.strip(),
        payment_date=payload.payment_date,
        amount=payload.amount,
        payment_mode=payload.payment_mode.strip().lower(),
        comments=(payload.comments or "").strip() or None,
        recorded_by_id=actor.id,
    )
    db.add(payment)
    db.flush()
    from app.modules.commercial.service import prepare_client_payment_fx

    prepare_client_payment_fx(
        db,
        actor=actor,
        invoice=invoice,
        payment=payment,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
    )
    paid_after = paid_before + payload.amount
    complete = paid_after == total_due
    invoice.status = PAYMENT_RECEIVED if complete else PARTIALLY_PAID
    workflow = _workflow(db, invoice.project_id)
    state = PAYMENT_RECEIVED if complete else PARTIALLY_PAID
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=state,
        event_type="invoice_payment_received" if complete else "invoice_partial_payment",
        title="Payment Received" if complete else "Partial Payment",
        comments=f"{invoice.currency} {payload.amount} ({payload.payment_reference})",
    )
    project = _project(db, invoice.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.payment_received" if complete else "lifecycle.partial_payment",
        title=("Payment received" if complete else "Partial payment") + f": {project.project_code}",
        message=f"{invoice.currency} {payload.amount} recorded for invoice {invoice.invoice_number}.",
        target_url="/management/project-360",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:payment:{payment.id}",
    )
    return payment


def mark_invoice_overdue(db: Session, *, actor: User, invoice_id: int) -> ProjectInvoice:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    if invoice.due_date >= date.today():
        raise ValueError("Invoice is not overdue")
    if invoice.status not in {INVOICE_RAISED, PAYMENT_PENDING, PARTIALLY_PAID}:
        raise ValueError("Only an unpaid open invoice can be marked overdue")
    invoice.status = PAYMENT_OVERDUE
    workflow = _workflow(db, invoice.project_id)
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=PAYMENT_OVERDUE,
        event_type="invoice_payment_overdue",
        title="Payment Overdue",
        comments=f"Invoice {invoice.invoice_number} was due {invoice.due_date.isoformat()}",
    )
    project = _project(db, invoice.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.payment_overdue",
        title=f"Payment overdue: {project.project_code}",
        message=f"invoice {invoice.invoice_number} is overdue.",
        target_url="/finance/billing",
        recipient_roles=["finance", "management"],
        dedupe_key=f"lifecycle:invoice-overdue:{invoice.id}",
    )
    return invoice


def close_invoice(
    db: Session, *, actor: User, invoice_id: int, payload: InvoiceClose
) -> ProjectInvoice:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    total_due = Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0)
    if _payment_total(db, invoice.id) < total_due or invoice.status != PAYMENT_RECEIVED:
        raise ValueError("Full payment is required before invoice closure")
    invoice.status = INVOICE_CLOSED
    invoice.closed_by_id = actor.id
    invoice.closed_at = utc_now()
    workflow = _workflow(db, invoice.project_id)
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=INVOICE_CLOSED,
        event_type="invoice_closed",
        title=f"Invoice Closed {invoice.invoice_number}",
        comments=payload.comments,
    )
    open_count = int(db.scalar(select(func.count(ProjectInvoice.id)).where(
        ProjectInvoice.project_id == invoice.project_id,
        ProjectInvoice.id != invoice.id,
        ProjectInvoice.status != INVOICE_CLOSED,
    )) or 0)
    if open_count == 0:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=FINANCE_CLOSURE_PENDING,
            event_type="finance_closure_pending",
            title="Finance Closure Pending",
            comments="All invoices are fully paid and closed.",
        )
    return invoice


def assert_finance_closable(db: Session, *, workflow: ProjectWorkflow) -> None:
    """Apply V8.1 closure guards while grandfathering legacy pre-lifecycle rows."""
    if workflow.status == "finance_closure_pending":
        has_lifecycle = db.scalar(select(ProjectTimelineEvent.id).where(
            ProjectTimelineEvent.project_id == workflow.project_id
        ).limit(1))
        if has_lifecycle is None:
            # Preserve the legacy lifecycle grandfathering rule, but still enforce
            # Commercial settlement when this legacy project has opted into the new
            # commercial/cost layer. The Commercial guard itself is a no-op when no
            # commercial records exist.
            from app.modules.commercial.service import assert_commercial_closure_ready

            assert_commercial_closure_ready(db, project_id=workflow.project_id)
            return
    if workflow.status != FINANCE_CLOSURE_PENDING:
        raise ValueError("Finance Closure Pending is required before Finance Closure")
    accepted = db.scalar(select(ProjectTimelineEvent.id).where(
        ProjectTimelineEvent.project_id == workflow.project_id,
        ProjectTimelineEvent.status.in_([CLIENT_ACCEPTED, DEEMED_ACCEPTED]),
    ).limit(1))
    if accepted is None:
        raise ValueError("Client acceptance or authorized deemed acceptance is required")
    ready = db.scalar(select(ProjectTimelineEvent.id).where(
        ProjectTimelineEvent.project_id == workflow.project_id,
        ProjectTimelineEvent.status == READY_FOR_BILLING,
    ).limit(1))
    if ready is None:
        raise ValueError("Ready For Billing is required")
    invoices = list(db.scalars(select(ProjectInvoice).where(ProjectInvoice.project_id == workflow.project_id)).all())
    if not invoices:
        raise ValueError("At least one invoice is required")
    for invoice in invoices:
        if invoice.status != INVOICE_CLOSED:
            raise ValueError(f"Invoice {invoice.invoice_number} must be fully paid and closed")
        if _payment_total(db, invoice.id) < Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0):
            raise ValueError(f"Invoice {invoice.invoice_number} has an outstanding payment balance")

    # Additive V8.1 Commercial guard: unresolved estimate revisions, employee
    # expenses/declarations, or vendor payables must not be silently bypassed.
    from app.modules.commercial.service import assert_commercial_closure_ready

    assert_commercial_closure_ready(db, project_id=workflow.project_id)


def record_project_closed_timeline(db: Session, *, actor: User, project_id: int, remarks: str) -> None:
    add_timeline_event(
        db,
        project_id=project_id,
        event_type="project_closed",
        title="Project Closed",
        status=CLOSED,
        actor_user_id=actor.id,
        details=remarks,
    )


def _invoice_payload(db: Session, row: ProjectInvoice) -> dict:
    paid = _payment_total(db, row.id)
    due = Decimal(row.amount) + Decimal(row.tax_amount or 0)
    effective_status = row.status
    if row.status in {INVOICE_RAISED, PAYMENT_PENDING, PARTIALLY_PAID} and row.due_date < date.today() and paid < due:
        effective_status = PAYMENT_OVERDUE
    payments = list(db.scalars(select(ProjectInvoicePayment).where(
        ProjectInvoicePayment.invoice_id == row.id
    ).order_by(ProjectInvoicePayment.payment_date.asc(), ProjectInvoicePayment.id.asc())).all())
    return {
        "id": row.id,
        "invoice_number": row.invoice_number,
        "status": effective_status,
        "stored_status": row.status,
        "invoice_date": row.invoice_date.isoformat(),
        "due_date": row.due_date.isoformat(),
        "amount": float(row.amount),
        "tax_amount": float(row.tax_amount or 0),
        "total_amount": float(due),
        "paid_amount": float(paid),
        "balance": float(max(Decimal("0"), due - paid)),
        "currency": row.currency,
        "tax_percent": float(row.tax_percent) if row.tax_percent is not None else None,
        "payment_terms": row.payment_terms,
        "po_wo_reference": row.po_wo_reference,
        "fx_snapshot_id": row.fx_snapshot_id,
        "fx_rate_to_inr": float(row.fx_rate_to_inr) if row.fx_rate_to_inr is not None else None,
        "fx_rate_date": row.fx_rate_date.isoformat() if row.fx_rate_date else None,
        "fx_rate_source": row.fx_rate_source,
        "fx_rate_mode": row.fx_rate_mode,
        "base_inr": float(row.base_inr) if row.base_inr is not None else None,
        "tax_inr": float(row.tax_inr) if row.tax_inr is not None else None,
        "total_inr": float(row.total_inr) if row.total_inr is not None else None,
        "fx_locked": bool(row.fx_locked),
        "estimate_revision_id": row.estimate_revision_id,
        "billing_basis_id": row.billing_basis_id,
        "billed_quantity": float(row.billed_quantity) if row.billed_quantity is not None else None,
        "billed_milestone_id": row.billed_milestone_id,
        "notes": row.notes,
        "raised_at": row.raised_at.isoformat() if row.raised_at else None,
        "closed_at": row.closed_at.isoformat() if row.closed_at else None,
        "payments": [
            {
                "id": payment.id,
                "payment_reference": payment.payment_reference,
                "payment_date": payment.payment_date.isoformat(),
                "amount": float(payment.amount),
                "payment_currency": payment.payment_currency or row.currency,
                "fx_snapshot_id": payment.fx_snapshot_id,
                "fx_rate_to_inr": float(payment.fx_rate_to_inr) if payment.fx_rate_to_inr is not None else None,
                "fx_rate_date": payment.fx_rate_date.isoformat() if payment.fx_rate_date else None,
                "fx_rate_source": payment.fx_rate_source,
                "fx_rate_mode": payment.fx_rate_mode,
                "inr_equivalent": float(payment.inr_equivalent) if payment.inr_equivalent is not None else None,
                "invoice_inr_equivalent": float(payment.invoice_inr_equivalent) if payment.invoice_inr_equivalent is not None else None,
                "fx_gain_loss_inr": float(payment.fx_gain_loss_inr) if payment.fx_gain_loss_inr is not None else None,
                "payment_mode": payment.payment_mode,
                "comments": payment.comments,
                "created_at": payment.created_at.isoformat(),
            }
            for payment in payments
        ],
    }


def _timeline_payload(db: Session, project_id: int) -> list[dict]:
    lifecycle = list(db.scalars(select(ProjectTimelineEvent).where(
        ProjectTimelineEvent.project_id == project_id
    ).order_by(ProjectTimelineEvent.occurred_at.asc(), ProjectTimelineEvent.id.asc())).all())
    workflow_events = list(db.scalars(select(ProjectWorkflowEvent).where(
        ProjectWorkflowEvent.project_id == project_id
    ).order_by(ProjectWorkflowEvent.created_at.asc(), ProjectWorkflowEvent.id.asc())).all())
    user_ids = {row.actor_user_id for row in lifecycle if row.actor_user_id} | {
        row.actor_user_id for row in workflow_events if row.actor_user_id
    }
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    rows = [
        {
            "id": f"workflow-{row.id}",
            "event_type": row.event_type,
            "title": row.event_type.replace("_", " ").title(),
            "details": row.comments,
            "status": row.to_status,
            "actor_name": users[row.actor_user_id].full_name if row.actor_user_id in users else None,
            "occurred_at": row.created_at.isoformat(),
            "source": "workflow",
        }
        for row in workflow_events
    ] + [
        {
            "id": f"lifecycle-{row.id}",
            "event_type": row.event_type,
            "title": row.title,
            "details": row.details,
            "status": row.status,
            "actor_name": users[row.actor_user_id].full_name if row.actor_user_id in users else None,
            "occurred_at": row.occurred_at.isoformat(),
            "source": "lifecycle",
        }
        for row in lifecycle
    ]
    return sorted(rows, key=lambda item: (item["occurred_at"], item["id"]))


def _project_summary(db: Session, project: FinanceProject, workflow: ProjectWorkflow) -> dict:
    invoices = list(db.scalars(select(ProjectInvoice).where(
        ProjectInvoice.project_id == project.id
    ).order_by(ProjectInvoice.id.asc())).all())
    reworks = list(db.scalars(select(ProjectReworkCycle).where(
        ProjectReworkCycle.project_id == project.id
    ).order_by(ProjectReworkCycle.cycle_number.asc())).all())
    packages = list(db.scalars(select(OrthoWorkPackage).where(OrthoWorkPackage.project_id == project.id)).all())
    delivered = sum(1 for package in packages if package.current_stage == "delivered")
    progress = round((delivered / len(packages)) * 100, 1) if packages else (100.0 if workflow.operational_completed_at else 0.0)
    client = project.client
    pm = project.master_profile.project_manager if project.master_profile else None
    tl_id = db.scalar(select(OrthoProjectMember.user_id).where(
        OrthoProjectMember.project_id == project.id,
        OrthoProjectMember.member_role == "team_leader",
        OrthoProjectMember.is_active.is_(True),
    ).order_by(OrthoProjectMember.id.desc()))
    tl = db.get(User, tl_id) if tl_id else None
    return {
        "id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "client_id": client.client_code if client else None,
        "client_name": (client.client_name or "") if client else (project.client_name or ""),
        "workflow_status": workflow.status,
        "project_manager_id": pm.id if pm else None,
        "project_manager_name": pm.full_name if pm else None,
        "team_leader_id": tl.id if tl else None,
        "team_leader_name": tl.full_name if tl else None,
        "current_stage": workflow.status,
        "progress_percent": progress,
        "operational_completed_at": workflow.operational_completed_at.isoformat() if workflow.operational_completed_at else None,
        "rework_count": len(reworks),
        "latest_rework_status": reworks[-1].status if reworks else None,
        "latest_rework_cycle_type": reworks[-1].cycle_type if reworks else None,
        "invoice_count": len(invoices),
        "invoice_balance": sum(item["balance"] for item in (_invoice_payload(db, invoice) for invoice in invoices)),
        "has_overdue_invoice": any(_invoice_payload(db, invoice)["status"] == PAYMENT_OVERDUE for invoice in invoices),
    }


def lifecycle_dashboard(db: Session, *, actor: User, role: str) -> dict:
    query = _project_query().join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
    if role == "bd":
        query = query.where(ProjectWorkflow.bd_owner_user_id == actor.id)
    elif role == "ortho":
        query = query.join(FinanceProjectMasterProfile).where(FinanceProjectMasterProfile.project_manager_id == actor.id)
    projects = list(db.scalars(query.order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())).unique().all())
    workflows = {row.project_id: row for row in db.scalars(select(ProjectWorkflow).where(
        ProjectWorkflow.project_id.in_([project.id for project in projects])
    )).all()} if projects else {}
    rows = [_project_summary(db, project, workflows[project.id]) for project in projects if project.id in workflows]
    if role == "ortho":
        rows = [_pm_restricted_project_view(row) for row in rows]
    statuses = [row["workflow_status"] for row in rows]
    summary = {
        "total_projects": len(rows),
        "active_projects": sum(status not in {CLOSED, "closed"} for status in statuses),
        "completed_projects": sum(row["operational_completed_at"] is not None for row in rows),
        "awaiting_feedback": sum(status in {FEEDBACK_NOT_SENT, FEEDBACK_REQUESTED, FEEDBACK_REMINDER_SENT, AWAITING_CLIENT_FEEDBACK} for status in statuses),
        "rework": sum(status in {FEEDBACK_NEGATIVE, REWORK_OPEN, REWORK_PRODUCTION, REWORK_QC, REWORK_QA, REWORK_DELIVERED, REWORK_RESUBMITTED} for status in statuses),
        "ready_for_billing": statuses.count(READY_FOR_BILLING),
        "payment_pending": sum(status in {PAYMENT_PENDING, PARTIALLY_PAID} for status in statuses),
        "overdue": sum(row["has_overdue_invoice"] for row in rows),
        "closed": sum(status in {CLOSED, "closed"} for status in statuses),
    }
    payload = {"summary": summary, "projects": rows}
    if role in MANAGEMENT_ROLES:
        payload["department_overview"] = {
            "bd": {
                "clients": int(db.scalar(select(func.count(FinanceClient.id))) or 0),
                "projects": len(rows),
                "pending_finance_approvals": statuses.count("pending_finance_approval"),
                "returned_projects": statuses.count("finance_returned"),
                "pm_unassigned": sum(row["project_manager_id"] is None for row in rows),
            },
            "finance": {
                "project_approvals": statuses.count("pending_finance_approval"),
                "clients": int(db.scalar(select(func.count(FinanceClient.id))) or 0),
                "projects": len(rows),
                "payment_pending": summary["payment_pending"],
                "overdue": summary["overdue"],
            },
            "ortho": {
                "active_projects": sum(status not in {CLOSED, "closed"} for status in statuses),
                "rework": summary["rework"],
                "operationally_completed": summary["completed_projects"],
            },
            "drone": {
                "active_projects": int(db.scalar(select(func.count(DroneProject.id)).where(
                    DroneProject.status.notin_(["closed", "completed", "cancelled"])
                )) or 0),
            },
            "it": {
                "active_support_tickets": int(db.scalar(select(func.count(SupportTicket.id)).where(
                    SupportTicket.status.notin_(["resolved", "closed"])
                )) or 0),
                "active_assets": int(db.scalar(select(func.count(Asset.id)).where(Asset.status != "retired")) or 0),
            },
            "hr": {
                "active_employees": int(db.scalar(select(func.count(User.id)).where(
                    User.is_active.is_(True), User.account_status == "active"
                )) or 0),
            },
            "employee_support": {
                "open_tickets": int(db.scalar(select(func.count(SupportTicket.id)).where(
                    SupportTicket.status.notin_(["resolved", "closed"])
                )) or 0),
            },
        }
    return payload


def _pm_restricted_project_view(payload: dict) -> dict:
    """Strip client identity and commercial/financial detail for the assigned Ortho
    Project Manager. Per V8.1 privacy rules, PM/Production/QC/QA may see the Project
    ID, permitted Client ID, PM/TL/team, stage/progress, feedback/rework operational
    status, delivery versions and the relevant operational timeline -- never the
    Client Name, commercial impact, invoices or payment information.
    """
    restricted = dict(payload)
    restricted["client_name"] = None
    if "invoice_count" in restricted:
        restricted["invoice_count"] = 0
    if "invoice_balance" in restricted:
        restricted["invoice_balance"] = 0.0
    if "has_overdue_invoice" in restricted:
        restricted["has_overdue_invoice"] = False
    if "invoices" in restricted:
        restricted["invoices"] = []
    if "feedback_requests" in restricted:
        restricted["feedback_requests"] = [
            {**row, "recipient_email": None} for row in payload["feedback_requests"]
        ]
    if "change_requests" in restricted:
        restricted["change_requests"] = [
            {**row, "commercial_impact": None} for row in payload["change_requests"]
        ]
    return restricted


def project_360(db: Session, *, actor: User, role: str, project_id: int) -> dict:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if role == "bd" and workflow.bd_owner_user_id != actor.id:
        raise PermissionError("Project is not assigned to this BD user")
    if role == "ortho" and (not project.master_profile or project.master_profile.project_manager_id != actor.id):
        raise PermissionError("Project is not assigned to this Project Manager")
    summary = _project_summary(db, project, workflow)
    member_rows = list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id == project_id,
        OrthoProjectMember.is_active.is_(True),
    ).order_by(OrthoProjectMember.id.asc())).all())
    users = {user.id: user for user in db.scalars(select(User).where(
        User.id.in_({row.user_id for row in member_rows})
    )).all()} if member_rows else {}
    feedback_requests = list(db.scalars(select(ProjectFeedbackRequest).where(
        ProjectFeedbackRequest.project_id == project_id
    ).order_by(ProjectFeedbackRequest.cycle_number.asc())).all())
    feedback_responses = list(db.scalars(select(ProjectFeedbackResponse).where(
        ProjectFeedbackResponse.project_id == project_id
    ).order_by(ProjectFeedbackResponse.responded_at.asc())).all())
    reworks = list(db.scalars(select(ProjectReworkCycle).where(
        ProjectReworkCycle.project_id == project_id
    ).order_by(ProjectReworkCycle.cycle_number.asc())).all())
    deliveries = list(db.scalars(select(ProjectDeliveryVersion).where(
        ProjectDeliveryVersion.project_id == project_id
    ).order_by(ProjectDeliveryVersion.version_number.asc())).all())
    changes = list(db.scalars(select(ProjectChangeRequest).where(
        ProjectChangeRequest.project_id == project_id
    ).order_by(ProjectChangeRequest.id.asc())).all())
    invoices = list(db.scalars(select(ProjectInvoice).where(
        ProjectInvoice.project_id == project_id
    ).order_by(ProjectInvoice.id.asc())).all())
    payload = {
        **summary,
        "scope": workflow.scope_text,
        "selected_team": [
            {
                "user_id": row.user_id,
                "name": users[row.user_id].full_name if row.user_id in users else None,
                "role": row.member_role,
            }
            for row in member_rows
        ],
        "timeline": _timeline_payload(db, project_id),
        "feedback_requests": [
            {
                "id": row.id,
                "request_code": row.request_code,
                "cycle_number": row.cycle_number,
                "recipient_email": row.recipient_email,
                "status": row.status,
                "expires_at": row.expires_at.isoformat(),
                "sent_at": row.sent_at.isoformat(),
                "reminder_count": row.reminder_count,
                "responded_at": row.responded_at.isoformat() if row.responded_at else None,
                "message_thread_id": row.message_thread_id,
            }
            for row in feedback_requests
        ],
        "feedback_responses": [
            {
                "id": row.id,
                "feedback_request_id": row.feedback_request_id,
                "response_type": row.response_type,
                "comments": row.comments,
                "correction_description": row.correction_description,
                "classification_status": row.classification_status,
                "classified_as": row.classified_as,
                "responded_at": row.responded_at.isoformat(),
            }
            for row in feedback_responses
        ],
        "rework_cycles": [
            {
                "id": row.id,
                "cycle_number": row.cycle_number,
                "cycle_type": row.cycle_type,
                "source_change_request_id": row.source_change_request_id,
                "status": row.status,
                "correction_scope": row.correction_scope,
                "opened_at": row.opened_at.isoformat(),
                "delivered_at": row.delivered_at.isoformat() if row.delivered_at else None,
                "resubmitted_at": row.resubmitted_at.isoformat() if row.resubmitted_at else None,
                "expected_status": _expected_rework_status(db, row),
                "out_of_sync": (_expected_rework_status(db, row) not in (None, row.status)),
            }
            for row in reworks
        ],
        "delivery_versions": [
            {
                "id": row.id,
                "version_number": row.version_number,
                "rework_cycle_id": row.rework_cycle_id,
                "delivery_reference": row.delivery_reference,
                "notes": row.notes,
                "delivered_at": row.delivered_at.isoformat(),
            }
            for row in deliveries
        ],
        "change_requests": [
            {
                "id": row.id,
                "request_code": row.request_code,
                "description": row.description,
                "status": row.status,
                "commercial_impact": float(row.commercial_impact) if row.commercial_impact is not None else None,
                "currency": row.currency,
                "decision_comments": row.decision_comments,
                "created_at": row.created_at.isoformat(),
            }
            for row in changes
        ],
        "invoices": [_invoice_payload(db, row) for row in invoices],
    }
    if role == "ortho":
        return _pm_restricted_project_view(payload)
    return payload


def list_project_messages(db: Session, *, actor: User, role: str, project_id: int) -> list[dict]:
    project = _project(db, project_id)
    pm_id = project.master_profile.project_manager_id if project.master_profile else None
    if role not in MANAGEMENT_ROLES and actor.id != pm_id:
        raise PermissionError("Project Chat is limited to Management and the assigned Project Manager")
    query = select(ProjectMessage).where(ProjectMessage.project_id == project_id)
    if role not in MANAGEMENT_ROLES:
        query = query.where(or_(ProjectMessage.sender_user_id == actor.id, ProjectMessage.recipient_user_id == actor.id))
    rows = list(db.scalars(query.order_by(ProjectMessage.created_at.asc(), ProjectMessage.id.asc())).all())
    user_ids = {row.sender_user_id for row in rows} | {row.recipient_user_id for row in rows}
    users = {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()} if user_ids else {}
    for row in rows:
        if row.recipient_user_id == actor.id and not row.is_read:
            row.is_read = True
            row.read_at = utc_now()
    return [
        {
            "id": row.id,
            "sender_user_id": row.sender_user_id,
            "sender_name": users[row.sender_user_id].full_name if row.sender_user_id in users else None,
            "recipient_user_id": row.recipient_user_id,
            "recipient_name": users[row.recipient_user_id].full_name if row.recipient_user_id in users else None,
            "message": row.message,
            "is_read": row.is_read,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]


def create_project_message(
    db: Session,
    *,
    actor: User,
    role: str,
    project_id: int,
    payload: ProjectMessageCreate,
) -> ProjectMessage:
    project = _project(db, project_id)
    pm_id = project.master_profile.project_manager_id if project.master_profile else None
    if pm_id is None:
        raise ValueError("Project Manager is not assigned")
    if role in MANAGEMENT_ROLES:
        recipient_id = pm_id
    elif actor.id == pm_id:
        recipient_id = payload.recipient_user_id
        recipient = db.get(User, recipient_id) if recipient_id else None
        if recipient is None or recipient.role != "management" or not recipient.is_active:
            raise ValueError("Select an active Management recipient")
    else:
        raise PermissionError("Project Chat is limited to Management and the assigned Project Manager")
    row = ProjectMessage(
        project_id=project_id,
        sender_user_id=actor.id,
        recipient_user_id=recipient_id,
        message=payload.message.strip(),
    )
    db.add(row)
    db.flush()
    create_global_notification(
        db,
        event_type="lifecycle.project_chat",
        title=f"Project chat: {project.project_code}",
        message=f"{actor.full_name} sent a Project Chat message.",
        category="system",
        target_url="/management/project-360" if role != "management" else "/ortho",
        recipient_user_ids=[recipient_id],
        dedupe_key=f"lifecycle:project-message:{row.id}",
    )
    add_timeline_event(
        db,
        project_id=project_id,
        event_type="project_chat_message",
        title="Project Chat message",
        status=None,
        actor_user_id=actor.id,
        details="Management / Project Manager project communication",
    )
    return row
