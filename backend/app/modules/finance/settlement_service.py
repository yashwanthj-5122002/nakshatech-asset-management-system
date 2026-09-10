from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
import logging
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

from app.models.entities import User, utc_now
from app.modules.employee_portal.service import record_audit, send_email
from app.modules.finance.models import (
    ExpenseClaim,
    ExpenseSettlement,
    ExpenseSettlementAttachment,
    ExpenseSettlementEvent,
    ExpenseSettlementItem,
)
from app.modules.finance.schemas import SettlementUpsertRequest
from app.modules.notifications.service import create_global_notification

logger = logging.getLogger(__name__)

EMPLOYEE_ROLE = "employee"
ADMIN_ROLE = "admin"
FINANCE_ROLE = "finance"
MANAGEMENT_ROLE = "management"
VISIBLE_STAFF_ROLES = {ADMIN_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE}
EDITABLE_SETTLEMENT_STATUSES = {"draft", "admin_sent_back", "admin_rejected", "finance_sent_back"}


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _claim_paid_amount(claim: ExpenseClaim) -> Decimal:
    if claim.payments:
        return _money(sum((_money(payment.amount) for payment in claim.payments), Decimal("0.00")))
    return _money(claim.paid_amount)


def advance_chain(root: ExpenseClaim) -> list[ExpenseClaim]:
    return [root, *list(root.linked_additional_advances)]


def total_advance_received(root: ExpenseClaim) -> Decimal:
    return _money(sum((_claim_paid_amount(claim) for claim in advance_chain(root)), Decimal("0.00")))


def _user_name(db: Session, user_id: int | None) -> str | None:
    if not user_id:
        return None
    user = db.get(User, user_id)
    return user.full_name if user else None


def _safe_notification(db: Session, **kwargs) -> None:
    try:
        create_global_notification(db, **kwargs)
    except Exception:
        logger.exception("Finance settlement notification creation failed")


def _add_event(
    db: Session,
    *,
    settlement: ExpenseSettlement,
    action: str,
    actor: User | None,
    from_status: str | None,
    to_status: str,
    comments: str | None,
) -> None:
    db.add(ExpenseSettlementEvent(
        settlement_id=settlement.id,
        event_key=f"{settlement.id}:{action}:{secrets.token_hex(12)}",
        action=action,
        actor_user_id=actor.id if actor else None,
        actor_name=actor.full_name if actor else None,
        actor_email=actor.email if actor else None,
        actor_role=actor.role if actor else None,
        from_status=from_status,
        to_status=to_status,
        comments=(comments or "").strip() or None,
    ))


def _recalculate(settlement: ExpenseSettlement) -> None:
    received = total_advance_received(settlement.root_claim)
    expenses = _money(sum((_money(item.amount) for item in settlement.items), Decimal("0.00")))
    settlement.total_advance_received = received
    settlement.total_expense_amount = expenses
    settlement.balance_to_return = max(Decimal("0.00"), _money(received - expenses))
    settlement.shortage_amount = max(Decimal("0.00"), _money(expenses - received))


def tally_status(settlement: ExpenseSettlement) -> str:
    if _money(settlement.shortage_amount) > 0:
        return "shortage"
    if _money(settlement.balance_to_return) > 0:
        return "balance_to_return"
    return "tallied"


def _attachment_payload(db: Session, attachment: ExpenseSettlementAttachment) -> dict:
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


def settlement_payload(db: Session, settlement: ExpenseSettlement, *, viewer: User, effective_role: str) -> dict:
    from app.modules.finance.service import project_payload

    requester = db.get(User, settlement.requester_id)
    role = (effective_role or viewer.role).strip().lower()
    is_owner = role == EMPLOYEE_ROLE and settlement.requester_id == viewer.id
    _recalculate(settlement)
    return {
        "id": settlement.id,
        "settlement_code": settlement.settlement_code,
        "root_claim_id": settlement.root_claim_id,
        "root_claim_code": settlement.root_claim.claim_code,
        "requester_id": settlement.requester_id,
        "requester_name": requester.full_name if requester else "Unknown employee",
        "project": project_payload(settlement.root_claim.project),
        "status": settlement.status,
        "total_advance_received": float(settlement.total_advance_received),
        "total_expense_amount": float(settlement.total_expense_amount),
        "balance_to_return": float(settlement.balance_to_return),
        "shortage_amount": float(settlement.shortage_amount),
        "tally_status": tally_status(settlement),
        "submitted_at": settlement.submitted_at,
        "finalized_at": settlement.finalized_at,
        "admin_decision_by_name": _user_name(db, settlement.admin_decision_by_id),
        "admin_decision_at": settlement.admin_decision_at,
        "admin_comments": settlement.admin_comments,
        "finance_decision_by_name": _user_name(db, settlement.finance_decision_by_id),
        "finance_decision_at": settlement.finance_decision_at,
        "finance_comments": settlement.finance_comments,
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
            for item in settlement.items
        ],
        "attachments": [_attachment_payload(db, attachment) for attachment in settlement.attachments],
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
            for event in settlement.events
        ],
        "can_edit": is_owner and settlement.status in EDITABLE_SETTLEMENT_STATUSES,
        "can_submit": is_owner and settlement.status in EDITABLE_SETTLEMENT_STATUSES,
        "can_admin_decide": role == ADMIN_ROLE and settlement.status == "submitted",
        "can_finance_decide": role == FINANCE_ROLE and settlement.status == "admin_approved",
    }


def get_visible_settlement(
    db: Session,
    *,
    settlement_id: int | None = None,
    root_claim_id: int | None = None,
    viewer: User,
    effective_role: str,
) -> ExpenseSettlement | None:
    settlement = None
    if settlement_id is not None:
        settlement = db.get(ExpenseSettlement, settlement_id)
    elif root_claim_id is not None:
        settlement = db.scalar(select(ExpenseSettlement).where(ExpenseSettlement.root_claim_id == root_claim_id))
    if settlement is None:
        return None
    role = effective_role.strip().lower()
    if role == EMPLOYEE_ROLE:
        return settlement if settlement.requester_id == viewer.id else None
    if role in VISIBLE_STAFF_ROLES:
        if settlement.status == "draft":
            return None
        return settlement
    return None


def upsert_settlement(
    db: Session,
    *,
    root_claim: ExpenseClaim,
    requester: User,
    payload: SettlementUpsertRequest,
    request=None,
) -> ExpenseSettlement:
    if root_claim.claim_type != "advance" or root_claim.requester_id != requester.id:
        raise PermissionError("Settlement can be created only for your original Advance Request")
    if total_advance_received(root_claim) <= 0:
        raise ValueError("Finance must release at least part of the advance before settlement can be prepared")

    settlement = db.scalar(select(ExpenseSettlement).where(ExpenseSettlement.root_claim_id == root_claim.id))
    if settlement is None:
        settlement = ExpenseSettlement(
            settlement_code=f"DRAFT-{secrets.token_hex(10)}",
            root_claim_id=root_claim.id,
            requester_id=requester.id,
            status="draft",
        )
        db.add(settlement)
        db.flush()
        settlement.settlement_code = f"NT-SET-{utc_now().year}-{settlement.id:05d}"
        _add_event(db, settlement=settlement, action="created", actor=requester, from_status=None, to_status="draft", comments="Advance settlement draft created")
    elif settlement.status not in EDITABLE_SETTLEMENT_STATUSES:
        raise PermissionError("This settlement is no longer editable")

    settlement.items.clear()
    for entry in payload.items:
        settlement.items.append(ExpenseSettlementItem(
            category=entry.category.strip().lower(),
            other_category=(entry.other_category or "").strip() or None,
            description=entry.description.strip(),
            amount=_money(entry.amount),
            payment_mode=entry.payment_mode,
            expense_date=entry.expense_date,
        ))
    db.flush()
    _recalculate(settlement)
    root_claim.settlement_status = settlement.status
    _add_event(db, settlement=settlement, action="updated", actor=requester, from_status=settlement.status, to_status=settlement.status, comments="Employee updated settlement expense details")
    record_audit(
        db,
        event_type="FINANCE_SETTLEMENT_UPDATED",
        request=request,
        user=requester,
        module="finance",
        target_type="expense_settlement",
        target_id=settlement.id,
        details={
            "settlement_code": settlement.settlement_code,
            "root_claim_id": root_claim.id,
            "advance_received": float(settlement.total_advance_received),
            "expense_total": float(settlement.total_expense_amount),
            "tally_status": tally_status(settlement),
        },
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def submit_settlement(db: Session, *, settlement: ExpenseSettlement, requester: User, request=None) -> ExpenseSettlement:
    if settlement.requester_id != requester.id or settlement.status not in EDITABLE_SETTLEMENT_STATUSES:
        raise PermissionError("This settlement cannot be submitted")
    if not settlement.items:
        raise ValueError("Add at least one actual expense before submitting settlement")
    if not settlement.attachments:
        raise ValueError("Attach the supporting bills/proof before submitting settlement")
    _recalculate(settlement)
    previous = settlement.status
    settlement.status = "submitted"
    settlement.submitted_at = utc_now()
    settlement.admin_decision_by_id = None
    settlement.admin_decision_at = None
    settlement.admin_comments = None
    settlement.finance_decision_by_id = None
    settlement.finance_decision_at = None
    settlement.finance_comments = None
    settlement.root_claim.settlement_status = "submitted"
    _add_event(db, settlement=settlement, action="submitted", actor=requester, from_status=previous, to_status="submitted", comments="Submitted for Admin settlement verification")
    _safe_notification(
        db,
        event_type="FINANCE_SETTLEMENT_SUBMITTED",
        category="approval",
        title=f"Advance settlement awaiting Admin verification: {settlement.settlement_code}",
        message=f"{requester.full_name} submitted settlement for {settlement.root_claim.claim_code}. Expenses: INR {float(settlement.total_expense_amount):,.2f}.",
        target_url=f"/finance/claims/{settlement.root_claim_id}",
        recipient_roles=[ADMIN_ROLE],
        dedupe_key=f"finance-settlement:{settlement.id}:submitted:{settlement.submitted_at.isoformat()}",
    )
    record_audit(
        db,
        event_type="FINANCE_SETTLEMENT_SUBMITTED",
        request=request,
        user=requester,
        module="finance",
        target_type="expense_settlement",
        target_id=settlement.id,
        details={"settlement_code": settlement.settlement_code, "tally_status": tally_status(settlement)},
    )
    db.commit()
    db.refresh(settlement)
    return settlement


def admin_settlement_decision(
    db: Session,
    *,
    settlement: ExpenseSettlement,
    actor: User,
    action: str,
    comments: str,
    request=None,
) -> ExpenseSettlement:
    if settlement.status != "submitted":
        raise ValueError("Only a submitted settlement can be decided by Admin")
    previous = settlement.status
    target = {"approve": "admin_approved", "reject": "admin_rejected", "send_back": "admin_sent_back"}[action]
    settlement.status = target
    settlement.admin_decision_by_id = actor.id
    settlement.admin_decision_at = utc_now()
    settlement.admin_comments = comments.strip()
    settlement.root_claim.settlement_status = target
    _add_event(db, settlement=settlement, action=f"admin_{action}", actor=actor, from_status=previous, to_status=target, comments=comments)
    if action == "approve":
        _safe_notification(
            db,
            event_type="FINANCE_SETTLEMENT_ADMIN_APPROVED",
            category="approval",
            title=f"Settlement requires Finance verification: {settlement.settlement_code}",
            message=f"Admin verified the bills for {settlement.root_claim.claim_code}. Finance final verification is required.",
            target_url=f"/finance/claims/{settlement.root_claim_id}",
            recipient_roles=[FINANCE_ROLE],
            dedupe_key=f"finance-settlement:{settlement.id}:admin-approved:{settlement.admin_decision_at.isoformat()}",
        )
    else:
        _safe_notification(
            db,
            event_type=f"FINANCE_SETTLEMENT_ADMIN_{action.upper()}",
            category="approval",
            title=f"Settlement update: {settlement.settlement_code}",
            message=f"Admin {('sent back' if action == 'send_back' else 'rejected')} the settlement. Review the verification comments.",
            target_url=f"/expenses/{settlement.root_claim_id}",
            recipient_user_ids=[settlement.requester_id],
            dedupe_key=f"finance-settlement:{settlement.id}:admin-{action}:{settlement.admin_decision_at.isoformat()}",
        )
    record_audit(db, event_type=f"FINANCE_SETTLEMENT_ADMIN_{action.upper()}", request=request, user=actor, module="finance", target_type="expense_settlement", target_id=settlement.id, details={"comments": comments, "tally_status": tally_status(settlement)})
    db.commit()
    db.refresh(settlement)
    return settlement


def finance_settlement_decision(
    db: Session,
    *,
    settlement: ExpenseSettlement,
    actor: User,
    action: str,
    comments: str,
    request=None,
) -> ExpenseSettlement:
    if settlement.status != "admin_approved":
        raise ValueError("Finance can decide only a settlement already verified by Admin")
    _recalculate(settlement)
    previous = settlement.status
    target = {"approve": "finance_finalized", "reject": "finance_rejected", "send_back": "finance_sent_back"}[action]
    settlement.status = target
    settlement.finance_decision_by_id = actor.id
    settlement.finance_decision_at = utc_now()
    settlement.finance_comments = comments.strip()
    if action == "approve":
        settlement.finalized_at = utc_now()
        if tally_status(settlement) == "tallied":
            settlement.root_claim.settlement_status = "settled"
        elif tally_status(settlement) == "balance_to_return":
            settlement.root_claim.settlement_status = "finalized_balance_pending"
        else:
            settlement.root_claim.settlement_status = "finalized_shortage"
    else:
        settlement.root_claim.settlement_status = target
    _add_event(db, settlement=settlement, action=f"finance_{action}", actor=actor, from_status=previous, to_status=target, comments=f"{comments.strip()} | Tally: {tally_status(settlement)}")
    _safe_notification(
        db,
        event_type=f"FINANCE_SETTLEMENT_FINANCE_{action.upper()}",
        category="approval",
        title=f"Settlement decision: {settlement.settlement_code}",
        message=(
            f"Finance finalized settlement. Advance received INR {float(settlement.total_advance_received):,.2f}; supported expenses INR {float(settlement.total_expense_amount):,.2f}; tally {tally_status(settlement).replace('_', ' ')}."
            if action == "approve"
            else f"Finance {('sent back' if action == 'send_back' else 'rejected')} the settlement."
        ),
        target_url=f"/expenses/{settlement.root_claim_id}",
        recipient_user_ids=[settlement.requester_id],
        dedupe_key=f"finance-settlement:{settlement.id}:finance-{action}:{settlement.finance_decision_at.isoformat()}",
    )
    record_audit(db, event_type=f"FINANCE_SETTLEMENT_FINANCE_{action.upper()}", request=request, user=actor, module="finance", target_type="expense_settlement", target_id=settlement.id, details={"comments": comments, "tally_status": tally_status(settlement), "advance_received": float(settlement.total_advance_received), "expense_total": float(settlement.total_expense_amount)})
    db.commit()
    db.refresh(settlement)
    return settlement


def _configured_email_list(raw: str) -> list[str]:
    return [value.strip().lower() for value in (raw or "").replace(";", ",").split(",") if value.strip()]


def _role_emails(db: Session, roles: list[str]) -> list[str]:
    return list(db.scalars(
        select(User.email).where(User.role.in_(roles), User.is_active.is_(True), User.account_status == "active").order_by(User.id.asc())
    ).all())


def deliver_finance_settlement_emails(settlement_id: int, event: str, actor_id: int | None = None) -> None:
    """Best-effort settlement email. Database state remains authoritative if SMTP is unavailable."""
    with SessionLocal() as db:
        settlement = db.get(ExpenseSettlement, settlement_id)
        if not settlement:
            return
        requester = db.get(User, settlement.requester_id)
        actor = db.get(User, actor_id) if actor_id else None
        recipients: list[tuple[str, str]] = []
        if event == "submitted":
            emails = _configured_email_list(settings.finance_admin_notification_emails) or _role_emails(db, [ADMIN_ROLE])
            recipients.extend((email, "Admin settlement verification") for email in emails)
        elif event == "admin_approved":
            emails = _configured_email_list(settings.finance_team_notification_emails) or _role_emails(db, [FINANCE_ROLE])
            recipients.extend((email, "Finance settlement verification") for email in emails)
        elif requester:
            recipients.append((requester.email, "Employee settlement update"))
        if event == "finance_finalized":
            recipients.extend((email, "Management settlement visibility") for email in _role_emails(db, [MANAGEMENT_ROLE]))

        seen: set[str] = set()
        for recipient, audience in recipients:
            recipient = (recipient or "").strip().lower()
            if not recipient or recipient in seen:
                continue
            seen.add(recipient)
            event_label = {
                "submitted": "Settlement submitted for Admin verification",
                "admin_approved": "Settlement Admin-verified - Finance action required",
                "admin_sent_back": "Settlement sent back by Admin",
                "admin_rejected": "Settlement rejected by Admin",
                "finance_finalized": "Settlement finalized by Finance",
                "finance_sent_back": "Settlement sent back by Finance",
                "finance_rejected": "Settlement rejected by Finance",
            }.get(event, event.replace("_", " ").title())
            target = f"/expenses/{settlement.root_claim_id}" if audience.startswith("Employee") else f"/finance/claims/{settlement.root_claim_id}"
            link = f"{settings.app_public_url.rstrip('/')}{target}"
            body = "\n".join([
                settings.finance_email_heading,
                "",
                f"Status: {event_label}",
                f"Settlement: {settlement.settlement_code}",
                f"Advance: {settlement.root_claim.claim_code}",
                f"Project: {settlement.root_claim.project.project_code} - {settlement.root_claim.project.project_name}",
                f"Advance received: INR {float(settlement.total_advance_received):,.2f}",
                f"Supported expenses: INR {float(settlement.total_expense_amount):,.2f}",
                f"Balance to return: INR {float(settlement.balance_to_return):,.2f}",
                f"Shortage: INR {float(settlement.shortage_amount):,.2f}",
                f"Open record: {link}",
            ])
            try:
                send_email(recipient=recipient, subject=f"[{settlement.settlement_code}] {event_label}", body=body, from_name=settings.finance_email_heading)
                record_audit(db, event_type="FINANCE_SETTLEMENT_EMAIL_SENT", user=actor, actor_email=actor.email if actor else None, module="finance", target_type="expense_settlement", target_id=settlement.id, details={"recipient": recipient, "event": event, "audience": audience})
            except Exception:
                logger.exception("Settlement email delivery failed for %s to %s", settlement.settlement_code, recipient)
                record_audit(db, event_type="FINANCE_SETTLEMENT_EMAIL_FAILED", user=actor, actor_email=actor.email if actor else None, result="failed", module="finance", target_type="expense_settlement", target_id=settlement.id, details={"recipient": recipient, "event": event, "audience": audience})
        try:
            db.commit()
        except Exception:
            db.rollback()
