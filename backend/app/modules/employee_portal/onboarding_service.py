"""New Joiner onboarding workflow: HR draft -> IT official email -> Management final approval.

Statuses (plain strings, imperative transitions, following project workflow conventions):
    hr_draft -> hr_submitted -> management_pending -> final_approved
                 (IT approve)      (Chetana OR Vinod)

IT approval records ``it_approved_at``/``it_approved_by_user_id`` and moves the request
to ``management_pending`` — the IT-approved and management-pending concepts are one
state because IT approval is what routes the request to the Management queue.

Final approval is OR-based: exactly one of the two authorized management accounts
(``MANAGEMENT_EMAILS``) is required. A second approval is an idempotent no-op.
Final approval creates the Employee Master row that makes the new joiner eligible for
the normal Create CRM Account self-registration flow, and emails the new joiner's
PERSONAL email with the official email address — never a password.
"""

from __future__ import annotations

from datetime import date
import logging

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.management_access import MANAGEMENT_EMAILS, normalize_privileged_email
from app.models.entities import User, utc_now
from app.modules.employee_portal.employee_master import (
    ACTIVE_EMPLOYMENT,
    NOT_REGISTERED,
    department_label,
    normalize_email,
    normalize_identifier,
    normalize_phone,
)
from app.modules.employee_portal.models import EmployeeMaster, EmployeeOnboardingRequest
from app.modules.employee_portal.service import ensure_allowed_email, record_audit, send_email
from app.modules.notifications.service import create_global_notification

logger = logging.getLogger(__name__)

HR_DRAFT = "hr_draft"
HR_SUBMITTED = "hr_submitted"
MANAGEMENT_PENDING = "management_pending"
FINAL_APPROVED = "final_approved"
REJECTED = "rejected"

IT_QUEUE_STATUSES = {HR_SUBMITTED}
MANAGEMENT_QUEUE_STATUSES = {MANAGEMENT_PENDING}
STAFF_VISUAL_STATUSES = IT_QUEUE_STATUSES | MANAGEMENT_QUEUE_STATUSES | {FINAL_APPROVED, REJECTED}


def _notify(db: Session, *, event_type: str, title: str, message: str, recipient_user_ids=None, recipient_roles=None, dedupe_key: str) -> None:
    try:
        create_global_notification(
            db,
            event_type=event_type,
            title=title,
            message=message,
            category="approval",
            target_url="/onboarding",
            recipient_user_ids=recipient_user_ids,
            recipient_roles=recipient_roles,
            dedupe_key=dedupe_key,
        )
    except Exception:
        logger.exception("onboarding notification failed for %s", dedupe_key)


def _safe_email(*, recipient: str, subject: str, body: str) -> None:
    try:
        send_email(recipient=recipient, subject=subject, body=body)
    except Exception:
        logger.exception("onboarding email failed to %s", recipient)


def visible_request_ids(db: Session, user: User, role: str) -> set[int] | None:
    """None means "no scoping" (see all); otherwise the allowed request ids."""
    role = (role or "").strip().lower()
    if role in {"admin", "software_team"}:
        return None
    if role == "hr":
        return set(db.scalars(select(EmployeeOnboardingRequest.id).where(EmployeeOnboardingRequest.created_by_user_id == user.id)).all())
    if role == "it":
        return set(db.scalars(select(EmployeeOnboardingRequest.id).where(EmployeeOnboardingRequest.status.in_(STAFF_VISUAL_STATUSES))).all())
    if role == "management":
        return set(db.scalars(select(EmployeeOnboardingRequest.id).where(EmployeeOnboardingRequest.status.in_(MANAGEMENT_QUEUE_STATUSES | {FINAL_APPROVED}))).all())
    return set()


def list_requests(db: Session, user: User, role: str) -> list[EmployeeOnboardingRequest]:
    allowed = visible_request_ids(db, user, role)
    query = select(EmployeeOnboardingRequest).order_by(EmployeeOnboardingRequest.created_at.desc())
    if allowed is not None:
        if not allowed:
            return []
        query = query.where(EmployeeOnboardingRequest.id.in_(allowed))
    return list(db.scalars(query).all())


def get_request(db: Session, user: User, role: str, request_id: int) -> EmployeeOnboardingRequest:
    request = db.get(EmployeeOnboardingRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    allowed = visible_request_ids(db, user, role)
    if allowed is not None and request.id not in allowed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    return request


def create_draft(db: Session, actor: User, *, employee_name: str, personal_email: str, phone: str, employee_number: str, access_card_no: str, department_code: str, designation: str, joining_date: date | None = None, notes: str | None = None) -> EmployeeOnboardingRequest:
    normalized_email = normalize_email(personal_email)
    request = EmployeeOnboardingRequest(
        employee_name=employee_name.strip(),
        personal_email=personal_email.strip(),
        personal_email_normalized=normalized_email,
        phone=phone.strip(),
        employee_number=str(employee_number).strip(),
        employee_number_normalized=normalize_identifier(employee_number),
        access_card_no=str(access_card_no).strip(),
        access_card_no_normalized=normalize_identifier(access_card_no),
        department_code=department_code.strip(),
        designation=designation.strip(),
        joining_date=joining_date,
        notes=(notes or "").strip() or None,
        status=HR_DRAFT,
        created_by_user_id=actor.id,
    )
    db.add(request)
    db.flush()
    return request


def submit_to_it(db: Session, actor: User, request_id: int) -> EmployeeOnboardingRequest:
    request = db.get(EmployeeOnboardingRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    if request.created_by_user_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the HR owner can submit this request")
    if request.status != HR_DRAFT:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only an HR draft can be submitted to IT")
    request.status = HR_SUBMITTED
    request.submitted_to_it_at = utc_now()
    db.flush()
    _notify(
        db,
        event_type="onboarding.it.pending",
        title="New Joiner awaiting IT setup",
        message=f"{request.employee_name} ({request.employee_number}) was submitted by HR. Create the official NakshaTech email and approve.",
        recipient_roles=["it"],
        dedupe_key=f"onboarding:{request.id}:it-pending",
    )
    return request


def it_approve(db: Session, actor: User, request_id: int, *, official_email: str) -> EmployeeOnboardingRequest:
    request = db.get(EmployeeOnboardingRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    if request.status != HR_SUBMITTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a submitted request can be approved by IT")
    official = ensure_allowed_email(official_email)
    existing = db.scalar(select(EmployeeMaster.id).where(EmployeeMaster.email_normalized == official))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This official email already exists in Employee Master")
    request.official_email = official
    request.official_email_normalized = normalize_email(official)
    request.status = MANAGEMENT_PENDING
    request.it_approved_by_user_id = actor.id
    request.it_approved_at = utc_now()
    db.flush()
    _notify(
        db,
        event_type="onboarding.management.pending",
        title="New Joiner awaiting Management approval",
        message=f"IT created the official email for {request.employee_name} ({request.employee_number}). Final approval required.",
        recipient_user_ids=[request.created_by_user_id],
        recipient_roles=["management"],
        dedupe_key=f"onboarding:{request.id}:management-pending",
    )
    return request


def management_approve(db: Session, actor: User, request_id: int) -> EmployeeOnboardingRequest:
    request = db.get(EmployeeOnboardingRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    if request.status == FINAL_APPROVED:
        # OR approval: the second management approver must not corrupt state.
        return request
    if request.status != MANAGEMENT_PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only a management-pending request can be finally approved")
    if normalize_privileged_email(actor.email) not in MANAGEMENT_EMAILS:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an authorized management approver can give final approval")
    request.status = FINAL_APPROVED
    request.decided_by = normalize_privileged_email(actor.email)
    request.management_approved_at = utc_now()
    db.flush()
    master = EmployeeMaster(
        source_sl_no=None,
        access_card_no=request.access_card_no,
        access_card_no_normalized=request.access_card_no_normalized,
        employee_number=request.employee_number,
        employee_number_normalized=request.employee_number_normalized,
        employee_name=request.employee_name,
        phone=request.phone,
        phone_normalized=normalize_phone(request.phone),
        department_raw=department_label(request.department_code),
        department_code=request.department_code,
        designation_raw=request.designation,
        email=request.official_email,
        email_normalized=request.official_email_normalized,
        employment_status=ACTIVE_EMPLOYMENT,
        crm_account_status=NOT_REGISTERED,
        source_batch_id=f"new-joiner-{request.id}",
        imported_at=utc_now(),
    )
    db.add(master)
    db.flush()
    request.employee_master_id = master.id
    _notify(
        db,
        event_type="onboarding.final_approved",
        title="New Joiner approved",
        message=f"{request.employee_name} ({request.employee_number}) is finally approved. Official email: {request.official_email}.",
        recipient_user_ids=[request.created_by_user_id],
        recipient_roles=["it"],
        dedupe_key=f"onboarding:{request.id}:final-approved",
    )
    _safe_email(
        recipient=request.personal_email,
        subject="NakshaTech onboarding approved - your official email",
        body=(
            f"Hello {request.employee_name},\n\n"
            "Your onboarding has been approved.\n\n"
            f"Your official NakshaTech email address is: {request.official_email}\n\n"
            "Open the NakshaTech CRM and choose \"Create CRM Account\" using this official email. "
            "You will create your own password and set up the Authenticator app during that flow.\n\n"
            "For security, your password is never sent by email.\n\n"
            "- NakshaTech HR / Software Team\n"
        ),
    )
    return request


def reject_request(db: Session, actor: User, request_id: int, *, reason: str) -> EmployeeOnboardingRequest:
    request = db.get(EmployeeOnboardingRequest, request_id)
    if request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Onboarding request not found")
    if request.status in {FINAL_APPROVED, REJECTED}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This request is already closed")
    request.status = REJECTED
    request.rejected_by_user_id = actor.id
    request.rejected_reason = (reason or "").strip() or None
    request.rejected_at = utc_now()
    db.flush()
    _notify(
        db,
        event_type="onboarding.rejected",
        title="New Joiner request rejected",
        message=f"{request.employee_name} ({request.employee_number}) was rejected. Reason: {request.rejected_reason or 'Not recorded'}.",
        recipient_user_ids=[request.created_by_user_id],
        dedupe_key=f"onboarding:{request.id}:rejected",
    )
    return request
