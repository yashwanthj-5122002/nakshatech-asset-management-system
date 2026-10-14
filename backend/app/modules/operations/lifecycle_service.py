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
from app.core.departments import is_technical_pm_role
from app.models.entities import Asset, User, utc_now
from app.modules.drone.models import DroneProject
from app.modules.employee_portal.models import SupportTicket
from app.modules.employee_portal.service import send_email
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.finance.visibility import exclude_hidden_clients, exclude_hidden_projects
from app.modules.notifications.service import create_global_notification
from app.core.management_access import MANAGEMENT_EMAILS
from app.modules.operations.lifecycle_models import (
    ProjectChangeRequest,
    ProjectDeliveryVersion,
    ProjectFeedbackAttachment,
    ProjectFeedbackRequest,
    ProjectFeedbackResponse,
    ProjectInvoice,
    ProjectInvoiceLineItem,
    ProjectInvoicePayment,
    ProjectInvoiceBadDebt,
    ProjectInvoiceBadDebtApproval,
    ProjectMessage,
    ProjectReworkCycle,
    ProjectTimelineEvent,
)
from app.modules.operations.lifecycle_schemas import (
    BadDebtDecision,
    BadDebtProposalCreate,
    BadDebtRecoveryCreate,
    ChangeRequestDecision,
    DeemedAcceptanceCreate,
    FeedbackClassification,
    FeedbackRequestCreate,
    FeedbackResponseCreate,
    InvoiceBillingSnapshotOverride,
    InvoiceClose,
    InvoiceDraftCreate,
    InvoicePaymentCreate,
    InvoiceRaise,
    ManualFeedbackResponseCreate,
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
CLIENT_ACCEPTANCE_PENDING_BD = "CLIENT_ACCEPTANCE_PENDING_BD"
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
        target_url=f"/bd/feedback?project={project.id}",
        recipient_user_ids=[workflow.bd_owner_user_id],
        dedupe_key=f"lifecycle:operational-complete:{project.id}",
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.operational_completed_management",
        title=f"Operational completion: {project.project_code}",
        message="entered the client feedback lifecycle.",
        target_url=f"/management/project-360/{project.id}",
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
        target_url=f"/management/project-360/{project.id}",
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
        # Every client response is confirmed by the owning BD user before it can
        # drive an internal workflow transition. This keeps the client-facing
        # response and NakshaTech's internal billing/rework decision separate.
        classification_status="pending_bd",
        classified_as=None,
        classified_by_id=None,
        classified_at=None,
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
            status=CLIENT_ACCEPTANCE_PENDING_BD,
            event_type="client_acceptance_requires_bd_confirmation",
            title="Client acceptance requires BD confirmation",
            comments=payload.comments,
        )
        _notify(
            db,
            project=project,
            event_type="lifecycle.client_acceptance_requires_bd",
            title=f"Client accepted: {project.project_code}",
            message="The client submitted positive feedback. Confirm acceptance and send the project to Finance for billing.",
            target_url=f"/bd/feedback?project={project.id}&response={response.id}",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:accepted-awaiting-bd:{response.id}",
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
            target_url=f"/bd/feedback?project={project.id}",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:classify-response:{response.id}",
        )
    return response


def record_manual_feedback_response(
    db: Session,
    *,
    actor: User,
    project_id: int,
    payload: ManualFeedbackResponseCreate,
) -> ProjectFeedbackResponse:
    """BD records an offline client outcome (call, email or letter).

    This is the BD Feedback Action Center's manual path for clients that never
    respond through the secure portal link. It creates a ProjectFeedbackResponse
    row marked source='bd_manual' and then reuses the exact same transitions as
    a portal response: positive -> CLIENT_ACCEPTANCE_PENDING_BD (BD confirms via
    confirm_client_acceptance), negative -> FEEDBACK_NEGATIVE (BD classifies via
    classify_feedback_response). No competing transition is introduced.
    """
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if workflow.bd_owner_user_id != actor.id and actor.role != "admin":
        raise PermissionError("Only the project BD owner can record a manual client feedback response")
    allowed = {FEEDBACK_NOT_SENT, FEEDBACK_REQUESTED, FEEDBACK_REMINDER_SENT, AWAITING_CLIENT_FEEDBACK}
    if workflow.status not in allowed:
        raise ValueError(f"Manual client feedback cannot be recorded while project is {workflow.status}")

    positive = payload.response_type == "accepted"
    response = ProjectFeedbackResponse(
        project_id=project_id,
        feedback_request_id=None,
        response_type=payload.response_type,
        comments=(payload.comments or "").strip() or None,
        correction_description=(payload.correction_description or "").strip() or None,
        client_name=(payload.client_name or "").strip() or None,
        client_email=None,
        external_message_id=(payload.reference or "").strip() or None,
        source="bd_manual",
        classification_status="pending_bd",
        classified_as=None,
        classified_by_id=None,
        classified_at=None,
    )
    db.add(response)
    db.flush()
    if positive:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=CLIENT_ACCEPTANCE_PENDING_BD,
            event_type="client_acceptance_requires_bd_confirmation",
            title="Client acceptance requires BD confirmation",
            comments=payload.comments,
        )
    else:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=FEEDBACK_NEGATIVE,
            event_type="client_feedback_requires_classification",
            title="Client feedback requires BD classification",
            comments=payload.correction_description,
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


def confirm_client_acceptance(
    db: Session, *, actor: User, response_id: int
) -> ProjectFeedbackResponse:
    response = db.get(ProjectFeedbackResponse, response_id)
    if response is None:
        raise ValueError("Feedback response not found")
    if response.response_type != "accepted":
        raise ValueError("Only positive client feedback can be confirmed as accepted")
    workflow = _workflow(db, response.project_id)
    if workflow.bd_owner_user_id != actor.id and (actor.role or "").lower() != "admin":
        raise PermissionError("Only the owning BD user can confirm client acceptance")
    if response.classification_status == "confirmed" and response.classified_as == "accepted":
        return response
    if response.classification_status != "pending_bd":
        raise ValueError("This client acceptance is not awaiting BD confirmation")
    project = _project(db, response.project_id)
    response.classification_status = "confirmed"
    response.classified_as = "accepted"
    response.classified_by_id = actor.id
    response.classified_at = utc_now()
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=CLIENT_ACCEPTED,
        event_type="bd_confirmed_client_acceptance",
        title="Client Accepted",
        comments=response.comments,
    )
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=READY_FOR_BILLING,
        event_type="project_ready_for_billing",
        title="Ready For Billing",
        comments="BD confirmed the client's positive feedback and released the project for billing.",
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.client_accepted",
        title=f"Ready for billing: {project.project_code}",
        message="BD confirmed positive client feedback. Finance can prepare the invoice using the approved commercial and PM billing basis.",
        target_url=f"/finance/billing?project={project.id}",
        recipient_roles=["finance"],
        dedupe_key=f"lifecycle:client-accepted:{response.id}",
    )
    return response


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
            target_url=f"/bd/feedback?project={project.id}",
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
        target_url=f"/management/project-360/{project.id}",
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
        target_url=f"/finance/billing?project={project.id}",
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
            target_url=f"/bd/feedback?project={project.id}",
            recipient_user_ids=[workflow.bd_owner_user_id],
            dedupe_key=f"lifecycle:change-request-rejected:{row.id}",
        )
    return row


def _resolve_invoice_document_snapshot(db: Session, *, project: FinanceProject, overrides: "InvoiceBillingSnapshotOverride | None") -> dict:
    """Build the point-in-time billing/company/bank snapshot for a new invoice.

    Auto Fill mode calls this with no overrides (pure ERP data). Manual mode may supply
    ``overrides`` for any subset of fields; everything left blank still falls back to the
    live Client Master / app configuration, exactly like Auto Fill. Once stored on the
    invoice, this dict is what every later preview/PDF/print reads — a later Client Master
    edit or company-configuration change never retroactively changes an issued invoice.
    """
    from app.modules.operations.invoice_documents import _configured_company

    client = project.client
    override = overrides.model_dump() if overrides is not None else {}
    company = _configured_company()

    def pick(key: str, fallback):
        value = override.get(key)
        return value if value not in (None, "") else fallback

    return {
        "billing": {
            "name": pick("billing_name", (client.client_name if client else project.client_name) or "Client not recorded"),
            "address": pick("billing_address", client.address if client else None),
            "gstin": pick("billing_gstin", client.gst_number if client else None),
            "pan": pick("billing_pan", None),
            "email": pick("billing_email", (client.client_email if client else None)),
            "phone": pick("billing_phone", (client.contact_person_phone or client.primary_phone) if client else None),
        },
        "company": {
            "name": pick("company_name", company["name"]),
            "address": pick("company_address", company["address"]),
            "gstin": pick("company_gstin", company["gstin"]),
            "pan": pick("company_pan", company["pan"]),
            "phone": pick("company_phone", company["phone"]),
            "email": pick("company_email", company["email"]),
            "website": pick("company_website", None),
            "hsn_sac": pick("company_hsn_sac", None),
        },
        "bank": {
            "bank_name": pick("bank_name", company["bank_name"]),
            "account_name": pick("bank_account_name", company["bank_account_name"]),
            "account_number": pick("bank_account_number", company["bank_account_number"]),
            "ifsc": pick("bank_ifsc", company["bank_ifsc"]),
            "swift": pick("bank_swift", None),
            "branch": pick("bank_branch", company["bank_branch"]),
        },
    }


def invoice_auto_fill(db: Session, *, project_id: int) -> dict:
    """Auto Fill mode: pull everything the ERP already knows for this project.

    Pure read — creates nothing, changes nothing. Finance reviews every field in the
    common invoice editor before clicking Create Invoice Draft; nothing here raises an
    invoice or writes to the database. Client/company/bank data always reuses this same
    helper the invoice itself will snapshot from (``_resolve_invoice_document_snapshot``),
    so what Finance sees here is exactly what the issued document will show.
    """
    project = _project(db, project_id)
    client = project.client
    snapshot = _resolve_invoice_document_snapshot(db, project=project, overrides=None)

    from app.modules.commercial.service import billing_recommendation

    try:
        recommendation = billing_recommendation(db, project_id=project_id)
    except Exception:  # noqa: BLE001 - a legacy/unlinked project must still auto-fill client/company data
        recommendation = None

    recommended = None
    rec = (recommendation or {}).get("recommendation") if recommendation else None
    basis = (recommendation or {}).get("commercial_basis") if recommendation else None
    if rec:
        recommended = {
            "currency": rec["currency_code"],
            "amount": rec["base_amount"],
            "tax_percent": rec["tax_percent"],
            "tax_amount": rec["tax_amount"],
            "payment_terms": (basis or {}).get("payment_terms"),
            "po_wo_reference": (basis or {}).get("po_wo_reference"),
            "links": {
                "estimate_revision_id": rec.get("estimate_revision_id"),
                "billing_basis_id": rec.get("billing_basis_id"),
                "billed_quantity": rec.get("quantity") if rec.get("method") == "UNIT_RATE" else None,
                "billed_milestone_id": rec.get("milestone_id") if rec.get("method") == "MILESTONE" else None,
            },
        }

    return {
        "client": {
            "name": (client.client_name if client else project.client_name) or "Client not recorded",
            "address": client.address if client else None,
            "gstin": client.gst_number if client else None,
            "email": (client.client_email if client else None),
            "phone": (client.contact_person_phone or client.primary_phone) if client else None,
        },
        "project": {
            "code": project.project_code,
            "name": project.project_name,
            "description": project.description,
        },
        "company": snapshot["company"],
        "bank": snapshot["bank"],
        "recommended": recommended,
    }


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
        entry_mode=payload.entry_mode,
        cgst_percent=payload.cgst_percent,
        cgst_amount=payload.cgst_amount,
        sgst_percent=payload.sgst_percent,
        sgst_amount=payload.sgst_amount,
        igst_percent=payload.igst_percent,
        igst_amount=payload.igst_amount,
        work_order_date=payload.work_order_date,
        dispatch_details=(payload.dispatch_details or "").strip() or None,
        dispatch_date=payload.dispatch_date,
        place_of_supply=(payload.place_of_supply or "").strip() or None,
    )
    invoice.document_snapshot = _resolve_invoice_document_snapshot(db, project=project, overrides=payload.billing_snapshot)
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
    for item in payload.line_items:
        db.add(ProjectInvoiceLineItem(
            invoice_id=invoice.id,
            sequence=item.sequence,
            description=item.description,
            hsn_sac=item.hsn_sac,
            unit=item.unit,
            quantity=item.quantity,
            rate=item.rate,
            amount=item.amount,
        ))
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
    invoice.status = PAYMENT_PENDING
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
        target_url=f"/management/project-360/{project.id}",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:invoice-raised:{invoice.id}",
    )
    return invoice


def _payment_total(db: Session, invoice_id: int) -> Decimal:
    """Amount already settled against an invoice, in the invoice's own currency.

    A client advance applied to this invoice settles it just as a normal payment
    does, so it is included here. The advance is never duplicated into
    ``project_invoice_payments``: the amount is read from the isolated
    ``client_advance_transactions`` ledger, so the invoice face value, the
    revenue recognition rule and the Employee Advance flow are all unchanged.
    """
    cash = Decimal(db.scalar(select(func.coalesce(func.sum(ProjectInvoicePayment.amount), 0)).where(
        ProjectInvoicePayment.invoice_id == invoice_id
    )) or 0)
    from app.modules.finance.advance_settlement_service import advance_applied_original_by_invoice

    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        return cash
    applied = advance_applied_original_by_invoice(db, {int(invoice.id): invoice}).get(int(invoice.id), Decimal("0"))
    return Decimal(cash) + Decimal(applied)


def _invoice_total_due(invoice: ProjectInvoice) -> Decimal:
    return Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0)


def compute_invoice_payment_status(*, invoice_total: Decimal, paid_total: Decimal) -> str:
    """Derive invoice payment status from recorded payments.

    remaining_balance = invoice_total - sum(all payments)
    - remaining_balance <= 0 -> INVOICE_CLOSED
    - paid_total > 0 and remaining_balance > 0 -> PARTIALLY_PAID
    - paid_total == 0 -> PAYMENT_PENDING
    """
    remaining_balance = invoice_total - paid_total
    if remaining_balance <= 0:
        return INVOICE_CLOSED
    if paid_total > 0:
        return PARTIALLY_PAID
    return PAYMENT_PENDING


def _maybe_finance_closure_pending(
    db: Session, *, actor: User, workflow: ProjectWorkflow, exclude_invoice_id: int
) -> None:
    other_invoices = list(db.scalars(select(ProjectInvoice).where(
        ProjectInvoice.project_id == workflow.project_id,
        ProjectInvoice.id != exclude_invoice_id,
    )).all())
    open_invoices = [row for row in other_invoices if not (
        row.status == INVOICE_CLOSED
        or _approved_bad_debt_remaining(db, row.id) >= _invoice_cash_balance(db, row)
    )]
    if not open_invoices:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=FINANCE_CLOSURE_PENDING,
            event_type="finance_closure_pending",
            title="Finance Closure Pending",
            comments="All invoices are fully settled or covered by Management-approved Bad Debt.",
        )


def record_invoice_payment(
    db: Session,
    *,
    actor: User,
    invoice_id: int,
    payload: InvoicePaymentCreate,
    _allow_bad_debt_recovery: bool = False,
) -> ProjectInvoicePayment:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    if invoice.status not in {INVOICE_RAISED, PAYMENT_PENDING, PARTIALLY_PAID, PAYMENT_OVERDUE}:
        raise ValueError("Payments can only be recorded against an open raised invoice")
    total_due = _invoice_total_due(invoice)
    paid_before = _payment_total(db, invoice.id)

    # Keep ordinary collection and Bad Debt recovery as two explicit paths.
    # When Management has approved a write-off, Finance may still collect any
    # amount that remains genuinely collectible outside that write-off. Money
    # received against the written-off portion must go through
    # ``record_bad_debt_recovery`` so the original write-off history and
    # recovered_amount remain accurate.
    if not _allow_bad_debt_recovery:
        approved_bad_debt = _approved_bad_debt_remaining(db, invoice.id)
        if approved_bad_debt > 0:
            collectible_before = max(total_due - paid_before - approved_bad_debt, Decimal("0"))
            if payload.amount > collectible_before:
                if collectible_before <= 0:
                    raise ValueError(
                        "This invoice balance is covered by Management-approved Bad Debt; "
                        "use Bad Debt Recovery to record money received against the write-off"
                    )
                raise ValueError(
                    "Payment exceeds the collectible balance while Management-approved Bad Debt exists; "
                    "use Bad Debt Recovery for the written-off portion"
                )

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
    new_status = compute_invoice_payment_status(invoice_total=total_due, paid_total=paid_after)
    if paid_after > total_due or (paid_after < total_due and new_status == INVOICE_CLOSED) or (
        paid_after == 0 and new_status != PAYMENT_PENDING
    ):
        raise ValueError("Inconsistent invoice payment status calculation")
    invoice.status = new_status
    complete = new_status == INVOICE_CLOSED
    if complete:
        invoice.closed_by_id = actor.id
        invoice.closed_at = utc_now()
    workflow = _workflow(db, invoice.project_id)
    _transition(
        db,
        workflow=workflow,
        actor=actor,
        status=new_status,
        event_type="invoice_payment_received" if complete else "invoice_partial_payment",
        title="Payment Received" if complete else "Partial Payment",
        comments=f"{invoice.currency} {payload.amount} ({payload.payment_reference})",
    )
    if complete:
        _maybe_finance_closure_pending(db, actor=actor, workflow=workflow, exclude_invoice_id=invoice.id)
    project = _project(db, invoice.project_id)
    _notify(
        db,
        project=project,
        event_type="lifecycle.payment_received" if complete else "lifecycle.partial_payment",
        title=("Payment received" if complete else "Partial payment") + f": {project.project_code}",
        message=f"{invoice.currency} {payload.amount} recorded for invoice {invoice.invoice_number}.",
        target_url=f"/management/project-360/{project.id}",
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
        target_url=f"/finance/billing?project={project.id}&invoice={invoice.id}",
        recipient_roles=["finance", "management"],
        dedupe_key=f"lifecycle:invoice-overdue:{invoice.id}",
    )
    return invoice


BAD_DEBT_PROPOSED = "PROPOSED"
BAD_DEBT_APPROVED = "APPROVED"
BAD_DEBT_REJECTED = "REJECTED"
BAD_DEBT_RECOVERED = "RECOVERED"

# ---------------------------------------------------------------------------
# DUAL management approval for Bad Debt (Vinod Sir AND Chethan).
#
# The two approvers are NOT hard-coded numeric employee ids: they are the two
# authorized MANAGEMENT accounts already defined by the platform
# (``app.core.management_access.MANAGEMENT_ACCOUNTS`` / ``MANAGEMENT_EMAILS``).
# Only the email is used as the identity key, and the configuration is validated
# loudly — if those addresses are not authorized management accounts the feature
# refuses to guess.
# ---------------------------------------------------------------------------
BAD_DEBT_APPROVER_EMAILS: dict[str, str] = {
    "vinod": "vinod@nakshatech.com",
    "chethan": "chethan@nakshatech.com",
}
BAD_DEBT_APPROVER_LABELS: dict[str, str] = {
    "vinod": "Vinod Sir",
    "chethan": "Chethan",
}


def _assert_bad_debt_approver_configuration() -> None:
    missing = [addr for addr in BAD_DEBT_APPROVER_EMAILS.values() if addr not in MANAGEMENT_EMAILS]
    if missing:
        raise RuntimeError(
            "Bad Debt approver configuration is ambiguous — these addresses are not authorized "
            "management accounts: " + ", ".join(missing)
        )


def bad_debt_approver_key(actor: User) -> str:
    """Resolve the authenticated user to 'vinod' / 'chethan', else refuse."""
    _assert_bad_debt_approver_configuration()
    email = (actor.email or "").strip().lower()
    for key, address in BAD_DEBT_APPROVER_EMAILS.items():
        if email == address:
            return key
    raise PermissionError(
        "Only the authorized management approvers (Vinod Sir / Chethan) can decide a Bad Debt proposal"
    )


def _current_bad_debt_approvals(db: Session, row: ProjectInvoiceBadDebt) -> dict[str, ProjectInvoiceBadDebtApproval]:
    """Latest decision per approver within the CURRENT proposal cycle (append-only)."""
    rows = list(db.scalars(select(ProjectInvoiceBadDebtApproval).where(
        ProjectInvoiceBadDebtApproval.bad_debt_id == row.id,
        ProjectInvoiceBadDebtApproval.decided_at >= row.proposed_at,
    ).order_by(ProjectInvoiceBadDebtApproval.decided_at.asc(), ProjectInvoiceBadDebtApproval.id.asc())).all())
    latest: dict[str, ProjectInvoiceBadDebtApproval] = {}
    for approval in rows:
        latest[approval.approver_key] = approval
    return latest


def _bad_debt_approval_payload(db: Session, row: ProjectInvoiceBadDebt | None) -> dict:
    """Dual-approval status for UI/reporting (never mixes pending with approved)."""
    if row is None:
        return {"required_approvers": [], "decisions": [], "approved_count": 0, "required_count": len(BAD_DEBT_APPROVER_EMAILS)}
    decisions = _current_bad_debt_approvals(db, row)
    return {
        "required_approvers": [
            {"key": key, "label": BAD_DEBT_APPROVER_LABELS[key]} for key in BAD_DEBT_APPROVER_EMAILS
        ],
        "decisions": [
            {
                "approver_key": key,
                "approver_label": BAD_DEBT_APPROVER_LABELS.get(key, key),
                "approver_name": _user_display_name(db, approval.approver_user_id),
                "decision": approval.decision,
                "comment": approval.comment,
                "decided_at": approval.decided_at.isoformat() if approval.decided_at else None,
            }
            for key, approval in decisions.items()
        ],
        "approved_count": sum(1 for a in decisions.values() if a.decision == "approved"),
        "required_count": len(BAD_DEBT_APPROVER_EMAILS),
    }


def _bad_debt_row(db: Session, invoice_id: int) -> ProjectInvoiceBadDebt | None:
    return db.scalar(select(ProjectInvoiceBadDebt).where(ProjectInvoiceBadDebt.invoice_id == invoice_id))


def _user_display_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.full_name if user is not None else None


def _invoice_cash_balance(db: Session, invoice: ProjectInvoice) -> Decimal:
    return max(_invoice_total_due(invoice) - _payment_total(db, invoice.id), Decimal("0"))


def _approved_bad_debt_remaining(db: Session, invoice_id: int) -> Decimal:
    row = _bad_debt_row(db, invoice_id)
    if row is None or row.status != BAD_DEBT_APPROVED:
        return Decimal("0")
    return max(Decimal(row.approved_amount or 0) - Decimal(row.recovered_amount or 0), Decimal("0"))


def propose_bad_debt(
    db: Session, *, actor: User, invoice_id: int, payload: BadDebtProposalCreate
) -> ProjectInvoiceBadDebt:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    if invoice.due_date >= date.today():
        raise ValueError("Bad Debt can only be proposed after the invoice due date")
    balance = _invoice_cash_balance(db, invoice)
    if balance <= 0:
        raise ValueError("This invoice has no unpaid balance")
    if invoice.status != PAYMENT_OVERDUE:
        raise ValueError("Mark the invoice Payment Overdue before proposing Bad Debt")
    row = _bad_debt_row(db, invoice_id)
    if row is not None and row.status == BAD_DEBT_APPROVED:
        raise ValueError("Bad Debt is already approved for this invoice")
    if row is not None and row.status == BAD_DEBT_PROPOSED:
        raise ValueError("A Bad Debt proposal is already pending Management review")
    # Finance may write off the full collectible balance (default) or a smaller
    # amount. The proposal can never exceed what is still collectible.
    proposed_amount = payload.proposed_amount if payload.proposed_amount is not None else balance
    if proposed_amount <= 0:
        raise ValueError("Bad Debt amount must be greater than zero")
    if proposed_amount > balance:
        raise ValueError("Bad Debt amount cannot exceed the outstanding collectible balance")
    if row is None:
        row = ProjectInvoiceBadDebt(
            project_id=invoice.project_id,
            invoice_id=invoice.id,
            status=BAD_DEBT_PROPOSED,
            proposed_amount=proposed_amount,
            approved_amount=None,
            recovered_amount=Decimal("0"),
            currency=invoice.currency,
            reason=payload.reason.strip(),
            collection_attempts=payload.collection_attempts.strip(),
            last_followup_date=payload.last_followup_date,
            finance_remarks=(payload.finance_remarks or "").strip() or None,
            proposed_by_id=actor.id,
        )
        db.add(row)
    else:
        row.status = BAD_DEBT_PROPOSED
        row.proposed_amount = proposed_amount
        row.approved_amount = None
        row.recovered_amount = Decimal("0")
        row.reason = payload.reason.strip()
        row.collection_attempts = payload.collection_attempts.strip()
        row.last_followup_date = payload.last_followup_date
        row.finance_remarks = (payload.finance_remarks or "").strip() or None
        row.proposed_by_id = actor.id
        row.proposed_at = utc_now()
        row.reviewed_by_id = None
        row.reviewed_at = None
        row.decision_reason = None
    db.flush()
    project = _project(db, invoice.project_id)
    add_timeline_event(
        db,
        project_id=invoice.project_id,
        event_type="bad_debt_proposed",
        title=f"Bad Debt Proposed · {invoice.invoice_number}",
        status=PAYMENT_OVERDUE,
        actor_user_id=actor.id,
        details=f"{invoice.currency} {row.proposed_amount} proposed for Management review. {row.reason}",
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.bad_debt.proposed",
        title=f"Bad Debt approval required: {project.project_code}",
        message=f"Finance proposed {invoice.currency} {row.proposed_amount} Bad Debt for invoice {invoice.invoice_number}.",
        target_url=f"/management/project-360/{project.id}?tab=actions&invoice={invoice.id}",
        recipient_roles=["management"],
        dedupe_key=f"lifecycle:bad-debt:proposal:{invoice.id}:{int(row.proposed_at.timestamp())}",
    )
    return row


def decide_bad_debt(
    db: Session, *, actor: User, invoice_id: int, payload: BadDebtDecision
) -> ProjectInvoiceBadDebt:
    """Record ONE authorized management decision on a pending Bad Debt proposal.

    DUAL APPROVAL: the write-off becomes effective only when BOTH management
    approvers (Vinod Sir AND Chethan) approve. A single approval leaves the case
    pending (no financial effect). Either approver rejecting rejects the case.
    Repeated or concurrent calls are idempotent — one decision per approver per
    proposal cycle, so the financial effect is applied exactly once.
    """
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    approver_key = bad_debt_approver_key(actor)
    # Serialize concurrent decisions for this invoice (double-click / two approvers).
    row = db.scalar(select(ProjectInvoiceBadDebt).where(
        ProjectInvoiceBadDebt.invoice_id == invoice_id).with_for_update())
    if row is None:
        raise ValueError("A pending Bad Debt proposal is required")
    decisions = _current_bad_debt_approvals(db, row)
    if approver_key in decisions:
        # Idempotent replay: this approver already decided in the current cycle (even if
        # the case has since been finalized) — return the authoritative state untouched.
        return row
    if row.status not in {BAD_DEBT_PROPOSED}:
        raise ValueError("A pending Bad Debt proposal is required")
    if payload.decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected")
    if payload.decision == "rejected" and not (payload.comments or "").strip():
        raise ValueError("A rejection reason is required")

    if payload.decision == "approved":
        balance = _invoice_cash_balance(db, invoice)
        if Decimal(row.proposed_amount or 0) > balance:
            # Never trust the proposal snapshot — the client may have paid while the
            # proposal was pending. Refuse (no silent shrink, no negative balance).
            raise ValueError(
                "The collectible balance changed after this proposal "
                f"({invoice.currency} {balance} remaining) — amend or resubmit the Bad Debt proposal"
            )

    db.add(ProjectInvoiceBadDebtApproval(
        bad_debt_id=row.id,
        invoice_id=invoice.id,
        project_id=invoice.project_id,
        approver_key=approver_key,
        approver_user_id=actor.id,
        approver_email=(actor.email or "").strip().lower(),
        decision=payload.decision,
        comment=(payload.comments or "").strip() or None,
    ))
    db.flush()
    decisions = _current_bad_debt_approvals(db, row)

    if any(a.decision == "rejected" for a in decisions.values()):
        row.status = BAD_DEBT_REJECTED
        row.approved_amount = None
    elif len(decisions) == len(BAD_DEBT_APPROVER_EMAILS) and all(
        a.decision == "approved" for a in decisions.values()
    ):
        # BOTH approvals present -> the write-off becomes effective exactly once.
        row.status = BAD_DEBT_APPROVED
        row.approved_amount = Decimal(row.proposed_amount or 0)
    # else: still PROPOSED (awaiting the remaining approval) — no financial effect.

    row.reviewed_by_id = actor.id
    row.reviewed_at = utc_now()
    row.decision_reason = (payload.comments or "").strip() or row.decision_reason
    db.flush()

    project = _project(db, invoice.project_id)
    approver_label = BAD_DEBT_APPROVER_LABELS.get(approver_key, approver_key)
    final = row.status in {BAD_DEBT_APPROVED, BAD_DEBT_REJECTED}
    add_timeline_event(
        db,
        project_id=invoice.project_id,
        event_type=(
            "bad_debt_approved" if row.status == BAD_DEBT_APPROVED
            else "bad_debt_rejected" if row.status == BAD_DEBT_REJECTED
            else "bad_debt_decision_recorded"
        ),
        title=(
            f"Bad Debt {'Approved' if row.status == BAD_DEBT_APPROVED else 'Rejected'}" if final
            else f"Bad Debt approval {approver_label} recorded"
        ) + f" · {invoice.invoice_number}",
        status=PAYMENT_OVERDUE,
        actor_user_id=actor.id,
        details=row.decision_reason,
    )
    if final:
        _notify(
            db,
            project=project,
            event_type="lifecycle.bad_debt.approved" if row.status == BAD_DEBT_APPROVED else "lifecycle.bad_debt.rejected",
            title=("Bad Debt approved" if row.status == BAD_DEBT_APPROVED else "Bad Debt rejected") + f": {project.project_code}",
            message=f"Invoice {invoice.invoice_number}: {row.decision_reason}",
            target_url=f"/finance/billing?project={project.id}&invoice={invoice.id}",
            recipient_roles=["finance"],
            dedupe_key=f"lifecycle:bad-debt:final:{invoice.id}:{row.status}",
        )
    else:
        # Still pending: tell management the remaining approval is awaited, and tell
        # Finance that a decision was recorded. Dedupe key includes the approval so
        # repeated calls never spam.
        _notify(
            db,
            project=project,
            event_type="lifecycle.bad_debt.partially_approved",
            title=f"Bad Debt awaiting final approval: {project.project_code}",
            message=(
                f"{approver_label} recorded a decision on invoice {invoice.invoice_number}. "
                f"{len(decisions)} of {len(BAD_DEBT_APPROVER_EMAILS)} required approvals recorded."
            ),
            target_url=f"/management/project-360/{project.id}?tab=actions&invoice={invoice.id}",
            recipient_roles=["management"],
            dedupe_key=f"lifecycle:bad-debt:partial:{invoice.id}:{approver_key}",
        )
        _notify(
            db,
            project=project,
            event_type="lifecycle.bad_debt.partially_approved",
            title=f"Bad Debt decision recorded: {project.project_code}",
            message=(
                f"{approver_label} recorded a decision on invoice {invoice.invoice_number}. "
                f"{len(decisions)} of {len(BAD_DEBT_APPROVER_EMAILS)} required approvals recorded."
            ),
            target_url=f"/finance/billing?project={project.id}&invoice={invoice.id}",
            recipient_roles=["finance"],
            dedupe_key=f"lifecycle:bad-debt:partial:{invoice.id}:{approver_key}",
        )
    if (
        row.status == BAD_DEBT_APPROVED
        and _approved_bad_debt_remaining(db, invoice.id) >= _invoice_cash_balance(db, invoice)
    ):
        # A partial write-off must never make the project look closure-ready
        # while a normal collectible balance still remains.
        _maybe_finance_closure_pending(
            db,
            actor=actor,
            workflow=_workflow(db, invoice.project_id),
            exclude_invoice_id=invoice.id,
        )
    return row


def record_bad_debt_recovery(
    db: Session, *, actor: User, invoice_id: int, payload: BadDebtRecoveryCreate
) -> ProjectInvoiceBadDebt:
    """Record real cash recovered against an approved Bad Debt write-off.

    The money is booked through the normal invoice payment architecture (no
    fake payment rows, no separate settlement), while the original Bad Debt
    record and its history are preserved. The write-off only shrinks to the
    extent the client actually pays back.
    """
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    row = _bad_debt_row(db, invoice_id)
    if row is None or row.status not in {BAD_DEBT_APPROVED, BAD_DEBT_RECOVERED}:
        raise ValueError("An approved Bad Debt write-off is required before recording a recovery")
    approved = Decimal(row.approved_amount or 0)
    recovered_before = Decimal(row.recovered_amount or 0)
    unrecovered = max(approved - recovered_before, Decimal("0"))
    if unrecovered <= 0:
        raise ValueError("This Bad Debt is already fully recovered")
    amount = payload.amount
    if amount <= 0:
        raise ValueError("Recovery amount must be greater than zero")
    if amount > unrecovered:
        raise ValueError("Recovery amount cannot exceed the unrecovered Bad Debt balance")

    # Real money: reuse the existing invoice payment path so Cash Received,
    # Outstanding and FX handling stay correct. Never a synthetic settlement.
    record_invoice_payment(
        db,
        actor=actor,
        invoice_id=invoice_id,
        payload=InvoicePaymentCreate(
            payment_reference=payload.payment_reference.strip(),
            payment_date=payload.payment_date,
            amount=amount,
            payment_mode=payload.payment_mode.strip().lower(),
            comments=f"Bad Debt recovery. {payload.remarks}".strip(),
        ),
        _allow_bad_debt_recovery=True,
    )

    recovered_after = recovered_before + amount
    row.recovered_amount = recovered_after
    row.status = BAD_DEBT_RECOVERED if recovered_after >= approved else BAD_DEBT_APPROVED
    db.flush()

    # ``record_invoice_payment`` necessarily moved the workflow back through a
    # payment status. If the still-unpaid cash balance remains fully covered by
    # the still-approved write-off, restore Finance Closure Pending eligibility.
    # This keeps a partial recovery from accidentally making an already-approved
    # write-off project appear open again.
    if (
        row.status == BAD_DEBT_APPROVED
        and _approved_bad_debt_remaining(db, invoice.id) >= _invoice_cash_balance(db, invoice)
    ):
        _maybe_finance_closure_pending(
            db,
            actor=actor,
            workflow=_workflow(db, invoice.project_id),
            exclude_invoice_id=invoice.id,
        )

    project = _project(db, invoice.project_id)
    unrecovered_after = max(approved - recovered_after, Decimal("0"))
    add_timeline_event(
        db,
        project_id=invoice.project_id,
        event_type="bad_debt_recovered",
        title=f"Bad Debt Recovery · {invoice.invoice_number}",
        status=PAYMENT_OVERDUE if unrecovered_after > 0 else PAYMENT_RECEIVED,
        actor_user_id=actor.id,
        details=(
            f"{invoice.currency} {amount} recovered. Written off {invoice.currency} {approved}, "
            f"recovered {invoice.currency} {recovered_after}, remaining unrecovered {invoice.currency} {unrecovered_after}."
        ),
    )
    _notify(
        db,
        project=project,
        event_type="lifecycle.bad_debt.recovered",
        title=f"Bad Debt recovery recorded: {project.project_code}",
        message=(
            f"Invoice {invoice.invoice_number}: {invoice.currency} {amount} recovered. "
            f"Remaining unrecovered {invoice.currency} {unrecovered_after}."
        ),
        target_url=f"/finance/billing?project={project.id}&invoice={invoice.id}",
        recipient_roles=["finance", "management"],
        dedupe_key=f"lifecycle:bad-debt:recovery:{invoice.id}:{int((row.updated_at or utc_now()).timestamp())}",
    )
    return row


def _client_name(project: FinanceProject) -> str:
    client = project.client
    return ((client.client_name if client is not None else project.client_name) or "Client not recorded").strip()


def list_bad_debts(db: Session) -> list[dict]:
    rows = list(db.scalars(select(ProjectInvoiceBadDebt).order_by(ProjectInvoiceBadDebt.updated_at.desc(), ProjectInvoiceBadDebt.id.desc())).all())
    invoice_ids = [row.invoice_id for row in rows]
    invoices = {row.id: row for row in db.scalars(select(ProjectInvoice).where(ProjectInvoice.id.in_(invoice_ids))).all()} if invoice_ids else {}
    projects = {row.id: row for row in db.scalars(_project_query().where(FinanceProject.id.in_({r.project_id for r in rows}))).unique().all()} if rows else {}
    result = []
    for row in rows:
        invoice = invoices.get(row.invoice_id)
        project = projects.get(row.project_id)
        if invoice is None or project is None:
            continue
        cash_balance = _invoice_cash_balance(db, invoice)
        approved_remaining = _approved_bad_debt_remaining(db, invoice.id)
        result.append({
            "id": row.id,
            "project_id": row.project_id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "client_name": _client_name(project),
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "invoice_total": float(_invoice_total_due(invoice)),
            "paid_amount": float(_payment_total(db, invoice.id)),
            "cash_balance": float(cash_balance),
            "status": row.status,
            "proposed_amount": float(row.proposed_amount),
            "approved_amount": float(row.approved_amount) if row.approved_amount is not None else None,
            "recovered_amount": float(row.recovered_amount or 0),
            "net_bad_debt": float(approved_remaining),
            "unrecovered_amount": float(
                max(Decimal(row.approved_amount or 0) - Decimal(row.recovered_amount or 0), Decimal("0"))
            ) if row.approved_amount is not None else 0.0,
            "currency": row.currency,
            "reason": row.reason,
            "collection_attempts": row.collection_attempts,
            "last_followup_date": row.last_followup_date.isoformat() if row.last_followup_date else None,
            "finance_remarks": row.finance_remarks,
            "proposed_at": row.proposed_at.isoformat(),
            "proposed_by_name": _user_display_name(db, row.proposed_by_id),
            "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
            "reviewed_by_name": _user_display_name(db, row.reviewed_by_id),
            "decision_reason": row.decision_reason,
            "approvals": _bad_debt_approval_payload(db, row),
            "final_approved_at": (
                row.reviewed_at.isoformat()
                if row.status == BAD_DEBT_APPROVED and row.reviewed_at else None
            ),
        })
    return result


def close_invoice(
    db: Session, *, actor: User, invoice_id: int, payload: InvoiceClose
) -> ProjectInvoice:
    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None:
        raise ValueError("Invoice not found")
    total_due = _invoice_total_due(invoice)
    paid = _payment_total(db, invoice.id)
    if paid < total_due:
        raise ValueError("Full payment is required before invoice closure")
    if invoice.status == INVOICE_CLOSED:
        if invoice.closed_at is None:
            invoice.closed_at = utc_now()
            invoice.closed_by_id = actor.id
        return invoice
    if paid > total_due:
        raise ValueError("Inconsistent invoice payment status calculation")
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
    _maybe_finance_closure_pending(db, actor=actor, workflow=workflow, exclude_invoice_id=invoice.id)
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
        paid = _payment_total(db, invoice.id)
        total_due = _invoice_total_due(invoice)
        cash_balance = max(total_due - paid, Decimal("0"))
        approved_bad_debt = _approved_bad_debt_remaining(db, invoice.id)
        if cash_balance <= 0:
            if invoice.status != INVOICE_CLOSED:
                raise ValueError(f"Invoice {invoice.invoice_number} must be closed after full settlement")
            continue
        if approved_bad_debt < cash_balance:
            raise ValueError(
                f"Invoice {invoice.invoice_number} has an outstanding balance not covered by Management-approved Bad Debt"
            )

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
    if row.status != INVOICE_DRAFT:
        derived = compute_invoice_payment_status(invoice_total=due, paid_total=paid)
        remaining = due - paid
        if derived == INVOICE_CLOSED:
            effective_status = INVOICE_CLOSED
        elif (
            remaining > 0
            and row.due_date < date.today()
            and row.status not in {INVOICE_CLOSED, PAYMENT_RECEIVED}
        ):
            # Overdue is authoritative for the detail Finance actually sees:
            # due date passed + open balance + not settled. This must hold for
            # every stored status (INVOICE_RAISED / PAYMENT_PENDING /
            # PARTIALLY_PAID / PAYMENT_OVERDUE) - a persisted PAYMENT_OVERDUE
            # must never fall back to the payment-derived PAYMENT_PENDING.
            effective_status = PAYMENT_OVERDUE
        elif paid > 0:
            effective_status = PARTIALLY_PAID
        else:
            effective_status = derived
    payments = list(db.scalars(select(ProjectInvoicePayment).where(
        ProjectInvoicePayment.invoice_id == row.id
    ).order_by(ProjectInvoicePayment.payment_date.asc(), ProjectInvoicePayment.id.asc())).all())
    bad_debt = _bad_debt_row(db, row.id)
    approved_bad_debt = _approved_bad_debt_remaining(db, row.id)
    cash_balance = max(Decimal("0"), due - paid)
    collectible_balance = max(Decimal("0"), cash_balance - approved_bad_debt)
    bad_debt_payload = None if bad_debt is None else {
        "id": bad_debt.id,
        "status": bad_debt.status,
        "proposed_amount": float(bad_debt.proposed_amount),
        "approved_amount": float(bad_debt.approved_amount) if bad_debt.approved_amount is not None else None,
        "recovered_amount": float(bad_debt.recovered_amount or 0),
        "net_bad_debt": float(approved_bad_debt),
        "reason": bad_debt.reason,
        "collection_attempts": bad_debt.collection_attempts,
        "last_followup_date": bad_debt.last_followup_date.isoformat() if bad_debt.last_followup_date else None,
        "finance_remarks": bad_debt.finance_remarks,
        "proposed_at": bad_debt.proposed_at.isoformat(),
        "proposed_by_name": _user_display_name(db, bad_debt.proposed_by_id),
        "reviewed_at": bad_debt.reviewed_at.isoformat() if bad_debt.reviewed_at else None,
        "reviewed_by_name": _user_display_name(db, bad_debt.reviewed_by_id),
        "decision_reason": bad_debt.decision_reason,
        # Dual-approval progress (Vinod Sir AND Chethan) for the Billing/Management UI.
        "approvals": _bad_debt_approval_payload(db, bad_debt),
    }
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
        "balance": float(cash_balance),
        "collectible_balance": float(collectible_balance),
        "days_overdue": max((date.today() - row.due_date).days, 0) if cash_balance > 0 and row.due_date < date.today() else 0,
        "bad_debt": bad_debt_payload,
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
        "invoice_balance": sum(item["collectible_balance"] for item in (_invoice_payload(db, invoice) for invoice in invoices)),
        "has_overdue_invoice": any(
            payload["status"] == PAYMENT_OVERDUE and payload["collectible_balance"] > 0
            for payload in (_invoice_payload(db, invoice) for invoice in invoices)
        ),
    }


def lifecycle_dashboard(db: Session, *, actor: User, role: str) -> dict:
    query = _project_query().join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
    query = exclude_hidden_projects(db, query)
    if role == "bd":
        query = query.where(ProjectWorkflow.bd_owner_user_id == actor.id)
    elif is_technical_pm_role(role):
        query = query.join(FinanceProjectMasterProfile).where(FinanceProjectMasterProfile.project_manager_id == actor.id)
    projects = list(db.scalars(query.order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())).unique().all())
    workflows = {row.project_id: row for row in db.scalars(select(ProjectWorkflow).where(
        ProjectWorkflow.project_id.in_([project.id for project in projects])
    )).all()} if projects else {}
    rows = [_project_summary(db, project, workflows[project.id]) for project in projects if project.id in workflows]
    if is_technical_pm_role(role):
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
                "clients": int(db.scalar(exclude_hidden_clients(db, select(func.count(FinanceClient.id)))) or 0),
                "projects": len(rows),
                "pending_finance_approvals": statuses.count("pending_finance_approval"),
                "returned_projects": statuses.count("finance_returned"),
                "pm_unassigned": sum(row["project_manager_id"] is None for row in rows),
            },
            "finance": {
                "project_approvals": statuses.count("pending_finance_approval"),
                "clients": int(db.scalar(exclude_hidden_clients(db, select(func.count(FinanceClient.id)))) or 0),
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
    if is_technical_pm_role(role) and (not project.master_profile or project.master_profile.project_manager_id != actor.id):
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
                "source": row.source or "client_portal",
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
    if is_technical_pm_role(role):
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
