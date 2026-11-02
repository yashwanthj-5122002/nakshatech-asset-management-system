"""Isolated authenticated Payables API. No writes to legacy finance tables."""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User, utc_now
from .models import Payable, PayableApproval, PayablePayment, PayableDocument, PayableAudit
from .schemas import BillInput, DecisionInput
from .service import MANAGERS, accessible, approvals_of, audit, fill_fields, managers, money_to_paise, notify, required, role, serialize, summary, _finance_ids

router = APIRouter(prefix='/payables', tags=['payables'])
MAX_FILE_BYTES = 10 * 1024 * 1024


def save_document(db: Session, auth: CurrentAuth, bill: Payable, uploaded: UploadFile, kind: str, payment_id: int | None = None) -> PayableDocument:
    # Filename never becomes a disk path or response header without sanitization.
    filename = Path((uploaded.filename or 'document').replace('\\', '/')).name[:180]
    payload = uploaded.file.read(MAX_FILE_BYTES + 1)
    if not payload or len(payload) > MAX_FILE_BYTES:
        raise HTTPException(400, 'A non-empty document of at most 10 MB is required')
    kind_type = None
    if payload.startswith(b'%PDF-'):
        kind_type = 'application/pdf'
    elif payload.startswith(b'\xff\xd8\xff'):
        kind_type = 'image/jpeg'
    elif payload.startswith(b'\x89PNG\r\n\x1a\n'):
        kind_type = 'image/png'
    if not kind_type:
        raise HTTPException(400, 'Only original PDF, JPG or PNG documents are supported')
    item = PayableDocument(payable_id=bill.id, payment_id=payment_id, kind=kind,
        filename=filename, media_type=kind_type, sha256=hashlib.sha256(payload).hexdigest(),
        content=payload, uploaded_by_id=auth.user.id)
    db.add(item)
    return item


def commit(db: Session):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Duplicate bill number for this vendor, or duplicate payment reference') from exc


@router.get('/me')
def whoami(auth: CurrentAuth = Depends(get_current_auth)):
    return {'role': role(auth), 'email': auth.user.email, 'manager_emails': list(MANAGERS)}


@router.get('')
def list_payables(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    current_role = required(auth, 'admin', 'finance', 'manager')
    stmt = select(Payable).order_by(Payable.created_at.desc(), Payable.id.desc())
    if current_role == 'admin':
        stmt = stmt.where(Payable.origin == 'admin')
        # Admin can see all Admin Bills, including drafts.
    return [summary(obj) for obj in db.scalars(stmt.limit(300)).all()]


@router.get('/{payable_id}')
def get_payable(payable_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    return serialize(db, accessible(db, auth, payable_id))


@router.post('', status_code=201)
def create_payable(data: BillInput, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    current_role = required(auth, 'admin', 'finance')
    origin = 'admin' if current_role == 'admin' else 'finance'
    bill = Payable(code=f'TEMP-{uuid.uuid4().hex[:20]}', origin=origin,
        raised_by_id=auth.user.id, status='draft', paid_paise=0, approval_version=1)
    fill_fields(bill, data)
    db.add(bill)
    db.flush()
    bill.code = f'PAY-{utc_now():%Y}-{bill.id:06d}'
    audit(db, bill, auth, 'created', {'origin': origin, 'amount_paise': bill.total_paise})
    commit(db)
    return serialize(db, bill)


@router.put('/{payable_id}')
def edit_payable(payable_id: int, data: BillInput, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    current_role = required(auth, 'admin', 'finance')
    bill = accessible(db, auth, payable_id, lock=True)
    if current_role == 'admin' and (bill.origin != 'admin' or bill.raised_by_id != auth.user.id or bill.status not in ('draft', 'returned')):
        raise HTTPException(403, 'Admin can edit only their own drafts or returned bills')
    if bill.paid_paise > 0 or bill.status == 'paid_closed':
        raise HTTPException(409, 'Paid and partially paid bills are immutable; a separate controlled adjustment is required')
    previous = {'total_paise': bill.total_paise, 'status': bill.status, 'version': bill.approval_version}
    if bill.status != 'draft':
        bill.approval_version += 1  # previous approvals remain in historical version, never valid for new version
    fill_fields(bill, data)
    bill.status = 'draft'
    audit(db, bill, auth, 'edited_approvals_reset', {'before': previous, 'after_total_paise': bill.total_paise, 'version': bill.approval_version})
    commit(db)
    return serialize(db, bill)


@router.post('/{payable_id}/bill-document')
def upload_bill(payable_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    current_role = required(auth, 'admin', 'finance')
    bill = accessible(db, auth, payable_id, lock=True)
    if current_role == 'admin' and (bill.raised_by_id != auth.user.id or bill.status not in ('draft', 'returned')):
        raise HTTPException(403, 'Admin can upload documents only to their own drafts or returned bills')
    if bill.status not in ('draft', 'returned') or bill.paid_paise > 0:
        raise HTTPException(409, 'Bill attachments can be changed only before submitting a bill for approval')
    item = save_document(db, auth, bill, file, 'bill')
    db.flush()
    audit(db, bill, auth, 'bill_document_uploaded', {'document_id': item.id, 'sha256': item.sha256})
    commit(db)
    return {'document_id': item.id, 'filename': item.filename}


@router.post('/{payable_id}/submit')
def submit_payable(payable_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    current_role = required(auth, 'admin', 'finance')
    bill = accessible(db, auth, payable_id, lock=True)
    if current_role == 'admin' and bill.raised_by_id != auth.user.id:
        raise HTTPException(403, 'Only the creating Admin can submit this bill')
    if bill.status not in ('draft', 'returned'):
        raise HTTPException(409, 'Bill is already submitted or paid')
    if not db.scalar(select(PayableDocument.id).where(PayableDocument.payable_id == bill.id, PayableDocument.kind == 'bill')):
        raise HTTPException(409, 'Upload the original bill before submission')
    users = managers(db)
    bill.status = 'pending_approval'
    audit(db, bill, auth, 'submitted', {'version': bill.approval_version})
    notify(db, bill, 'submitted', f'{bill.bill_name} from {bill.vendor_name} (INR {bill.total_paise / 100:,.2f}) requires your approval.', [u.id for u in users])
    if bill.origin == 'admin':
        notify(db, bill, 'new_admin_bill', 'A new Admin Bill is awaiting both management approvals.', _finance_ids(db))
    commit(db)
    return serialize(db, bill)


@router.post('/{payable_id}/decision')
def manager_decision(payable_id: int, data: DecisionInput, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    required(auth, 'manager')
    email = str(auth.user.email).lower()
    bill = accessible(db, auth, payable_id, lock=True)
    if bill.status != 'pending_approval':
        raise HTTPException(409, 'This bill is not waiting for management approval')
    current = approvals_of(db, bill)
    if current[email]['decision'] != 'pending':
        raise HTTPException(409, 'You have already decided on this version of the bill')
    if data.decision == 'rejected' and not (data.comment or '').strip():
        raise HTTPException(400, 'A rejection reason is required')
    db.add(PayableApproval(payable_id=bill.id, approval_version=bill.approval_version,
        manager_email=email, manager_user_id=auth.user.id, decision=data.decision, comment=data.comment))
    audit(db, bill, auth, 'decision', {'decision': data.decision, 'version': bill.approval_version, 'comment': data.comment})
    if data.decision == 'rejected':
        bill.status = 'returned'
        recipients = [bill.raised_by_id, *_finance_ids(db)]
        notify(db, bill, 'returned', f'{email} returned {bill.bill_name} for correction: {data.comment}', recipients)
    elif all(current[m]['decision'] == 'approved' or m == email for m in MANAGERS):
        bill.status = 'approved'
        notify(db, bill, 'approved', f'Vinod and Chethan approved {bill.bill_name}; Finance can record payment.', _finance_ids(db))
    db.flush()
    commit(db)
    return serialize(db, bill)


@router.post('/{payable_id}/payments')
def record_payment(payable_id: int, amount: str = Form(...), payment_date: date = Form(...),
                   method: str = Form(...), reference: str = Form(...), proof: UploadFile = File(...),
                   db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    required(auth, 'finance')
    bill = accessible(db, auth, payable_id, lock=True)
    if bill.status not in ('approved', 'partially_paid'):
        raise HTTPException(409, 'Both current management approvals are required before payment')
    current = approvals_of(db, bill)
    if any(current[manager]['decision'] != 'approved' for manager in MANAGERS):
        raise HTTPException(409, 'Both Vinod and Chethan must approve this exact bill version')
    try:
        parsed = Decimal(amount)
        if not parsed.is_finite() or parsed.as_tuple().exponent < -2:
            raise ValueError()
        paise = money_to_paise(parsed)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, 'Enter a valid amount with at most 2 decimal places')
    if paise <= 0 or paise > bill.total_paise - bill.paid_paise:
        raise HTTPException(400, 'Payment must be positive and cannot exceed the outstanding amount')
    if payment_date > date.today():
        raise HTTPException(400, 'Payment date cannot be in the future')
    method = method.strip().lower()
    if method not in ('bank_transfer', 'upi', 'cheque', 'cash', 'other'):
        raise HTTPException(400, 'Unsupported payment method')
    reference = reference.strip()
    if len(reference) < 3 or len(reference) > 120:
        raise HTTPException(400, 'Enter a valid transaction reference')
    if db.scalar(select(PayablePayment.id).where(PayablePayment.payable_id == bill.id, PayablePayment.reference == reference)) is not None:
        raise HTTPException(409, 'This payment reference has already been recorded')
    payment = PayablePayment(payable_id=bill.id, amount_paise=paise, payment_date=payment_date,
        payment_method=method, reference=reference, recorded_by_id=auth.user.id)
    db.add(payment)
    db.flush()
    document = save_document(db, auth, bill, proof, 'challan', payment.id)
    db.flush()
    bill.paid_paise += paise
    bill.status = 'paid_closed' if bill.paid_paise == bill.total_paise else 'partially_paid'
    if bill.status == 'paid_closed':
        bill.closed_at = utc_now()
        recipient_ids = [user.id for user in managers(db)]
        if bill.origin == 'admin':
            # Only the Admin who raised the bill gets the closure alert; other admin users may still see admin bills.
            recipient_ids.append(bill.raised_by_id)
        notify(db, bill, 'paid_closed', f'{bill.bill_name} is fully paid (INR {bill.total_paise / 100:,.2f}). Download the challan in Payables.', recipient_ids)
    else:
        notify(db, bill, 'partial_payment', f'{bill.bill_name}: INR {bill.paid_paise / 100:,.2f} paid; INR {(bill.total_paise - bill.paid_paise) / 100:,.2f} outstanding.', [u.id for u in managers(db)] + ([bill.raised_by_id] if bill.origin == 'admin' else []))
    audit(db, bill, auth, 'payment', {'payment_id': payment.id, 'amount_paise': paise, 'reference': reference, 'proof_id': document.id, 'status': bill.status})
    commit(db)
    return serialize(db, bill)


@router.get('/{payable_id}/documents/{document_id}')
def download_document(payable_id: int, document_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    bill = accessible(db, auth, payable_id)
    document = db.scalar(select(PayableDocument).where(PayableDocument.id == document_id, PayableDocument.payable_id == bill.id))
    if document is None:
        raise HTTPException(404, 'Document not found')
    safe_name = ''.join(c if (c.isascii() and (c.isalnum() or c in '._-')) else '_' for c in document.filename) or 'document'
    return Response(content=document.content, media_type=document.media_type, headers={'Content-Disposition': f'attachment; filename="{safe_name}"', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})


@router.get('/{payable_id}/audit')
def audit_history(payable_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    accessible(db, auth, payable_id)  # exactly the same role/origin protection
    rows = db.scalars(select(PayableAudit).where(PayableAudit.payable_id == payable_id).order_by(PayableAudit.id.asc())).all()
    return [{'id': row.id, 'action': row.action, 'actor_id': row.actor_id, 'details': row.details, 'created_at': row.created_at.isoformat() if row.created_at else None} for row in rows]
