from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, load_only
from app.api.dependencies import CurrentAuth
from app.models.entities import User, utc_now
from app.modules.notifications.service import create_global_notification
from .models import Payable, PayableApproval, PayablePayment, PayableDocument, PayableAudit
from .schemas import BillInput

MANAGERS = ('vinod@nakshatech.com', 'chethan@nakshatech.com')


def role(auth: CurrentAuth) -> str:
    # No admin-equivalent / global-management bypass for these financial records.
    value = auth.effective_role
    email = str(auth.user.email).strip().lower()
    if value == 'management' and email in MANAGERS:
        return 'manager'
    return value if value in ('admin', 'finance') else 'none'


def required(auth: CurrentAuth, *roles: str) -> str:
    value = role(auth)
    if value not in roles:
        raise HTTPException(403, 'Payables access is not allowed for this login')
    return value


def accessible(db: Session, auth: CurrentAuth, payable_id: int, *, lock: bool = False) -> Payable:
    current_role = required(auth, 'admin', 'finance', 'manager')
    statement = select(Payable).where(Payable.id == payable_id)
    if current_role == 'admin':
        statement = statement.where(Payable.origin == 'admin')
    if lock:
        statement = statement.with_for_update()
    bill = db.scalar(statement)
    if bill is None:
        raise HTTPException(404, 'Payable not found')
    return bill


def managers(db: Session) -> list[User]:
    users = list(db.scalars(select(User).where(func.lower(User.email).in_(MANAGERS), User.role == 'management', User.is_active.is_(True), User.account_status == 'active')).all())
    if {str(user.email).lower() for user in users} != set(MANAGERS):
        raise HTTPException(409, 'Both management logins must be active before submission')
    return users


def _finance_ids(db: Session) -> list[int]:
    return list(db.scalars(select(User.id).where(User.role == 'finance', User.is_active.is_(True), User.account_status == 'active')).all())


def notify(db: Session, bill: Payable, event: str, message: str, recipients: list[int]):
    if not recipients:
        return
    create_global_notification(db, event_type=f'payables.{event}', title=f'{bill.code} - {event.replace("_", " ").title()}', message=message,
        category='approval' if event in ('submitted', 'returned') else 'system',
        recipient_user_ids=sorted(set(recipients)), target_url=f'/payables/{bill.id}',
        dedupe_key=f'payables:{bill.id}:v{bill.approval_version}:{event}:{bill.paid_paise}')


def audit(db: Session, bill: Payable, auth: CurrentAuth, action: str, detail: object):
    db.add(PayableAudit(payable_id=bill.id, actor_id=auth.user.id, action=action, details=json.dumps(detail, default=str)))


def money_to_paise(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def fill_fields(bill: Payable, data: BillInput) -> None:
    base = money_to_paise(data.base_amount)
    gst_rate_bps = int((data.gst_rate * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    gst = int((Decimal(base) * Decimal(gst_rate_bps) / 10000).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    for field in ('bill_name', 'bill_number', 'bill_category', 'vendor_name', 'bill_date', 'due_date', 'priority'):
        setattr(bill, field, getattr(data, field))
    for field in ('vendor_gstin', 'billing_period', 'cost_center', 'remarks'):
        setattr(bill, field, getattr(data, field))
    bill.base_paise = base
    bill.gst_rate_bps = gst_rate_bps
    bill.gst_paise = gst
    bill.total_paise = base + gst


def approvals_of(db: Session, bill: Payable) -> dict[str, dict]:
    rows = db.scalars(select(PayableApproval).where(PayableApproval.payable_id == bill.id, PayableApproval.approval_version == bill.approval_version)).all()
    result = {name: {'decision': 'pending', 'comment': None, 'decided_at': None} for name in MANAGERS}
    for row in rows:
        if row.manager_email in result:
            result[row.manager_email] = {'decision': row.decision, 'comment': row.comment, 'decided_at': row.decided_at.isoformat() if row.decided_at else None}
    return result


def serialize(db: Session, bill: Payable) -> dict:
    approvals = approvals_of(db, bill)
    pay = db.scalars(select(PayablePayment).where(PayablePayment.payable_id == bill.id).order_by(PayablePayment.id.asc())).all()
    docs = db.scalars(select(PayableDocument).options(load_only(PayableDocument.id, PayableDocument.payable_id, PayableDocument.payment_id, PayableDocument.kind, PayableDocument.filename)).where(PayableDocument.payable_id == bill.id).order_by(PayableDocument.id.asc())).all()
    doc_rows = [{'id': d.id, 'kind': d.kind, 'filename': d.filename, 'payment_id': d.payment_id} for d in docs]
    total = bill.total_paise
    return {
        'id': bill.id, 'code': bill.code, 'origin': bill.origin, 'raised_by_id': bill.raised_by_id,
        'bill_name': bill.bill_name, 'bill_number': bill.bill_number, 'bill_category': bill.bill_category,
        'vendor_name': bill.vendor_name, 'vendor_gstin': bill.vendor_gstin,
        'bill_date': bill.bill_date.isoformat(), 'due_date': bill.due_date.isoformat(),
        'billing_period': bill.billing_period, 'cost_center': bill.cost_center,
        'base_amount': bill.base_paise / 100, 'gst_rate': bill.gst_rate_bps / 100,
        'gst_amount': bill.gst_paise / 100, 'total_amount': total / 100,
        'paid_amount': bill.paid_paise / 100, 'balance_amount': (total - bill.paid_paise) / 100,
        'progress': round(100 * bill.paid_paise / total, 2) if total else 0,
        'status': bill.status, 'priority': bill.priority, 'remarks': bill.remarks,
        'approval_version': bill.approval_version, 'approvals': approvals,
        'payments': [{'id': p.id, 'amount': p.amount_paise / 100, 'date': p.payment_date.isoformat(), 'method': p.payment_method, 'reference': p.reference, 'recorded_by_id': p.recorded_by_id} for p in pay],
        'documents': doc_rows, 'created_at': bill.created_at.isoformat() if bill.created_at else None,
    }


def summary(bill: Payable) -> dict:
    """List view: avoid N+1 queries and loading large document binaries."""
    total = bill.total_paise
    return {
        'id': bill.id, 'code': bill.code, 'origin': bill.origin, 'raised_by_id': bill.raised_by_id,
        'bill_name': bill.bill_name, 'bill_number': bill.bill_number, 'bill_category': bill.bill_category,
        'vendor_name': bill.vendor_name, 'vendor_gstin': bill.vendor_gstin,
        'bill_date': bill.bill_date.isoformat(), 'due_date': bill.due_date.isoformat(),
        'billing_period': bill.billing_period, 'cost_center': bill.cost_center,
        'base_amount': bill.base_paise / 100, 'gst_rate': bill.gst_rate_bps / 100,
        'gst_amount': bill.gst_paise / 100, 'total_amount': total / 100,
        'paid_amount': bill.paid_paise / 100, 'balance_amount': (total - bill.paid_paise) / 100,
        'progress': round(100 * bill.paid_paise / total, 2) if total else 0,
        'status': bill.status, 'priority': bill.priority, 'remarks': bill.remarks,
        'approval_version': bill.approval_version, 'approvals': {}, 'payments': [], 'documents': [],
        'created_at': bill.created_at.isoformat() if bill.created_at else None,
    }
