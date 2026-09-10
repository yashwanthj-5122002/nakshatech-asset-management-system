from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import json
import math
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceProject
from app.modules.finance.service import project_expense_allowed
from app.modules.travel_km.models import TravelKmAttachment, TravelKmClaim, TravelKmEmailDelivery, TravelKmEmailRouting, TravelKmEvent
from app.modules.travel_km.schemas import (
    TravelKmClaimCreateRequest,
    TravelKmDecisionRequest,
    TravelKmEndRequest,
    TravelKmEmailRoutingRequest,
    TravelKmFinanceDecisionRequest,
    TravelKmPaymentRequest,
    TravelKmReviseRequest,
)

EMPLOYEE_ROLE = "employee"
ADMIN_ROLE = "admin"
HR_ROLE = "hr"
FINANCE_ROLE = "finance"
MANAGEMENT_ROLE = "management"
SOFTWARE_TEAM_ROLE = "software_team"
STAFF_VISIBLE_ROLES = {ADMIN_ROLE, HR_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE}
RATE_PER_KM = Decimal("5.00")
EDITABLE_STATUSES = {"draft", "admin_sent_back", "hr_sent_back"}


def money(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def km3(value: Decimal | float | int | str | None) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))


def _claim_options():
    return (
        selectinload(TravelKmClaim.attachments),
        selectinload(TravelKmClaim.events),
        selectinload(TravelKmClaim.email_routing),
        selectinload(TravelKmClaim.email_deliveries),
        selectinload(TravelKmClaim.verification_snapshot),
    )


def _project_snapshot(project: FinanceProject) -> tuple[str, str, str | None]:
    client_name = getattr(getattr(project, "client", None), "client_name", None) or project.client_name
    return project.project_code, project.project_name, client_name


def _unique_emails(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        email = str(value or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        result.append(email)
    return result


def email_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(decoded, list):
        return []
    return _unique_emails(str(item) for item in decoded)


def set_email_routing(
    db: Session,
    *,
    claim: TravelKmClaim,
    requester: User,
    payload: TravelKmEmailRoutingRequest,
) -> TravelKmEmailRouting:
    if claim.requester_id != requester.id:
        raise PermissionError("Employees can update email recipients only on their own Travel/KM claims")
    if claim.status not in EDITABLE_STATUSES:
        raise ValueError("Email recipients are locked because this claim is already in the approval workflow")

    manager = str(payload.reporting_manager_email).strip().lower()
    to_emails = _unique_emails([manager, *[str(value) for value in payload.to_emails]])
    cc_emails = [email for email in _unique_emails(str(value) for value in payload.cc_emails) if email not in set(to_emails)]
    if not to_emails:
        raise ValueError("At least one TO email address is required")

    routing = claim.email_routing
    if routing is None:
        routing = TravelKmEmailRouting(
            claim_id=claim.id,
            reporting_manager_email=manager,
            to_emails_json=json.dumps(to_emails),
            cc_emails_json=json.dumps(cc_emails),
            created_by_id=requester.id,
        )
        db.add(routing)
        claim.email_routing = routing
    else:
        routing.reporting_manager_email = manager
        routing.to_emails_json = json.dumps(to_emails)
        routing.cc_emails_json = json.dumps(cc_emails)
        routing.updated_at = utc_now()
    db.flush()
    return routing


def create_claim(db: Session, *, requester: User, payload: TravelKmClaimCreateRequest) -> TravelKmClaim:
    project = db.get(FinanceProject, payload.project_id)
    if project is None:
        raise ValueError("Selected Project Number was not found")
    allowed, reason = project_expense_allowed(project, on_date=payload.travel_date)
    if not allowed:
        raise ValueError(reason or "The selected project is not active for travel claims")
    project_code, project_name, client_name = _project_snapshot(project)
    claim = TravelKmClaim(
        claim_code=f"PENDING-{requester.id}-{int(datetime.now().timestamp() * 1000)}",
        requester_id=requester.id,
        project_id=project.id,
        project_code_snapshot=project_code,
        project_name_snapshot=project_name,
        client_name_snapshot=client_name,
        travel_date=payload.travel_date,
        purpose_description=payload.purpose_description.strip(),
        start_km=money(payload.start_km),
        start_latitude=float(payload.start_latitude),
        start_longitude=float(payload.start_longitude),
        start_accuracy_m=float(payload.start_accuracy_m) if payload.start_accuracy_m is not None else None,
        start_captured_at=payload.start_captured_at.replace(tzinfo=None),
        rate_per_km=RATE_PER_KM,
        status="draft",
    )
    db.add(claim)
    db.flush()
    claim.claim_code = f"NT-KM-{payload.travel_date.year}-{claim.id:05d}"
    if payload.email_routing is not None:
        set_email_routing(db, claim=claim, requester=requester, payload=payload.email_routing)
    add_event(db, claim=claim, action="claim_created", actor=requester, from_status=None, to_status="draft", comments="Travel claim started and live start GPS captured.")
    if payload.email_routing is not None:
        add_event(db, claim=claim, action="email_routing_configured", actor=requester, from_status="draft", to_status="draft", comments="Reporting Manager, TO and CC email recipients were configured for submission notification.")
    db.commit(); db.refresh(claim)
    return claim


def finish_journey(db: Session, *, claim: TravelKmClaim, requester: User, payload: TravelKmEndRequest) -> TravelKmClaim:
    if claim.requester_id != requester.id:
        raise PermissionError("Employees can update only their own travel claims")
    if claim.status not in EDITABLE_STATUSES:
        raise ValueError("This claim is locked because it is already in approval workflow")
    end_km = money(payload.end_km)
    if end_km < money(claim.start_km):
        raise ValueError("End KM cannot be lower than Start KM")
    claim.end_km = end_km
    claim.end_latitude = float(payload.end_latitude)
    claim.end_longitude = float(payload.end_longitude)
    claim.end_accuracy_m = float(payload.end_accuracy_m) if payload.end_accuracy_m is not None else None
    claim.end_captured_at = payload.end_captured_at.replace(tzinfo=None)
    recalculate_claim(claim)
    add_event(db, claim=claim, action="journey_completed", actor=requester, from_status=claim.status, to_status=claim.status, comments="End odometer and live end GPS captured.")
    db.commit(); db.refresh(claim)
    return claim


def revise_claim(db: Session, *, claim: TravelKmClaim, requester: User, payload: TravelKmReviseRequest) -> TravelKmClaim:
    if claim.requester_id != requester.id:
        raise PermissionError("Employees can revise only their own travel claims")
    if claim.status not in EDITABLE_STATUSES:
        raise ValueError("This claim cannot be revised at the current workflow stage")
    if payload.purpose_description is not None:
        claim.purpose_description = payload.purpose_description.strip()
    if payload.travel_date is not None:
        project = db.get(FinanceProject, claim.project_id)
        allowed, reason = project_expense_allowed(project, on_date=payload.travel_date) if project else (False, "Project not found")
        if not allowed:
            raise ValueError(reason or "Project is not active on this travel date")
        claim.travel_date = payload.travel_date
    if payload.start_km is not None:
        claim.start_km = money(payload.start_km)
    if payload.end_km is not None:
        claim.end_km = money(payload.end_km)
    if claim.end_km is not None and money(claim.end_km) < money(claim.start_km):
        raise ValueError("End KM cannot be lower than Start KM")
    recalculate_claim(claim)
    add_event(db, claim=claim, action="employee_revised", actor=requester, from_status=claim.status, to_status=claim.status, comments="Employee revised travel claim data before resubmission.")
    db.commit(); db.refresh(claim)
    return claim


def recalculate_claim(claim: TravelKmClaim) -> None:
    if claim.end_km is None or claim.end_latitude is None or claim.end_longitude is None:
        claim.odometer_km = None
        claim.gps_straight_line_km = None
        claim.distance_variance_km = None
        claim.distance_variance_percent = None
        claim.calculated_allowance = None
        return
    odo = money(money(claim.end_km) - money(claim.start_km))
    gps = Decimal(str(haversine_km(claim.start_latitude, claim.start_longitude, claim.end_latitude, claim.end_longitude)))
    variance = abs(Decimal(str(odo)) - gps)
    claim.odometer_km = odo
    claim.gps_straight_line_km = km3(gps)
    claim.distance_variance_km = km3(variance)
    claim.distance_variance_percent = money((variance / odo * Decimal("100")) if odo > 0 else Decimal("0"))
    claim.rate_per_km = RATE_PER_KM
    claim.calculated_allowance = money(odo * RATE_PER_KM)


def add_event(db: Session, *, claim: TravelKmClaim, action: str, actor: User, from_status: str | None, to_status: str | None, comments: str | None = None, metadata: dict | None = None) -> TravelKmEvent:
    event = TravelKmEvent(
        claim_id=claim.id,
        action=action,
        actor_user_id=actor.id,
        actor_name=actor.full_name or actor.email,
        actor_email=actor.email,
        actor_role=actor.role,
        from_status=from_status,
        to_status=to_status,
        comments=(comments or "").strip() or None,
        event_metadata=json.dumps(metadata, ensure_ascii=False, sort_keys=True) if metadata else None,
    )
    db.add(event)
    db.flush()
    return event


def submit_claim(db: Session, *, claim: TravelKmClaim, requester: User) -> TravelKmClaim:
    if claim.requester_id != requester.id:
        raise PermissionError("Employees can submit only their own travel claims")
    if claim.status not in EDITABLE_STATUSES:
        raise ValueError("This claim is not editable or ready for submission")
    if claim.end_km is None or claim.end_latitude is None or claim.end_longitude is None or claim.end_captured_at is None:
        raise ValueError("Complete the End Journey KM and live GPS capture before submitting")
    phases = {item.phase for item in claim.attachments}
    if "start" not in phases or "end" not in phases:
        raise ValueError("Both Start and End geotagged odometer photos are required")
    if claim.email_routing is None or not email_list(claim.email_routing.to_emails_json):
        raise ValueError("Add Reporting Manager and TO/CC email recipients before submitting the Travel/KM claim")
    recalculate_claim(claim)
    # V5 Smart Journey Verification is advisory only. Freeze the evidence score
    # at submission/resubmission without changing workflow eligibility or allowance.
    from app.modules.travel_km.verification import freeze_verification_snapshot
    verification = freeze_verification_snapshot(db, claim)
    previous = claim.status
    claim.status = "submitted"
    claim.submitted_at = utc_now()
    add_event(
        db, claim=claim, action="submitted", actor=requester, from_status=previous, to_status=claim.status,
        comments="Submitted to Admin for verification.",
        metadata={
            "smart_verification_score": verification.score,
            "smart_verification_outcome": verification.outcome,
            "advisory_only": True,
        },
    )
    db.commit(); db.refresh(claim)
    return claim


def _eligible_amount(eligible_km: Decimal | None, max_km: Decimal, *, default: Decimal) -> Decimal:
    value = money(eligible_km if eligible_km is not None else default)
    if value < 0:
        raise ValueError("Eligible KM cannot be negative")
    if value > max_km:
        raise ValueError("Eligible KM cannot exceed the employee's odometer KM")
    return value


def admin_decision(db: Session, *, claim: TravelKmClaim, actor: User, payload: TravelKmDecisionRequest) -> TravelKmClaim:
    if claim.status != "submitted":
        raise ValueError("Admin can act only on submitted travel claims")
    previous = claim.status
    if payload.action == "approve":
        max_km = money(claim.odometer_km)
        eligible = _eligible_amount(payload.eligible_km, max_km, default=max_km)
        if eligible != max_km and not payload.comments.strip():
            raise ValueError("Admin remarks are required when eligible KM is adjusted")
        claim.admin_eligible_km = eligible
        claim.status = "admin_approved"
    elif payload.action == "send_back":
        claim.status = "admin_sent_back"
    else:
        claim.status = "admin_rejected"
    claim.admin_decision_by_id = actor.id
    claim.admin_decision_at = utc_now()
    claim.admin_comments = payload.comments.strip() or None
    add_event(db, claim=claim, action=f"admin_{payload.action}", actor=actor, from_status=previous, to_status=claim.status, comments=payload.comments, metadata={"eligible_km": float(claim.admin_eligible_km or 0)})
    db.commit(); db.refresh(claim)
    return claim


def hr_decision(db: Session, *, claim: TravelKmClaim, actor: User, payload: TravelKmDecisionRequest) -> TravelKmClaim:
    if claim.status != "admin_approved":
        raise ValueError("HR can act only after Admin approval")
    previous = claim.status
    if payload.action == "approve":
        max_km = money(claim.odometer_km)
        admin_cap = money(claim.admin_eligible_km if claim.admin_eligible_km is not None else max_km)
        eligible = _eligible_amount(payload.eligible_km, max_km, default=admin_cap)
        if eligible > admin_cap:
            raise ValueError("HR eligible KM cannot exceed the Admin verified KM")
        if eligible != admin_cap and not payload.comments.strip():
            raise ValueError("HR remarks are required when eligible KM is adjusted")
        claim.hr_eligible_km = eligible
        claim.final_eligible_km = eligible
        claim.final_allowance = money(eligible * money(claim.rate_per_km))
        claim.status = "hr_approved"
    elif payload.action == "send_back":
        claim.status = "hr_sent_back"
    else:
        claim.status = "hr_rejected"
    claim.hr_decision_by_id = actor.id
    claim.hr_decision_at = utc_now()
    claim.hr_comments = payload.comments.strip() or None
    add_event(db, claim=claim, action=f"hr_{payload.action}", actor=actor, from_status=previous, to_status=claim.status, comments=payload.comments, metadata={"eligible_km": float(claim.hr_eligible_km or 0), "final_allowance": float(claim.final_allowance or 0)})
    db.commit(); db.refresh(claim)
    return claim


def finance_decision(db: Session, *, claim: TravelKmClaim, actor: User, payload: TravelKmFinanceDecisionRequest) -> TravelKmClaim:
    if claim.status != "hr_approved":
        raise ValueError("Finance can approve or reject only after HR approval")
    previous = claim.status
    claim.finance_decision_by_id = actor.id
    claim.finance_decision_at = utc_now()
    claim.finance_comments = payload.comments.strip() or None
    if payload.action == "reject":
        claim.status = "finance_rejected"
        add_event(db, claim=claim, action="finance_rejected", actor=actor, from_status=previous, to_status=claim.status, comments=payload.comments)
    else:
        # Travel allowance is added through the monthly salary process. Finance
        # performs the final approval only; no payment/UTR data is collected.
        claim.status = "finance_approved"
        claim.payment_reference = None
        claim.payment_mode = None
        claim.paid_amount = None
        claim.paid_at = None
        add_event(
            db,
            claim=claim,
            action="finance_approved",
            actor=actor,
            from_status=previous,
            to_status=claim.status,
            comments=payload.comments,
            metadata={"approved_for_monthly_salary": True, "final_allowance": float(claim.final_allowance or 0)},
        )
    db.commit(); db.refresh(claim)
    return claim


def finance_payment(db: Session, *, claim: TravelKmClaim, actor: User, payload: TravelKmPaymentRequest) -> TravelKmClaim:
    """Compatibility wrapper for older V1 callers.

    action=pay now means final Finance approval for monthly salary addition.
    Payment reference/mode are intentionally ignored.
    """
    action = "reject" if payload.action == "reject" else "approve"
    return finance_decision(
        db,
        claim=claim,
        actor=actor,
        payload=TravelKmFinanceDecisionRequest(action=action, comments=payload.comments),
    )


def visible_claim_query(*, viewer: User, effective_role: str):
    stmt = select(TravelKmClaim).options(*_claim_options())
    if effective_role == EMPLOYEE_ROLE:
        stmt = stmt.where(TravelKmClaim.requester_id == viewer.id)
    elif effective_role not in STAFF_VISIBLE_ROLES:
        stmt = stmt.where(TravelKmClaim.id == -1)
    return stmt


def list_visible_claims(db: Session, *, viewer: User, effective_role: str, status: str | None = None, project_id: int | None = None, requester_id: int | None = None, date_from: date | None = None, date_to: date | None = None) -> list[TravelKmClaim]:
    stmt = visible_claim_query(viewer=viewer, effective_role=effective_role)
    if status:
        stmt = stmt.where(TravelKmClaim.status == status)
    if project_id:
        stmt = stmt.where(TravelKmClaim.project_id == project_id)
    if requester_id and effective_role in STAFF_VISIBLE_ROLES:
        stmt = stmt.where(TravelKmClaim.requester_id == requester_id)
    if date_from:
        stmt = stmt.where(TravelKmClaim.travel_date >= date_from)
    if date_to:
        stmt = stmt.where(TravelKmClaim.travel_date <= date_to)
    return list(db.scalars(stmt.order_by(TravelKmClaim.travel_date.desc(), TravelKmClaim.id.desc())).unique().all())


def get_visible_claim(db: Session, *, claim_id: int, viewer: User, effective_role: str) -> TravelKmClaim | None:
    stmt = visible_claim_query(viewer=viewer, effective_role=effective_role).where(TravelKmClaim.id == claim_id)
    return db.scalar(stmt)


def claim_payload(db: Session, claim: TravelKmClaim, *, viewer: User, effective_role: str) -> dict:
    requester = db.get(User, claim.requester_id)
    actor_ids = {e.actor_user_id for e in claim.events if e.actor_user_id}
    actors = {u.id: u for u in db.scalars(select(User).where(User.id.in_(actor_ids))).all()} if actor_ids else {}
    attachments = []
    for item in claim.attachments:
        attachments.append({
            "id": item.id,
            "phase": item.phase,
            "original_filename": item.original_filename,
            "mime_type": item.mime_type,
            "file_size": item.file_size,
            "content_sha256": item.content_sha256,
            "device_latitude": item.device_latitude,
            "device_longitude": item.device_longitude,
            "device_accuracy_m": item.device_accuracy_m,
            "device_captured_at": item.device_captured_at,
            "exif_gps_present": item.exif_gps_present,
            "exif_latitude": item.exif_latitude,
            "exif_longitude": item.exif_longitude,
            "exif_captured_at": item.exif_captured_at,
            "exif_device_distance_m": item.exif_device_distance_m,
            "verification_flag": item.verification_flag,
            "created_at": item.created_at,
        })
    events = [{
        "id": e.id,
        "action": e.action,
        "actor_user_id": e.actor_user_id,
        "actor_name": e.actor_name,
        "actor_email": e.actor_email,
        "actor_role": e.actor_role,
        "from_status": e.from_status,
        "to_status": e.to_status,
        "comments": e.comments,
        "event_metadata": json.loads(e.event_metadata) if e.event_metadata else None,
        "created_at": e.created_at,
    } for e in claim.events]
    routing = claim.email_routing
    email_routing = None if routing is None else {
        "reporting_manager_email": routing.reporting_manager_email,
        "to_emails": email_list(routing.to_emails_json),
        "cc_emails": email_list(routing.cc_emails_json),
        "created_at": routing.created_at,
        "updated_at": routing.updated_at,
    }
    email_history = [{
        "id": delivery.id,
        "event_type": delivery.event_type,
        "subject": delivery.subject,
        "to_emails": email_list(delivery.to_emails_json),
        "cc_emails": email_list(delivery.cc_emails_json),
        "delivery_mode": delivery.delivery_mode,
        "status": delivery.status,
        "error_message": delivery.error_message,
        "attempted_at": delivery.attempted_at,
        "sent_at": delivery.sent_at,
    } for delivery in claim.email_deliveries]
    latest_delivery = email_history[-1] if email_history else None
    return {
        "id": claim.id,
        "claim_code": claim.claim_code,
        "requester_id": claim.requester_id,
        "employee_name": requester.full_name if requester else "Unknown employee",
        "employee_email": requester.email if requester else None,
        "employee_id": getattr(requester, "employee_id", None) if requester else None,
        "department": getattr(requester, "department", None) if requester else None,
        "project_id": claim.project_id,
        "project_code": claim.project_code_snapshot,
        "project_name": claim.project_name_snapshot,
        "client_name": claim.client_name_snapshot,
        "travel_date": claim.travel_date,
        "purpose_description": claim.purpose_description,
        "start_km": float(claim.start_km),
        "end_km": float(claim.end_km) if claim.end_km is not None else None,
        "odometer_km": float(claim.odometer_km) if claim.odometer_km is not None else None,
        "start_latitude": claim.start_latitude,
        "start_longitude": claim.start_longitude,
        "start_accuracy_m": claim.start_accuracy_m,
        "start_captured_at": claim.start_captured_at,
        "end_latitude": claim.end_latitude,
        "end_longitude": claim.end_longitude,
        "end_accuracy_m": claim.end_accuracy_m,
        "end_captured_at": claim.end_captured_at,
        "gps_straight_line_km": float(claim.gps_straight_line_km) if claim.gps_straight_line_km is not None else None,
        "distance_variance_km": float(claim.distance_variance_km) if claim.distance_variance_km is not None else None,
        "distance_variance_percent": float(claim.distance_variance_percent) if claim.distance_variance_percent is not None else None,
        "rate_per_km": float(claim.rate_per_km),
        "calculated_allowance": float(claim.calculated_allowance) if claim.calculated_allowance is not None else None,
        "admin_eligible_km": float(claim.admin_eligible_km) if claim.admin_eligible_km is not None else None,
        "hr_eligible_km": float(claim.hr_eligible_km) if claim.hr_eligible_km is not None else None,
        "final_eligible_km": float(claim.final_eligible_km) if claim.final_eligible_km is not None else None,
        "final_allowance": float(claim.final_allowance) if claim.final_allowance is not None else None,
        "status": claim.status,
        "admin_comments": claim.admin_comments,
        "admin_decision_at": claim.admin_decision_at,
        "hr_comments": claim.hr_comments,
        "hr_decision_at": claim.hr_decision_at,
        "finance_comments": claim.finance_comments,
        "finance_decision_at": claim.finance_decision_at,
        "payment_reference": claim.payment_reference,
        "payment_mode": claim.payment_mode,
        "paid_amount": float(claim.paid_amount) if claim.paid_amount is not None else None,
        "paid_at": claim.paid_at,
        "submitted_at": claim.submitted_at,
        "created_at": claim.created_at,
        "updated_at": claim.updated_at,
        "email_routing": email_routing,
        "email_history": email_history,
        "attachments": attachments,
        "events": events,
        "permissions": {
            "can_edit": effective_role == EMPLOYEE_ROLE and claim.requester_id == viewer.id and claim.status in EDITABLE_STATUSES,
            "can_submit": effective_role == EMPLOYEE_ROLE and claim.requester_id == viewer.id and claim.status in EDITABLE_STATUSES,
            "can_edit_email_routing": effective_role == EMPLOYEE_ROLE and claim.requester_id == viewer.id and claim.status in EDITABLE_STATUSES,
            "can_retry_email": bool(
                effective_role == EMPLOYEE_ROLE
                and claim.requester_id == viewer.id
                and claim.submitted_at is not None
                and latest_delivery
                and latest_delivery.get("status") == "failed"
            ),
            "can_admin_decide": effective_role == ADMIN_ROLE and claim.status == "submitted",
            "can_hr_decide": effective_role == HR_ROLE and claim.status == "admin_approved",
            "can_finance_decide": effective_role == FINANCE_ROLE and claim.status == "hr_approved",
            # Kept for V1 frontend compatibility; it now means Finance can decide.
            "can_finance_pay": effective_role == FINANCE_ROLE and claim.status == "hr_approved",
            "read_only_management": effective_role == MANAGEMENT_ROLE,
        },
    }


def dashboard_payload(db: Session, *, viewer: User, effective_role: str) -> dict:
    claims = list_visible_claims(db, viewer=viewer, effective_role=effective_role)
    counts = Counter(c.status for c in claims)
    total_km = sum((money(c.odometer_km) for c in claims if c.odometer_km is not None), Decimal("0"))
    approved_allowance = sum((money(c.final_allowance) for c in claims if c.final_allowance is not None), Decimal("0"))
    paid = sum((money(c.paid_amount) for c in claims if c.paid_amount is not None), Decimal("0"))
    salary_approved = sum(
        (money(c.final_allowance) for c in claims if c.status in {"finance_approved", "paid"} and c.final_allowance is not None),
        Decimal("0"),
    )
    project = defaultdict(lambda: {"claims": 0, "km": Decimal("0"), "allowance": Decimal("0")})
    employee = defaultdict(lambda: {"claims": 0, "km": Decimal("0"), "allowance": Decimal("0")})
    monthly = defaultdict(lambda: {"claims": 0, "km": Decimal("0"), "allowance": Decimal("0")})
    user_cache: dict[int, User | None] = {}
    for c in claims:
        project_label = f"{c.project_code_snapshot} - {c.project_name_snapshot}"
        p = project[project_label]
        p["claims"] += 1; p["km"] += money(c.odometer_km); p["allowance"] += money(c.final_allowance or c.calculated_allowance)
        if c.requester_id not in user_cache:
            user_cache[c.requester_id] = db.get(User, c.requester_id)
        u = user_cache[c.requester_id]
        name = u.full_name if u else f"Employee #{c.requester_id}"
        e = employee[name]
        e["claims"] += 1; e["km"] += money(c.odometer_km); e["allowance"] += money(c.final_allowance or c.calculated_allowance)
        key = c.travel_date.strftime("%Y-%m")
        m = monthly[key]
        m["claims"] += 1; m["km"] += money(c.odometer_km); m["allowance"] += money(c.final_allowance or c.calculated_allowance)
    def rows(mapping):
        return [{"name": name, "claims": val["claims"], "km": float(val["km"]), "allowance": float(val["allowance"])} for name, val in sorted(mapping.items(), key=lambda item: (-item[1]["claims"], item[0]))]
    verification_counts = Counter(
        c.verification_snapshot.outcome
        for c in claims
        if c.verification_snapshot is not None
    )
    geofence_confirmed = sum(
        1 for c in claims
        if c.verification_snapshot is not None
        and c.verification_snapshot.geofence_configured
        and c.verification_snapshot.site_entered
    )
    return {
        "total_claims": len(claims),
        "total_km": float(total_km),
        "approved_allowance": float(approved_allowance),
        # V1 legacy payment metrics are retained for API compatibility.
        "paid_amount": float(paid),
        "paid_count": counts.get("paid", 0),
        "salary_approved_amount": float(salary_approved),
        "finance_approved_count": counts.get("finance_approved", 0) + counts.get("paid", 0),
        "pending_admin": counts.get("submitted", 0),
        "pending_hr": counts.get("admin_approved", 0),
        "pending_finance": counts.get("hr_approved", 0),
        "rejected_count": counts.get("admin_rejected", 0) + counts.get("hr_rejected", 0) + counts.get("finance_rejected", 0),
        "sent_back_count": counts.get("admin_sent_back", 0) + counts.get("hr_sent_back", 0),
        "status_counts": dict(counts),
        "smart_verification_counts": dict(verification_counts),
        "verified_journeys": verification_counts.get("verified", 0),
        "journeys_needing_review": sum(verification_counts.get(key, 0) for key in ("review", "needs_review", "high_variance", "insufficient_gps")),
        "high_variance_journeys": verification_counts.get("high_variance", 0),
        "geofence_confirmed_journeys": geofence_confirmed,
        "project_summary": rows(project)[:20],
        "employee_summary": rows(employee)[:20],
        "monthly_summary": [{"name": name, "claims": monthly[name]["claims"], "km": float(monthly[name]["km"]), "allowance": float(monthly[name]["allowance"])} for name in sorted(monthly.keys(), reverse=True)[:18]],
    }
