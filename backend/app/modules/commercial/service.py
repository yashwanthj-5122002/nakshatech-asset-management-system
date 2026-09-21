from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, object_session

from app.core.config import settings
from app.models.entities import User, utc_now
from app.modules.commercial.currencies import BASE_CURRENCY, MANAGEMENT_DISPLAY_CURRENCIES, list_currencies, normalize_currency
from app.modules.commercial.fx_service import (
    FX_MODE_AUTO,
    FX_MODE_BASE_CURRENCY,
    FX_MODE_MANUAL_OVERRIDE,
    OVERRIDE_MODES,
    FxQuote,
    FxUnavailableError,
    convert_to_inr,
    get_fx_service,
    money,
    quantize_rate,
)
from app.modules.commercial.models import (
    ProjectBillingBasis,
    ProjectCommercialAttachment,
    ProjectCommercialEstimateRevision,
    ProjectCommercialMilestone,
    ProjectExpense,
    ProjectExpenseDeclaration,
    ProjectExpenseEvent,
    ProjectFxOverride,
    ProjectFxSnapshot,
    ProjectVendorInvoice,
    ProjectVendorPayment,
)
from app.modules.commercial.schemas import (
    BILLING_TYPES,
    QUANTITY_BILLING_TYPES,
    UNIT_RATE_BILLING_TYPES,
    BillingBasisInput,
    CommercialEstimateDecision,
    CommercialEstimateInput,
    ProjectExpenseDecision,
    ProjectExpenseDeclarationInput,
    ProjectExpenseInput,
    ProjectExpenseReimbursement,
    VendorInvoiceInput,
    VendorPaymentInput,
)
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectAssignment
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import OrthoWorkPackage, ProjectWorkflow, ProjectWorkflowEvent


EXPENSE_EDITABLE = {"DRAFT", "RETURNED"}
EXPENSE_OPEN = {"DRAFT", "SUBMITTED", "RETURNED", "APPROVED"}
EXPENSE_FINANCE_QUEUE = {"SUBMITTED"}
EXPENSE_FINAL = {"REJECTED", "REIMBURSED"}


def _project(db: Session, project_id: int) -> FinanceProject:
    row = db.get(FinanceProject, project_id)
    if row is None:
        raise ValueError("Project not found")
    return row


def _workflow(db: Session, project_id: int) -> ProjectWorkflow | None:
    return db.get(ProjectWorkflow, project_id)


def _estimate(db: Session, revision_id: int) -> ProjectCommercialEstimateRevision:
    row = db.get(ProjectCommercialEstimateRevision, revision_id)
    if row is None:
        raise ValueError("Commercial estimate revision not found")
    return row


def _expense(db: Session, expense_id: int) -> ProjectExpense:
    row = db.get(ProjectExpense, expense_id)
    if row is None:
        raise ValueError("Project expense not found")
    return row


def _vendor_invoice(db: Session, invoice_id: int) -> ProjectVendorInvoice:
    row = db.get(ProjectVendorInvoice, invoice_id)
    if row is None:
        raise ValueError("Vendor invoice not found")
    return row


def _manual_quote(currency: str, rate: Decimal, rate_date: date, mode: str, source: str = "MANUAL") -> FxQuote:
    return FxQuote(currency, BASE_CURRENCY, quantize_rate(rate), rate_date, None, source, mode)


def resolve_fx_quote(
    *,
    currency_code: str,
    event_date: date,
    manual_rate: Decimal | None = None,
    manual_mode: str | None = None,
    manual_reason: str | None = None,
) -> tuple[FxQuote, Decimal | None, str | None]:
    currency = normalize_currency(currency_code)
    if currency == BASE_CURRENCY:
        return get_fx_service().get_rate(BASE_CURRENCY, BASE_CURRENCY, event_date), None, None
    if manual_rate is None:
        return get_fx_service().get_rate(currency, BASE_CURRENCY, event_date), None, None

    mode = (manual_mode or FX_MODE_MANUAL_OVERRIDE).strip().upper()
    if mode not in OVERRIDE_MODES:
        raise ValueError("Manual FX rate requires an allowed override mode")
    reason = (manual_reason or "").strip()
    if not reason:
        raise ValueError("Reason is mandatory for a manual FX rate")
    reference_rate: Decimal | None = None
    try:
        reference_rate = get_fx_service().get_rate(currency, BASE_CURRENCY, event_date).rate
    except FxUnavailableError:
        # Explicitly permitted: provider outage must not force a fabricated rate. The manual rate
        # remains auditable and reference_rate stays NULL.
        reference_rate = None
    return _manual_quote(currency, manual_rate, event_date, mode, source="MANUAL_OVERRIDE"), reference_rate, reason


def create_fx_snapshot(
    db: Session,
    *,
    project_id: int,
    event_type: str,
    original_amount: Decimal,
    currency_code: str,
    event_date: date,
    actor: User,
    manual_rate: Decimal | None = None,
    manual_mode: str | None = None,
    manual_reason: str | None = None,
    locked: bool = False,
) -> ProjectFxSnapshot:
    quote, reference_rate, reason = resolve_fx_quote(
        currency_code=currency_code,
        event_date=event_date,
        manual_rate=manual_rate,
        manual_mode=manual_mode,
        manual_reason=manual_reason,
    )
    snapshot = ProjectFxSnapshot(
        project_id=project_id,
        event_type=event_type,
        event_ref_id=None,
        currency_code=quote.from_currency,
        original_amount=money(original_amount),
        fx_rate_to_inr=quote.rate,
        fx_rate_date=quote.rate_date,
        fx_rate_timestamp=quote.timestamp,
        fx_rate_source=quote.source,
        fx_rate_mode=quote.mode,
        reference_rate=reference_rate,
        inr_equivalent=convert_to_inr(original_amount, quote.rate),
        fx_locked=locked,
        override_reason=reason,
        entered_by_id=actor.id,
    )
    db.add(snapshot)
    db.flush()
    if manual_rate is not None and quote.from_currency != BASE_CURRENCY:
        db.add(ProjectFxOverride(
            snapshot_id=snapshot.id,
            project_id=project_id,
            old_rate=reference_rate,
            new_rate=quote.rate,
            old_mode=FX_MODE_AUTO if reference_rate is not None else None,
            new_mode=quote.mode,
            reason=reason or "Manual rate",
            rate_date=quote.rate_date,
            actor_id=actor.id,
        ))
        db.flush()
    return snapshot


def fx_preview(*, amount: Decimal, currency_code: str, event_date: date, manual_rate=None, manual_mode=None, manual_reason=None) -> dict:
    quote, reference_rate, reason = resolve_fx_quote(
        currency_code=currency_code,
        event_date=event_date,
        manual_rate=manual_rate,
        manual_mode=manual_mode,
        manual_reason=manual_reason,
    )
    return {
        "currency_code": quote.from_currency,
        "amount": float(money(amount)),
        "fx_rate_to_inr": float(quote.rate),
        "fx_rate_date": quote.rate_date.isoformat(),
        "fx_rate_timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
        "fx_rate_source": quote.source,
        "fx_rate_mode": quote.mode,
        "reference_rate": float(reference_rate) if reference_rate is not None else None,
        "override_reason": reason,
        "inr_equivalent": float(convert_to_inr(amount, quote.rate)),
    }


def currencies_payload() -> dict:
    return {
        "base_currency": BASE_CURRENCY,
        "management_display_currencies": MANAGEMENT_DISPLAY_CURRENCIES,
        "currencies": list_currencies(),
    }


def _milestone_rows(db: Session, revision_id: int) -> list[ProjectCommercialMilestone]:
    return list(db.scalars(select(ProjectCommercialMilestone).where(
        ProjectCommercialMilestone.revision_id == revision_id
    ).order_by(ProjectCommercialMilestone.sequence)).all())


def _milestone_payloads(row: ProjectCommercialEstimateRevision) -> list[dict]:
    session = object_session(row)
    if session is None or row.id is None:
        return []
    return [
        {
            "id": item.id,
            "sequence": item.sequence,
            "milestone_name": item.milestone_name,
            "percent": float(item.percent) if item.percent is not None else None,
            "amount": float(item.amount) if item.amount is not None else None,
        }
        for item in _milestone_rows(session, row.id)
    ]


def _replace_milestones(db: Session, row: ProjectCommercialEstimateRevision, payload: CommercialEstimateInput, base: Decimal) -> None:
    """Milestone schedule belongs to one revision; it is rewritten only while that revision is still editable."""
    for old in _milestone_rows(db, row.id):
        db.delete(old)
    db.flush()
    if row.billing_type != "milestone":
        return
    for index, item in enumerate(payload.milestones, start=1):
        amount = money(item.amount) if item.amount is not None else money(base * Decimal(item.percent) / Decimal("100"))
        percent = item.percent if item.percent is not None else (money(amount / base * Decimal("100")) if base else None)
        db.add(ProjectCommercialMilestone(
            revision_id=row.id, project_id=row.project_id, sequence=index,
            milestone_name=item.milestone_name, percent=percent, amount=amount,
        ))
    db.flush()


def _status_key(workflow: ProjectWorkflow | None) -> str:
    return (workflow.status or "").strip().lower() if workflow is not None else ""


# Project states in which Revision 1 travels with the project's own Finance approval cycle.
PROJECT_APPROVAL_STATES = {"draft", "pending_finance_approval", "finance_returned"}


def _workflow_event(db: Session, *, workflow: ProjectWorkflow | None, actor: User, event_type: str, comments: str | None) -> None:
    """Put commercial Revision 1 milestones into the same audit stream Finance already reads on the project review."""
    if workflow is None:
        return
    db.add(ProjectWorkflowEvent(
        project_id=workflow.project_id,
        event_type=event_type,
        from_status=workflow.status,
        to_status=workflow.status,
        comments=comments,
        actor_user_id=actor.id,
    ))


def _tax_values(payload: CommercialEstimateInput) -> tuple[Decimal, Decimal, Decimal]:
    base = money(payload.taxable_base_amount if payload.taxable_base_amount is not None else payload.estimated_amount)
    tax = money(base * Decimal(payload.tax_percent) / Decimal("100"))
    gross = money(base + tax)
    return base, tax, gross


def _estimate_payload(row: ProjectCommercialEstimateRevision) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "revision_no": row.revision_no,
        "is_baseline": row.is_baseline,
        "status": row.status,
        "is_locked": row.is_locked,
        "quotation_reference": row.quotation_reference,
        "po_wo_reference": row.po_wo_reference,
        "scope_description": row.scope_description,
        "billing_type": row.billing_type,
        "payment_terms": row.payment_terms,
        "expected_billing_milestone": row.expected_billing_milestone,
        "notes": row.notes,
        "currency_code": row.currency_code,
        "estimated_amount": float(row.estimated_amount),
        "taxable_base_amount": float(row.taxable_base_amount),
        "tax_percent": float(row.tax_percent),
        "expected_tax": float(row.expected_tax),
        "expected_gross": float(row.expected_gross),
        "estimated_direct_cost_inr": float(row.estimated_direct_cost_inr) if row.estimated_direct_cost_inr is not None else None,
        "billing_type_label": BILLING_TYPES.get(row.billing_type, row.billing_type),
        "unit_rate": float(row.unit_rate) if row.unit_rate is not None else None,
        "estimated_quantity": float(row.estimated_quantity) if row.estimated_quantity is not None else None,
        "quantity_unit": row.quantity_unit,
        "milestones": _milestone_payloads(row),
        "fx_snapshot_id": row.fx_snapshot_id,
        "fx_rate_to_inr": float(row.fx_rate_to_inr),
        "fx_rate_date": row.fx_rate_date.isoformat(),
        "fx_rate_source": row.fx_rate_source,
        "fx_rate_mode": row.fx_rate_mode,
        "estimated_inr": float(row.estimated_inr),
        "base_inr": float(row.base_inr),
        "tax_inr": float(row.tax_inr),
        "gross_inr": float(row.gross_inr),
        "estimate_date": row.estimate_date.isoformat(),
        "reason": row.reason,
        "previous_currency_code": row.previous_currency_code,
        "previous_amount": float(row.previous_amount) if row.previous_amount is not None else None,
        "previous_base_inr": float(row.previous_base_inr) if row.previous_base_inr is not None else None,
        "created_by_id": row.created_by_id,
        "created_at": row.created_at.isoformat(),
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "approved_by_id": row.approved_by_id,
        "approved_at": row.approved_at.isoformat() if row.approved_at else None,
        "decision_comments": row.decision_comments,
    }


def list_estimates(db: Session, *, project_id: int) -> list[dict]:
    _project(db, project_id)
    rows = list(db.scalars(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id
    ).order_by(ProjectCommercialEstimateRevision.revision_no.desc())).all())
    return [_estimate_payload(row) for row in rows]


def list_estimate_queue(db: Session, *, statuses: tuple[str, ...] = ("PENDING_APPROVAL",)) -> list[dict]:
    rows = list(db.scalars(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.status.in_(statuses)
    ).order_by(ProjectCommercialEstimateRevision.submitted_at.asc(), ProjectCommercialEstimateRevision.id.asc())).all())
    # Revision 1 of a project that is still inside its own BD -> Finance approval cycle is decided together with
    # the project (Finance project review), so it must not appear as an independent revision to approve.
    rows = [
        row for row in rows
        if not (row.revision_no == 1 and _status_key(_workflow(db, row.project_id)) in PROJECT_APPROVAL_STATES)
    ]
    return [_estimate_payload(row) for row in rows]


def current_approved_estimate(db: Session, project_id: int) -> ProjectCommercialEstimateRevision | None:
    return db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.status == "APPROVED",
    ).order_by(ProjectCommercialEstimateRevision.revision_no.desc()).limit(1))


def upsert_baseline_estimate(db: Session, *, actor: User, project_id: int, payload: CommercialEstimateInput) -> ProjectCommercialEstimateRevision:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    if workflow is not None and workflow.bd_owner_user_id != actor.id and (actor.role or "").lower() not in {"admin", "management", "software_team"}:
        raise PermissionError("Only the BD owner can maintain the initial commercial estimate")
    row = db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))
    if row is not None and (row.is_locked or row.status == "APPROVED"):
        raise ValueError("The Finance-approved baseline is locked; create a new revision instead")
    if row is not None and row.status == "PENDING_APPROVAL" and _status_key(workflow) == "pending_finance_approval":
        # Revision 1 exists and is under Finance review together with the project. A project that has no
        # Revision 1 yet (submitted before the commercial layer) may still receive one.
        raise ValueError("The project is under Finance review; commercial details can be edited again only if Finance returns it")

    base, tax, gross = _tax_values(payload)
    snapshot = create_fx_snapshot(
        db,
        project_id=project_id,
        event_type="ESTIMATE_BASELINE",
        original_amount=payload.estimated_amount,
        currency_code=payload.currency_code,
        event_date=payload.estimate_date,
        actor=actor,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
        locked=False,
    )
    if row is None:
        row = ProjectCommercialEstimateRevision(
            project_id=project.id,
            revision_no=1,
            is_baseline=True,
            status="DRAFT",
            is_locked=False,
            scope_description=payload.scope_description,
            billing_type=payload.billing_type,
            currency_code=payload.currency_code,
            estimated_amount=money(payload.estimated_amount),
            taxable_base_amount=base,
            tax_percent=payload.tax_percent,
            expected_tax=tax,
            expected_gross=gross,
            fx_rate_to_inr=snapshot.fx_rate_to_inr,
            fx_rate_date=snapshot.fx_rate_date,
            fx_rate_source=snapshot.fx_rate_source,
            fx_rate_mode=snapshot.fx_rate_mode,
            estimated_inr=convert_to_inr(payload.estimated_amount, snapshot.fx_rate_to_inr),
            base_inr=convert_to_inr(base, snapshot.fx_rate_to_inr),
            tax_inr=convert_to_inr(tax, snapshot.fx_rate_to_inr),
            gross_inr=convert_to_inr(gross, snapshot.fx_rate_to_inr),
            estimate_date=payload.estimate_date,
            created_by_id=actor.id,
        )
        db.add(row)
    else:
        row.previous_currency_code = row.currency_code
        row.previous_amount = row.estimated_amount
        row.previous_base_inr = row.base_inr
        row.status = "DRAFT"
        row.submitted_at = None
        row.decision_comments = None
        row.currency_code = payload.currency_code
        row.estimated_amount = money(payload.estimated_amount)
        row.taxable_base_amount = base
        row.tax_percent = payload.tax_percent
        row.expected_tax = tax
        row.expected_gross = gross
        row.fx_rate_to_inr = snapshot.fx_rate_to_inr
        row.fx_rate_date = snapshot.fx_rate_date
        row.fx_rate_source = snapshot.fx_rate_source
        row.fx_rate_mode = snapshot.fx_rate_mode
        row.estimated_inr = convert_to_inr(payload.estimated_amount, snapshot.fx_rate_to_inr)
        row.base_inr = convert_to_inr(base, snapshot.fx_rate_to_inr)
        row.tax_inr = convert_to_inr(tax, snapshot.fx_rate_to_inr)
        row.gross_inr = convert_to_inr(gross, snapshot.fx_rate_to_inr)
        row.estimate_date = payload.estimate_date
    row.quotation_reference = payload.quotation_reference
    row.po_wo_reference = payload.po_wo_reference
    row.scope_description = payload.scope_description
    row.billing_type = payload.billing_type
    row.payment_terms = payload.payment_terms
    row.expected_billing_milestone = payload.expected_billing_milestone
    row.notes = payload.notes
    row.estimated_direct_cost_inr = money(payload.estimated_direct_cost_inr) if payload.estimated_direct_cost_inr is not None else None
    row.unit_rate = payload.unit_rate
    row.estimated_quantity = payload.estimated_quantity
    row.quantity_unit = payload.quantity_unit
    row.reason = payload.reason
    row.fx_snapshot_id = snapshot.id
    db.flush()
    snapshot.event_ref_id = row.id
    _replace_milestones(db, row, payload, base)
    _workflow_event(db, workflow=workflow, actor=actor, event_type="commercial_revision1_saved",
                    comments=f"Revision 1: {row.currency_code} {row.estimated_amount} ({BILLING_TYPES.get(row.billing_type, row.billing_type)})")

    # Keep the old V8 workflow summary fields synchronized while the detailed estimate is still editable.
    if workflow is not None:
        workflow.commercial_value = row.estimated_amount
        workflow.currency = row.currency_code
        workflow.po_wo_number = row.po_wo_reference
        workflow.updated_by_id = actor.id
        workflow.updated_at = utc_now()
    db.flush()
    return row


def submit_baseline_estimate(db: Session, *, actor: User, project_id: int) -> ProjectCommercialEstimateRevision:
    row = db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))
    if row is None:
        raise ValueError("Create the commercial estimate before submitting it")
    if row.is_locked or row.status == "APPROVED":
        raise ValueError("The baseline estimate is already Finance-approved and locked")
    workflow = _workflow(db, project_id)
    if workflow is not None and workflow.bd_owner_user_id != actor.id and (actor.role or "").lower() not in {"admin", "management", "software_team"}:
        raise PermissionError("Only the BD owner can submit the commercial estimate")
    row.status = "PENDING_APPROVAL"
    row.submitted_at = utc_now()
    db.flush()
    return row


def freeze_baseline_on_finance_approval(db: Session, *, actor: User, project_id: int) -> ProjectCommercialEstimateRevision | None:
    row = db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))
    if row is None:
        if settings.commercial_estimate_required_on_submit:
            raise ValueError("A commercial estimate is required before Finance can approve the project")
        return None
    if row.status not in {"DRAFT", "PENDING_APPROVAL", "RETURNED"}:
        if row.status == "APPROVED":
            return row
        raise ValueError("Commercial estimate is not in an approvable state")
    row.status = "APPROVED"
    row.is_baseline = True
    row.is_locked = True
    row.approved_by_id = actor.id
    row.approved_at = utc_now()
    row.decision_comments = "Approved with project Finance approval"
    if row.fx_snapshot_id:
        snap = db.get(ProjectFxSnapshot, row.fx_snapshot_id)
        if snap:
            snap.fx_locked = True
            snap.verified_by_id = actor.id
            snap.verified_at = utc_now()
    _workflow_event(db, workflow=_workflow(db, project_id), actor=actor, event_type="commercial_revision1_approved_baseline",
                    comments=f"Revision 1 locked as approved baseline: {row.currency_code} {row.estimated_amount}")
    db.flush()
    return row


def prepare_revision1_for_finance_submission(db: Session, *, actor: User, project_id: int) -> ProjectCommercialEstimateRevision | None:
    """Submit Commercial Revision 1 together with the project (called inside the BD -> Finance submission).

    * A project that has never been submitted needs Revision 1 (unless the requirement flag is switched off).
    * A project submitted before the commercial layer existed (already returned once) may still be resubmitted
      without one, so legacy projects are never stranded.
    """
    workflow = _workflow(db, project_id)
    row = db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))
    first_submission = workflow is None or int(workflow.submission_count or 0) == 0
    if row is None:
        if first_submission and settings.commercial_revision1_required_on_submit:
            raise ValueError(
                "Commercial & Billing Details (Revision 1) are required before a new project can be submitted to Finance"
            )
        return None
    if row.is_locked or row.status == "APPROVED":
        return row
    row.status = "PENDING_APPROVAL"
    row.submitted_at = utc_now()
    row.decision_comments = None
    _workflow_event(db, workflow=workflow, actor=actor, event_type="commercial_revision1_submitted",
                    comments=f"Revision 1 submitted with the project: {row.currency_code} {row.estimated_amount}")
    db.flush()
    return row


def mark_revision1_returned(db: Session, *, actor: User, project_id: int, feedback: str) -> ProjectCommercialEstimateRevision | None:
    """Finance returned the project: Revision 1 (same row, same identity) goes back to BD for correction."""
    row = db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))
    if row is None or row.is_locked or row.status == "APPROVED":
        return row
    row.status = "RETURNED"
    row.decision_comments = feedback
    _workflow_event(db, workflow=_workflow(db, project_id), actor=actor, event_type="commercial_revision1_returned",
                    comments="Revision 1 returned to BD with the project: " + feedback)
    db.flush()
    return row


def create_estimate_revision(db: Session, *, actor: User, project_id: int, payload: CommercialEstimateInput) -> ProjectCommercialEstimateRevision:
    baseline = current_approved_estimate(db, project_id)
    if baseline is None:
        raise ValueError("Finance-approved baseline estimate is required before creating a revision")
    latest_no = int(db.scalar(select(func.coalesce(func.max(ProjectCommercialEstimateRevision.revision_no), 0)).where(
        ProjectCommercialEstimateRevision.project_id == project_id
    )) or 0)
    base, tax, gross = _tax_values(payload)
    snapshot = create_fx_snapshot(
        db,
        project_id=project_id,
        event_type="ESTIMATE_REVISION",
        original_amount=payload.estimated_amount,
        currency_code=payload.currency_code,
        event_date=payload.estimate_date,
        actor=actor,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
        locked=False,
    )
    row = ProjectCommercialEstimateRevision(
        project_id=project_id,
        revision_no=latest_no + 1,
        is_baseline=False,
        status="PENDING_APPROVAL",
        is_locked=False,
        quotation_reference=payload.quotation_reference,
        po_wo_reference=payload.po_wo_reference,
        scope_description=payload.scope_description,
        billing_type=payload.billing_type,
        payment_terms=payload.payment_terms,
        expected_billing_milestone=payload.expected_billing_milestone,
        notes=payload.notes,
        currency_code=payload.currency_code,
        estimated_amount=money(payload.estimated_amount),
        taxable_base_amount=base,
        tax_percent=payload.tax_percent,
        expected_tax=tax,
        expected_gross=gross,
        estimated_direct_cost_inr=money(payload.estimated_direct_cost_inr) if payload.estimated_direct_cost_inr is not None else None,
        unit_rate=payload.unit_rate,
        estimated_quantity=payload.estimated_quantity,
        quantity_unit=payload.quantity_unit,
        fx_snapshot_id=snapshot.id,
        fx_rate_to_inr=snapshot.fx_rate_to_inr,
        fx_rate_date=snapshot.fx_rate_date,
        fx_rate_source=snapshot.fx_rate_source,
        fx_rate_mode=snapshot.fx_rate_mode,
        estimated_inr=convert_to_inr(payload.estimated_amount, snapshot.fx_rate_to_inr),
        base_inr=convert_to_inr(base, snapshot.fx_rate_to_inr),
        tax_inr=convert_to_inr(tax, snapshot.fx_rate_to_inr),
        gross_inr=convert_to_inr(gross, snapshot.fx_rate_to_inr),
        estimate_date=payload.estimate_date,
        reason=payload.reason,
        previous_currency_code=baseline.currency_code,
        previous_amount=baseline.estimated_amount,
        previous_base_inr=baseline.base_inr,
        created_by_id=actor.id,
        submitted_at=utc_now(),
    )
    db.add(row)
    db.flush()
    snapshot.event_ref_id = row.id
    _replace_milestones(db, row, payload, base)
    return row


def decide_estimate_revision(db: Session, *, actor: User, revision_id: int, payload: CommercialEstimateDecision) -> ProjectCommercialEstimateRevision:
    row = _estimate(db, revision_id)
    if row.status not in {"PENDING_APPROVAL", "RETURNED"}:
        raise ValueError("Only a pending/returned estimate revision can receive a Finance decision")
    if row.revision_no == 1 and _status_key(_workflow(db, row.project_id)) in PROJECT_APPROVAL_STATES:
        raise ValueError("Revision 1 is approved together with the project: use the Finance project review to approve or return it")
    if payload.decision == "approve":
        row.status = "APPROVED"
        row.is_locked = True
        row.approved_by_id = actor.id
        row.approved_at = utc_now()
        if row.fx_snapshot_id:
            snap = db.get(ProjectFxSnapshot, row.fx_snapshot_id)
            if snap:
                snap.fx_locked = True
                snap.verified_by_id = actor.id
                snap.verified_at = utc_now()
        workflow = _workflow(db, row.project_id)
        if workflow is not None:
            workflow.commercial_value = row.estimated_amount
            workflow.currency = row.currency_code
            workflow.po_wo_number = row.po_wo_reference
            workflow.updated_by_id = actor.id
            workflow.updated_at = utc_now()
    elif payload.decision == "return":
        row.status = "RETURNED"
        row.is_locked = False
    else:
        row.status = "REJECTED"
        row.is_locked = True
    row.decision_comments = payload.comments
    db.flush()
    return row


def _employee_has_project_access(db: Session, *, project_id: int, employee_id: int) -> bool:
    return db.scalar(select(FinanceProjectAssignment.id).where(
        FinanceProjectAssignment.project_id == project_id,
        FinanceProjectAssignment.user_id == employee_id,
        FinanceProjectAssignment.is_active.is_(True),
    ).limit(1)) is not None


def assert_employee_project_access(db: Session, *, project_id: int, actor: User) -> None:
    _project(db, project_id)
    if (actor.role or "").lower() in {"admin", "management", "finance", "bd", "software_team"}:
        return
    if not _employee_has_project_access(db, project_id=project_id, employee_id=actor.id):
        raise PermissionError("You are not assigned to this project")


def _expense_payload(row: ProjectExpense) -> dict:
    return {
        "id": row.id,
        "expense_code": row.expense_code,
        "project_id": row.project_id,
        "employee_id": row.employee_id,
        "expense_date": row.expense_date.isoformat(),
        "category": row.category,
        "purpose": row.purpose,
        "amount": float(row.amount),
        "approved_amount": float(row.approved_amount) if row.approved_amount is not None else None,
        "currency": "INR",
        "payment_source": row.payment_source,
        "status": row.status,
        "remarks": row.remarks,
        "phase_key": row.phase_key,
        "linked_vendor_invoice_id": row.linked_vendor_invoice_id,
        "finance_reviewer_id": row.finance_reviewer_id,
        "finance_reviewed_at": row.finance_reviewed_at.isoformat() if row.finance_reviewed_at else None,
        "finance_comments": row.finance_comments,
        "adjustment_reason": row.adjustment_reason,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "reimbursed_at": row.reimbursed_at.isoformat() if row.reimbursed_at else None,
        "reimbursement_reference": row.reimbursement_reference,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def create_project_expense(db: Session, *, actor: User, project_id: int, payload: ProjectExpenseInput) -> ProjectExpense:
    assert_employee_project_access(db, project_id=project_id, actor=actor)
    if payload.linked_vendor_invoice_id is not None:
        invoice = _vendor_invoice(db, payload.linked_vendor_invoice_id)
        if invoice.project_id != project_id:
            raise ValueError("Linked vendor invoice belongs to a different project")
    row = ProjectExpense(
        expense_code=f"PEXP-{date.today():%Y%m%d}-{uuid4().hex[:10].upper()}",
        project_id=project_id,
        employee_id=actor.id,
        expense_date=payload.expense_date,
        category=payload.category,
        purpose=payload.purpose,
        amount=money(payload.amount),
        approved_amount=None,
        payment_source=payload.payment_source,
        status="DRAFT",
        remarks=payload.remarks,
        phase_key=payload.phase_key.upper(),
        linked_vendor_invoice_id=payload.linked_vendor_invoice_id,
    )
    db.add(row)
    db.flush()
    declaration = db.scalar(select(ProjectExpenseDeclaration).where(
        ProjectExpenseDeclaration.project_id == project_id,
        ProjectExpenseDeclaration.employee_id == actor.id,
        ProjectExpenseDeclaration.phase_key == row.phase_key,
    ))
    if declaration is not None and declaration.declaration_status == "NO_MORE_EXPENSES":
        declaration.declaration_status = "HAS_EXPENSES"
        declaration.declared_at = utc_now()
    db.add(ProjectExpenseEvent(expense_id=row.id, action="CREATED", from_status=None, to_status="DRAFT", actor_id=actor.id, new_amount=row.amount))
    db.flush()
    return row


def update_project_expense(db: Session, *, actor: User, expense_id: int, payload: ProjectExpenseInput) -> ProjectExpense:
    row = _expense(db, expense_id)
    if row.employee_id != actor.id and (actor.role or "").lower() not in {"admin", "software_team"}:
        raise PermissionError("Only the employee who created the expense can edit it")
    if row.status not in EXPENSE_EDITABLE:
        raise ValueError("Expense can be edited only while Draft or Returned")
    old_status = row.status
    old_amount = row.amount
    if payload.linked_vendor_invoice_id is not None:
        invoice = _vendor_invoice(db, payload.linked_vendor_invoice_id)
        if invoice.project_id != row.project_id:
            raise ValueError("Linked vendor invoice belongs to a different project")
    row.expense_date = payload.expense_date
    row.category = payload.category
    row.purpose = payload.purpose
    row.amount = money(payload.amount)
    row.payment_source = payload.payment_source
    row.remarks = payload.remarks
    row.phase_key = payload.phase_key.upper()
    row.linked_vendor_invoice_id = payload.linked_vendor_invoice_id
    row.status = "DRAFT"
    row.finance_comments = None
    row.finance_reviewer_id = None
    row.finance_reviewed_at = None
    row.adjustment_reason = None
    db.add(ProjectExpenseEvent(expense_id=row.id, action="UPDATED", from_status=old_status, to_status="DRAFT", actor_id=actor.id, old_amount=old_amount, new_amount=row.amount))
    db.flush()
    return row


def submit_project_expense(db: Session, *, actor: User, expense_id: int) -> ProjectExpense:
    row = _expense(db, expense_id)
    if row.employee_id != actor.id:
        raise PermissionError("Only the employee who created the expense can submit it")
    if row.status not in EXPENSE_EDITABLE:
        raise ValueError("Only Draft or Returned expenses can be submitted")
    old = row.status
    row.status = "SUBMITTED"
    row.submitted_at = utc_now()
    db.add(ProjectExpenseEvent(expense_id=row.id, action="SUBMITTED", from_status=old, to_status=row.status, actor_id=actor.id, old_amount=row.amount, new_amount=row.amount))
    db.flush()
    return row


def decide_project_expense(db: Session, *, actor: User, expense_id: int, payload: ProjectExpenseDecision) -> ProjectExpense:
    row = _expense(db, expense_id)
    if row.status != "SUBMITTED":
        raise ValueError("Only a Submitted project expense can receive a Finance decision")
    old = row.status
    row.finance_reviewer_id = actor.id
    row.finance_reviewed_at = utc_now()
    row.finance_comments = payload.comments
    row.adjustment_reason = payload.adjustment_reason
    if payload.decision == "approve":
        approved = money(payload.approved_amount)
        if approved > row.amount:
            raise ValueError("Approved amount cannot exceed the employee's claimed amount")
        if approved != row.amount and not payload.adjustment_reason:
            raise ValueError("Adjustment reason is required when Finance changes the approved amount")
        row.approved_amount = approved
        row.status = "APPROVED"
    elif payload.decision == "return":
        row.approved_amount = None
        row.status = "RETURNED"
    else:
        row.approved_amount = Decimal("0.00")
        row.status = "REJECTED"
    db.add(ProjectExpenseEvent(
        expense_id=row.id,
        action=f"FINANCE_{payload.decision.upper()}",
        from_status=old,
        to_status=row.status,
        actor_id=actor.id,
        old_amount=row.amount,
        new_amount=row.approved_amount,
        comments=payload.comments,
    ))
    db.flush()
    return row


def reimburse_project_expense(db: Session, *, actor: User, expense_id: int, payload: ProjectExpenseReimbursement) -> ProjectExpense:
    row = _expense(db, expense_id)
    if row.status != "APPROVED":
        raise ValueError("Only a Finance-approved expense can be marked reimbursed")
    row.status = "REIMBURSED"
    row.reimbursed_at = utc_now()
    row.reimbursement_reference = payload.reimbursement_reference
    db.add(ProjectExpenseEvent(
        expense_id=row.id,
        action="REIMBURSED",
        from_status="APPROVED",
        to_status="REIMBURSED",
        actor_id=actor.id,
        old_amount=row.approved_amount,
        new_amount=row.approved_amount,
        comments=payload.comments,
    ))
    db.flush()
    return row


def list_project_expenses(db: Session, *, actor: User, role: str, project_id: int | None = None, status: str | None = None) -> list[dict]:
    query = select(ProjectExpense)
    normalized_role = (role or "").lower()
    if normalized_role not in {"finance", "admin", "management", "bd"}:
        query = query.where(ProjectExpense.employee_id == actor.id)
    if project_id is not None:
        if normalized_role not in {"finance", "admin", "management", "bd"}:
            assert_employee_project_access(db, project_id=project_id, actor=actor)
        query = query.where(ProjectExpense.project_id == project_id)
    if status:
        query = query.where(ProjectExpense.status == status.strip().upper())
    rows = list(db.scalars(query.order_by(ProjectExpense.expense_date.desc(), ProjectExpense.id.desc())).all())
    return [_expense_payload(row) for row in rows]


def declare_project_expenses(db: Session, *, actor: User, project_id: int, payload: ProjectExpenseDeclarationInput) -> ProjectExpenseDeclaration:
    assert_employee_project_access(db, project_id=project_id, actor=actor)
    phase = payload.phase_key.upper()
    if payload.declaration_status == "NO_MORE_EXPENSES":
        unresolved = int(db.scalar(select(func.count(ProjectExpense.id)).where(
            ProjectExpense.project_id == project_id,
            ProjectExpense.employee_id == actor.id,
            ProjectExpense.phase_key == phase,
            ProjectExpense.status.in_(["DRAFT", "RETURNED"]),
        )) or 0)
        if unresolved:
            raise ValueError("Submit or resolve all Draft/Returned project expenses before declaring no more expenses")
    row = db.scalar(select(ProjectExpenseDeclaration).where(
        ProjectExpenseDeclaration.project_id == project_id,
        ProjectExpenseDeclaration.employee_id == actor.id,
        ProjectExpenseDeclaration.phase_key == phase,
    ))
    if row is None:
        row = ProjectExpenseDeclaration(
            project_id=project_id,
            employee_id=actor.id,
            phase_key=phase,
            declaration_status=payload.declaration_status,
            declared_at=utc_now(),
        )
        db.add(row)
    else:
        row.declaration_status = payload.declaration_status
        row.declared_at = utc_now()
    db.flush()
    return row


def _vendor_invoice_payload(db: Session, row: ProjectVendorInvoice) -> dict:
    paid = Decimal(db.scalar(select(func.coalesce(func.sum(ProjectVendorPayment.amount), 0)).where(
        ProjectVendorPayment.vendor_invoice_id == row.id
    )) or 0)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "vendor_name": row.vendor_name,
        "vendor_gstin": row.vendor_gstin,
        "invoice_number": row.invoice_number,
        "invoice_date": row.invoice_date.isoformat(),
        "due_date": row.due_date.isoformat() if row.due_date else None,
        "po_wo_reference": row.po_wo_reference,
        "category": row.category,
        "description": row.description,
        "hsn_sac": row.hsn_sac,
        "quantity": float(row.quantity) if row.quantity is not None else None,
        "rate": float(row.rate) if row.rate is not None else None,
        "currency_code": row.currency_code,
        "taxable_amount": float(row.taxable_amount),
        "cgst": float(row.cgst),
        "sgst": float(row.sgst),
        "igst": float(row.igst),
        "other_tax": float(row.other_tax),
        "gross_amount": float(row.gross_amount),
        "fx_rate_to_inr": float(row.fx_rate_to_inr),
        "fx_rate_date": row.fx_rate_date.isoformat() if row.fx_rate_date else None,
        "fx_rate_source": row.fx_rate_source,
        "fx_rate_mode": row.fx_rate_mode,
        "taxable_inr": float(row.taxable_inr),
        "tax_inr": float(row.tax_inr),
        "gross_inr": float(row.gross_inr),
        "paid_amount": float(paid),
        "outstanding_amount": float(max(Decimal("0"), Decimal(row.gross_amount) - paid)),
        "payment_status": row.payment_status,
        "payment_source": row.payment_source,
        "linked_employee_expense_id": row.linked_employee_expense_id,
        "status": row.status,
        "remarks": row.remarks,
        "created_by_id": row.created_by_id,
        "created_at": row.created_at.isoformat(),
    }


def create_vendor_invoice(db: Session, *, actor: User, project_id: int, payload: VendorInvoiceInput) -> ProjectVendorInvoice:
    _project(db, project_id)
    existing = db.scalar(select(ProjectVendorInvoice.id).where(
        ProjectVendorInvoice.project_id == project_id,
        func.lower(ProjectVendorInvoice.vendor_name) == payload.vendor_name.lower(),
        ProjectVendorInvoice.invoice_number == payload.invoice_number,
    ))
    if existing is not None:
        raise ValueError("This vendor invoice is already recorded for the project")
    if payload.linked_employee_expense_id is not None:
        expense = _expense(db, payload.linked_employee_expense_id)
        if expense.project_id != project_id:
            raise ValueError("Linked employee expense belongs to a different project")
        if expense.payment_source != "EMPLOYEE_PAID":
            raise ValueError("Employee-paid vendor invoices can link only to an employee-paid project expense")
        if expense.linked_vendor_invoice_id is not None:
            raise ValueError("The employee expense is already linked to a vendor invoice")
    tax = money(payload.cgst + payload.sgst + payload.igst + payload.other_tax)
    gross = money(payload.taxable_amount + tax)
    snapshot = create_fx_snapshot(
        db,
        project_id=project_id,
        event_type="VENDOR_INVOICE",
        original_amount=gross,
        currency_code=payload.currency_code,
        event_date=payload.invoice_date,
        actor=actor,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
        locked=True,
    )
    row = ProjectVendorInvoice(
        project_id=project_id,
        vendor_name=payload.vendor_name,
        vendor_gstin=payload.vendor_gstin,
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        due_date=payload.due_date,
        po_wo_reference=payload.po_wo_reference,
        category=payload.category,
        description=payload.description,
        hsn_sac=payload.hsn_sac,
        quantity=payload.quantity,
        rate=money(payload.rate) if payload.rate is not None else None,
        currency_code=payload.currency_code,
        taxable_amount=money(payload.taxable_amount),
        cgst=money(payload.cgst),
        sgst=money(payload.sgst),
        igst=money(payload.igst),
        other_tax=money(payload.other_tax),
        gross_amount=gross,
        fx_snapshot_id=snapshot.id,
        fx_rate_to_inr=snapshot.fx_rate_to_inr,
        fx_rate_date=snapshot.fx_rate_date,
        fx_rate_source=snapshot.fx_rate_source,
        fx_rate_mode=snapshot.fx_rate_mode,
        taxable_inr=convert_to_inr(payload.taxable_amount, snapshot.fx_rate_to_inr),
        tax_inr=convert_to_inr(tax, snapshot.fx_rate_to_inr),
        gross_inr=convert_to_inr(gross, snapshot.fx_rate_to_inr),
        # EMPLOYEE_PAID means the supplier has already been settled by the employee;
        # the company's remaining liability is the linked employee reimbursement.
        payment_status="PAID" if payload.payment_source == "EMPLOYEE_PAID" else "UNPAID",
        payment_source=payload.payment_source,
        linked_employee_expense_id=payload.linked_employee_expense_id,
        status="ACTIVE",
        remarks=payload.remarks,
        created_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    snapshot.event_ref_id = row.id
    if payload.linked_employee_expense_id is not None:
        expense = _expense(db, payload.linked_employee_expense_id)
        expense.linked_vendor_invoice_id = row.id
    db.flush()
    return row


def list_vendor_invoices(db: Session, *, project_id: int | None = None) -> list[dict]:
    query = select(ProjectVendorInvoice)
    if project_id is not None:
        _project(db, project_id)
        query = query.where(ProjectVendorInvoice.project_id == project_id)
    rows = list(db.scalars(query.order_by(ProjectVendorInvoice.invoice_date.desc(), ProjectVendorInvoice.id.desc())).all())
    return [_vendor_invoice_payload(db, row) for row in rows]


def record_vendor_payment(db: Session, *, actor: User, vendor_invoice_id: int, payload: VendorPaymentInput) -> ProjectVendorPayment:
    invoice = _vendor_invoice(db, vendor_invoice_id)
    if invoice.status != "ACTIVE":
        raise ValueError("Payments cannot be recorded against a cancelled vendor invoice")
    if invoice.payment_source == "EMPLOYEE_PAID":
        raise ValueError("Employee-paid vendor invoices are settled through the linked employee reimbursement, not a second vendor payment")
    paid_before = Decimal(db.scalar(select(func.coalesce(func.sum(ProjectVendorPayment.amount), 0)).where(
        ProjectVendorPayment.vendor_invoice_id == invoice.id
    )) or 0)
    if paid_before + payload.amount > Decimal(invoice.gross_amount):
        raise ValueError("Vendor payment exceeds the outstanding invoice amount")
    # The payment amount is always interpreted in the vendor invoice currency.
    # VendorPaymentInput inherits a generic FX currency field whose default is INR,
    # so requiring clients to echo the invoice currency would incorrectly reject
    # otherwise valid foreign-currency payments.
    snapshot = create_fx_snapshot(
        db,
        project_id=invoice.project_id,
        event_type="VENDOR_PAYMENT",
        original_amount=payload.amount,
        currency_code=invoice.currency_code,
        event_date=payload.payment_date,
        actor=actor,
        manual_rate=payload.fx_rate_to_inr,
        manual_mode=payload.fx_rate_mode,
        manual_reason=payload.fx_override_reason,
        locked=True,
    )
    row = ProjectVendorPayment(
        vendor_invoice_id=invoice.id,
        project_id=invoice.project_id,
        amount=money(payload.amount),
        amount_inr=convert_to_inr(payload.amount, snapshot.fx_rate_to_inr),
        payment_date=payload.payment_date,
        payment_reference=payload.payment_reference,
        payment_mode=payload.payment_mode,
        recorded_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    snapshot.event_ref_id = row.id
    paid_after = paid_before + payload.amount
    invoice.payment_status = "PAID" if paid_after == Decimal(invoice.gross_amount) else "PARTIALLY_PAID"
    db.flush()
    return row


def prepare_client_invoice_fx(
    db: Session,
    *,
    actor: User,
    invoice: ProjectInvoice,
    manual_rate: Decimal | None = None,
    manual_mode: str | None = None,
    manual_reason: str | None = None,
) -> ProjectFxSnapshot:
    gross = money(Decimal(invoice.amount) + Decimal(invoice.tax_amount or 0))
    snapshot = create_fx_snapshot(
        db,
        project_id=invoice.project_id,
        event_type="CLIENT_INVOICE",
        original_amount=gross,
        currency_code=invoice.currency,
        event_date=invoice.invoice_date,
        actor=actor,
        manual_rate=manual_rate,
        manual_mode=manual_mode,
        manual_reason=manual_reason,
        locked=False,
    )
    invoice.fx_snapshot_id = snapshot.id
    invoice.fx_rate_to_inr = snapshot.fx_rate_to_inr
    invoice.fx_rate_date = snapshot.fx_rate_date
    invoice.fx_rate_source = snapshot.fx_rate_source
    invoice.fx_rate_mode = snapshot.fx_rate_mode
    invoice.base_inr = convert_to_inr(invoice.amount, snapshot.fx_rate_to_inr)
    invoice.tax_inr = convert_to_inr(invoice.tax_amount or 0, snapshot.fx_rate_to_inr)
    invoice.total_inr = convert_to_inr(gross, snapshot.fx_rate_to_inr)
    invoice.fx_locked = False
    db.flush()
    snapshot.event_ref_id = invoice.id
    return snapshot


def lock_client_invoice_fx(
    db: Session,
    *,
    actor: User,
    invoice: ProjectInvoice,
    manual_rate: Decimal | None = None,
    manual_mode: str | None = None,
    manual_reason: str | None = None,
) -> None:
    if invoice.fx_rate_to_inr is None:
        prepare_client_invoice_fx(
            db,
            actor=actor,
            invoice=invoice,
            manual_rate=manual_rate,
            manual_mode=manual_mode,
            manual_reason=manual_reason,
        )
    invoice.fx_locked = True
    if invoice.fx_snapshot_id:
        snap = db.get(ProjectFxSnapshot, invoice.fx_snapshot_id)
        if snap:
            snap.fx_locked = True
            snap.verified_by_id = actor.id
            snap.verified_at = utc_now()
    db.flush()


def prepare_client_payment_fx(
    db: Session,
    *,
    actor: User,
    invoice: ProjectInvoice,
    payment: ProjectInvoicePayment,
    manual_rate: Decimal | None = None,
    manual_mode: str | None = None,
    manual_reason: str | None = None,
) -> ProjectFxSnapshot:
    snapshot = create_fx_snapshot(
        db,
        project_id=invoice.project_id,
        event_type="CLIENT_PAYMENT",
        original_amount=payment.amount,
        currency_code=invoice.currency,
        event_date=payment.payment_date,
        actor=actor,
        manual_rate=manual_rate,
        manual_mode=manual_mode,
        manual_reason=manual_reason,
        locked=True,
    )
    invoice_rate = Decimal(invoice.fx_rate_to_inr or (1 if invoice.currency.upper() == "INR" else 0))
    if invoice_rate <= 0:
        raise ValueError("Invoice FX rate is missing; repair the invoice FX snapshot before recording payment")
    payment.payment_currency = invoice.currency.upper()
    payment.fx_snapshot_id = snapshot.id
    payment.fx_rate_to_inr = snapshot.fx_rate_to_inr
    payment.fx_rate_date = snapshot.fx_rate_date
    payment.fx_rate_source = snapshot.fx_rate_source
    payment.fx_rate_mode = snapshot.fx_rate_mode
    payment.inr_equivalent = convert_to_inr(payment.amount, snapshot.fx_rate_to_inr)
    payment.invoice_inr_equivalent = convert_to_inr(payment.amount, invoice_rate)
    payment.fx_gain_loss_inr = money(payment.inr_equivalent - payment.invoice_inr_equivalent)
    db.flush()
    snapshot.event_ref_id = payment.id
    return snapshot


def _date_in_range(value: date | None, start: date | None, end: date | None) -> bool:
    if value is None:
        return False
    return (start is None or value >= start) and (end is None or value <= end)


def project_cost_summary(db: Session, *, project_id: int) -> dict:
    project = _project(db, project_id)
    estimate = current_approved_estimate(db, project_id)
    expenses = list(db.scalars(select(ProjectExpense).where(ProjectExpense.project_id == project_id)).all())
    vendor = list(db.scalars(select(ProjectVendorInvoice).where(
        ProjectVendorInvoice.project_id == project_id,
        ProjectVendorInvoice.status == "ACTIVE",
    )).all())
    linked_expense_ids = {row.linked_employee_expense_id for row in vendor if row.linked_employee_expense_id}
    employee_cost = sum((money(row.approved_amount) for row in expenses if row.status in {"APPROVED", "REIMBURSED"} and row.id not in linked_expense_ids), Decimal("0.00"))
    vendor_cost = sum((money(row.gross_inr) for row in vendor), Decimal("0.00"))
    invoices = list(db.scalars(select(ProjectInvoice).where(
        ProjectInvoice.project_id == project_id,
        ProjectInvoice.status != "INVOICE_DRAFT",
    )).all())
    billed_net = sum((money(row.base_inr if row.base_inr is not None else row.amount if row.currency.upper() == "INR" else 0) for row in invoices), Decimal("0.00"))
    payments = list(db.scalars(select(ProjectInvoicePayment).where(ProjectInvoicePayment.project_id == project_id)).all())
    realized = sum((money(row.inr_equivalent if row.inr_equivalent is not None else row.amount) for row in payments), Decimal("0.00"))
    fx_variance = sum((money(row.fx_gain_loss_inr) for row in payments if row.fx_gain_loss_inr is not None), Decimal("0.00"))
    cost = money(employee_cost + vendor_cost)
    return {
        "project_id": project.id,
        "project_code": project.project_code,
        "client_code": project.client.client_code if project.client else None,
        "approved_estimate_base_inr": float(estimate.base_inr) if estimate else None,
        "estimated_direct_cost_inr": float(estimate.estimated_direct_cost_inr) if estimate and estimate.estimated_direct_cost_inr is not None else None,
        "billed_net_revenue_inr": float(billed_net),
        "payment_realization_inr": float(realized),
        "employee_cost_inr": float(employee_cost),
        "vendor_cost_inr": float(vendor_cost),
        "total_direct_cost_inr": float(cost),
        "actual_margin_inr": float(money(billed_net - cost)),
        "projected_margin_inr": float(money(estimate.base_inr - (estimate.estimated_direct_cost_inr if estimate.estimated_direct_cost_inr is not None else cost))) if estimate else None,
        "fx_gain_loss_inr": float(fx_variance),
    }


def assert_commercial_closure_ready(db: Session, *, project_id: int) -> None:
    """Additional V8.1 commercial guards. Legacy projects with no commercial records are grandfathered."""
    has_commercial = any([
        db.scalar(select(ProjectCommercialEstimateRevision.id).where(ProjectCommercialEstimateRevision.project_id == project_id).limit(1)),
        db.scalar(select(ProjectExpense.id).where(ProjectExpense.project_id == project_id).limit(1)),
        db.scalar(select(ProjectVendorInvoice.id).where(ProjectVendorInvoice.project_id == project_id).limit(1)),
    ])
    if not has_commercial:
        return
    pending_revision = db.scalar(select(ProjectCommercialEstimateRevision.id).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.status.in_(["DRAFT", "PENDING_APPROVAL", "RETURNED"]),
    ).limit(1))
    if pending_revision is not None:
        raise ValueError("Resolve all commercial estimate revisions before Finance Closure")
    open_expense = db.scalar(select(ProjectExpense).where(
        ProjectExpense.project_id == project_id,
        or_(
            ProjectExpense.status.in_(["DRAFT", "SUBMITTED", "RETURNED"]),
            and_(ProjectExpense.status == "APPROVED", ProjectExpense.payment_source == "EMPLOYEE_PAID"),
        ),
    ).order_by(ProjectExpense.id).limit(1))
    if open_expense is not None:
        raise ValueError(f"Project expense {open_expense.expense_code} is not financially settled")
    open_vendor = db.scalar(select(ProjectVendorInvoice).where(
        ProjectVendorInvoice.project_id == project_id,
        ProjectVendorInvoice.status == "ACTIVE",
        ProjectVendorInvoice.payment_status != "PAID",
    ).order_by(ProjectVendorInvoice.id).limit(1))
    if open_vendor is not None:
        raise ValueError(f"Vendor invoice {open_vendor.invoice_number} is not fully paid")

    # assigned_ids = set(db.scalars(select(FinanceProjectAssignment.user_id).where(
    #     FinanceProjectAssignment.project_id == project_id,
    #     FinanceProjectAssignment.is_active.is_(True),
    # )).all())
    # if assigned_ids:
    #     declared_ids = set(db.scalars(select(ProjectExpenseDeclaration.employee_id).where(
    #         ProjectExpenseDeclaration.project_id == project_id,
    #         ProjectExpenseDeclaration.phase_key == "ORIGINAL",
    #         ProjectExpenseDeclaration.declaration_status == "NO_MORE_EXPENSES",
    #         ProjectExpenseDeclaration.employee_id.in_(assigned_ids),
    #     )).all())
    #     missing = assigned_ids - declared_ids
    #     if missing:
    #         raise ValueError(f"{len(missing)} assigned employee(s) have not declared 'No More Project Expenses'")


def commercial_and_fx_variance(
    baseline: ProjectCommercialEstimateRevision | None,
    invoices: list[ProjectInvoice],
) -> tuple[Decimal | None, Decimal | None]:
    """Split (final revenue - baseline revenue) into a SCOPE effect and an FX effect, both in INR.

    baseline: the Finance-approved Revision 1 (original currency amount B0 at rate R0).
    invoices: the raised invoices of the same project (original-currency base Bi at its own rate Ri).

      commercial / scope variance = (sum(Bi) - B0) x R0        (what changed in the contract, at the baseline rate)
      FX variance                 = sum(Bi x (Ri - R0))        (what the currency moved, on what was billed)

    Their sum equals sum(Bi x Ri) - B0 x R0, the total INR movement. Returns (None, None) when there is no baseline,
    no raised invoice, or an invoice is in a different currency than the baseline (not comparable).
    """
    if baseline is None or not invoices:
        return None, None
    if any((inv.currency or "").upper() != baseline.currency_code for inv in invoices):
        return None, None
    if any(inv.fx_rate_to_inr is None for inv in invoices):
        return None, None
    baseline_amount = Decimal(baseline.taxable_base_amount)
    baseline_rate = Decimal(baseline.fx_rate_to_inr)
    billed_original = sum((Decimal(inv.amount) for inv in invoices), Decimal("0"))
    commercial = (billed_original - baseline_amount) * baseline_rate
    fx = sum((Decimal(inv.amount) * (Decimal(inv.fx_rate_to_inr) - baseline_rate) for inv in invoices), Decimal("0"))
    return money(commercial), money(fx)


def management_analytics(
    db: Session,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    project_id: int | None = None,
    display_currency: str = "INR",
) -> dict:
    if date_from and date_to and date_to < date_from:
        raise ValueError("date_to cannot be earlier than date_from")
    display = normalize_currency(display_currency)
    if display not in MANAGEMENT_DISPLAY_CURRENCIES:
        raise ValueError("Selected Management display currency is not enabled")

    project_query = select(FinanceProject)
    if project_id:
        project_query = project_query.where(FinanceProject.id == project_id)
    projects = list(db.scalars(project_query.order_by(FinanceProject.project_code)).all())
    ids = [p.id for p in projects]
    if not ids:
        return {"filters": {"date_from": date_from, "date_to": date_to, "project_id": project_id, "display_currency": display}, "summary_inr": {}, "projects": [], "employee_costs": [], "monthly": []}

    estimates = list(db.scalars(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id.in_(ids),
        ProjectCommercialEstimateRevision.status == "APPROVED",
    ).order_by(ProjectCommercialEstimateRevision.project_id, ProjectCommercialEstimateRevision.revision_no.desc())).all())
    current_estimate: dict[int, ProjectCommercialEstimateRevision] = {}
    baseline_estimate: dict[int, ProjectCommercialEstimateRevision] = {}
    for row in estimates:
        current_estimate.setdefault(row.project_id, row)
        if row.revision_no == 1:
            baseline_estimate[row.project_id] = row

    invoices = [row for row in db.scalars(select(ProjectInvoice).where(ProjectInvoice.project_id.in_(ids), ProjectInvoice.status != "INVOICE_DRAFT")).all() if _date_in_range(row.invoice_date, date_from, date_to)]
    payments = [row for row in db.scalars(select(ProjectInvoicePayment).where(ProjectInvoicePayment.project_id.in_(ids))).all() if _date_in_range(row.payment_date, date_from, date_to)]
    expenses = [row for row in db.scalars(select(ProjectExpense).where(ProjectExpense.project_id.in_(ids))).all() if _date_in_range(row.expense_date, date_from, date_to)]
    vendor = [row for row in db.scalars(select(ProjectVendorInvoice).where(ProjectVendorInvoice.project_id.in_(ids), ProjectVendorInvoice.status == "ACTIVE")).all() if _date_in_range(row.invoice_date, date_from, date_to)]
    linked_expense_ids = {row.linked_employee_expense_id for row in vendor if row.linked_employee_expense_id}

    billed_by_project: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in invoices:
        value = row.base_inr if row.base_inr is not None else (row.amount if row.currency.upper() == "INR" else Decimal("0"))
        billed_by_project[row.project_id] += money(value)
    paid_by_project: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    fx_by_project: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in payments:
        paid_by_project[row.project_id] += money(row.inr_equivalent if row.inr_equivalent is not None else row.amount)
        fx_by_project[row.project_id] += money(row.fx_gain_loss_inr)
    employee_by_project: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    employee_by_user: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in expenses:
        if row.status in {"APPROVED", "REIMBURSED"} and row.id not in linked_expense_ids:
            amount = money(row.approved_amount)
            employee_by_project[row.project_id] += amount
            employee_by_user[row.employee_id] += amount
    vendor_by_project: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for row in vendor:
        vendor_by_project[row.project_id] += money(row.gross_inr)

    invoices_by_project: dict[int, list[ProjectInvoice]] = defaultdict(list)
    for row in invoices:
        invoices_by_project[row.project_id].append(row)
    commercial_variance_total = Decimal("0.00")
    fx_variance_total = Decimal("0.00")
    not_comparable = 0

    rows: list[dict] = []
    for project in projects:
        estimate = current_estimate.get(project.id)
        baseline = baseline_estimate.get(project.id)
        scope_var, fx_var = commercial_and_fx_variance(baseline, invoices_by_project.get(project.id, []))
        if scope_var is None and invoices_by_project.get(project.id):
            not_comparable += 1
        commercial_variance_total += scope_var or Decimal("0.00")
        fx_variance_total += fx_var or Decimal("0.00")
        cost = money(employee_by_project[project.id] + vendor_by_project[project.id])
        billed = money(billed_by_project[project.id])
        rows.append({
            "project_id": project.id,
            "project_code": project.project_code,
            "client_code": project.client.client_code if project.client else None,
            "estimate_base_inr": float(estimate.base_inr) if estimate else None,
            "estimate_gross_inr": float(estimate.gross_inr) if estimate else None,
            "baseline_revision_base_inr": float(baseline.base_inr) if baseline else None,
            "latest_approved_revision_no": estimate.revision_no if estimate else None,
            "latest_approved_base_inr": float(estimate.base_inr) if estimate else None,
            "commercial_variance_inr": float(scope_var) if scope_var is not None else None,
            "fx_variance_inr": float(fx_var) if fx_var is not None else None,
            "billed_net_inr": float(billed),
            "payments_realized_inr": float(money(paid_by_project[project.id])),
            "employee_cost_inr": float(money(employee_by_project[project.id])),
            "vendor_cost_inr": float(money(vendor_by_project[project.id])),
            "total_direct_cost_inr": float(cost),
            "margin_inr": float(money(billed - cost)),
            "fx_gain_loss_inr": float(money(fx_by_project[project.id])),
        })

    summary = {
        "approved_estimate_base_inr": float(sum((money(current_estimate[p.id].base_inr) for p in projects if p.id in current_estimate), Decimal("0.00"))),
        "billed_net_inr": float(sum((billed_by_project[p.id] for p in projects), Decimal("0.00"))),
        "payments_realized_inr": float(sum((paid_by_project[p.id] for p in projects), Decimal("0.00"))),
        "employee_cost_inr": float(sum((employee_by_project[p.id] for p in projects), Decimal("0.00"))),
        "vendor_cost_inr": float(sum((vendor_by_project[p.id] for p in projects), Decimal("0.00"))),
        "fx_gain_loss_inr": float(sum((fx_by_project[p.id] for p in projects), Decimal("0.00"))),
    }
    summary["baseline_revision_base_inr"] = float(sum((money(baseline_estimate[p.id].base_inr) for p in projects if p.id in baseline_estimate), Decimal("0.00")))
    summary["commercial_variance_inr"] = float(money(commercial_variance_total))
    summary["fx_variance_inr"] = float(money(fx_variance_total))
    summary["variance_projects_not_comparable"] = not_comparable
    summary["total_direct_cost_inr"] = float(money(Decimal(str(summary["employee_cost_inr"])) + Decimal(str(summary["vendor_cost_inr"]))))
    summary["margin_inr"] = float(money(Decimal(str(summary["billed_net_inr"])) - Decimal(str(summary["total_direct_cost_inr"]))))

    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(list(employee_by_user.keys()) or [-1]))).all()}
    employee_costs = [
        {"employee_id": uid, "employee_name": users[uid].full_name if uid in users else f"User {uid}", "cost_inr": float(money(value))}
        for uid, value in sorted(employee_by_user.items(), key=lambda item: item[1], reverse=True)
    ]

    month_map: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"billing": Decimal("0"), "payments": Decimal("0"), "employee_cost": Decimal("0"), "vendor_cost": Decimal("0")})
    for row in invoices:
        month_map[row.invoice_date.strftime("%Y-%m")]["billing"] += money(row.base_inr if row.base_inr is not None else row.amount if row.currency.upper() == "INR" else 0)
    for row in payments:
        month_map[row.payment_date.strftime("%Y-%m")]["payments"] += money(row.inr_equivalent if row.inr_equivalent is not None else row.amount)
    for row in expenses:
        if row.status in {"APPROVED", "REIMBURSED"} and row.id not in linked_expense_ids:
            month_map[row.expense_date.strftime("%Y-%m")]["employee_cost"] += money(row.approved_amount)
    for row in vendor:
        month_map[row.invoice_date.strftime("%Y-%m")]["vendor_cost"] += money(row.gross_inr)
    monthly = []
    for month, values in sorted(month_map.items()):
        total_cost = money(values["employee_cost"] + values["vendor_cost"])
        monthly.append({
            "month": month,
            "billing_inr": float(money(values["billing"])),
            "payments_inr": float(money(values["payments"])),
            "employee_cost_inr": float(money(values["employee_cost"])),
            "vendor_cost_inr": float(money(values["vendor_cost"])),
            "total_cost_inr": float(total_cost),
            "margin_inr": float(money(values["billing"] - total_cost)),
        })

    display_block = None
    if display != "INR":
        quote = get_fx_service().get_rate("INR", display, None)
        rate = quote.rate
        converted = {key.replace("_inr", ""): float(money(Decimal(str(value)) * rate)) for key, value in summary.items() if key.endswith("_inr")}
        display_block = {
            "currency": display,
            "rate_from_inr": float(rate),
            "rate_date": quote.rate_date.isoformat(),
            "source": quote.source,
            "mode": "DISPLAY_ONLY_CURRENT_REFERENCE",
            "summary": converted,
        }

    return {
        "filters": {
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "project_id": project_id,
            "display_currency": display,
        },
        "summary_inr": summary,
        "display_conversion": display_block,
        "projects": rows,
        "employee_costs": employee_costs,
        "monthly": monthly,
    }


def validate_attachment_owner(db: Session, *, project_id: int, owner_type: str, owner_id: int) -> None:
    if owner_type == "ESTIMATE_REVISION":
        row = _estimate(db, owner_id)
    elif owner_type == "EXPENSE":
        row = _expense(db, owner_id)
    elif owner_type == "VENDOR_INVOICE":
        row = _vendor_invoice(db, owner_id)
    elif owner_type == "CLIENT_INVOICE":
        row = db.get(ProjectInvoice, owner_id)
        if row is None:
            raise ValueError("Client invoice not found")
    else:
        raise ValueError("Unsupported attachment owner type")
    if row.project_id != project_id:
        raise ValueError("Attachment owner belongs to a different project")


def attachment_payload(row: ProjectCommercialAttachment) -> dict:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "owner_type": row.owner_type,
        "owner_id": row.owner_id,
        "doc_type": row.doc_type,
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "file_size": row.file_size,
        "content_sha256": row.content_sha256,
        "uploaded_by_id": row.uploaded_by_id,
        "created_at": row.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Project Manager billing basis (operational facts) + Finance billing recommendation
# ---------------------------------------------------------------------------
# The PM confirms WHAT was delivered / achieved. Finance combines that with the approved commercial
# basis (rate, value, FX) to decide WHAT to invoice. The PM-facing functions below never read or
# return a rate, contract value, FX figure or margin, and the recommendation never raises an invoice.

_EARLY_STATES = {"draft", "pending_finance_approval", "finance_returned", "finance_approved", "pm_assigned"}
_INVOICED_STATES = {
    "invoice_raised", "payment_pending", "partially_paid", "payment_overdue", "payment_received",
    "invoice_closed", "finance_closure_pending", "closed",
}
BILLING_BASIS_BLOCKED_STATES = _EARLY_STATES | _INVOICED_STATES


def _admin_equivalent(actor: User) -> bool:
    return (actor.role or "").strip().lower() in {"admin", "software_team"}


def assert_pm_billing_authority(project: FinanceProject, actor: User) -> None:
    if _admin_equivalent(actor):
        return
    profile = project.master_profile
    if profile is None or profile.project_manager_id != actor.id:
        raise PermissionError("Only the Project Manager assigned to this project can confirm its billing basis")


def billing_basis_window(workflow: ProjectWorkflow | None) -> tuple[bool, str | None]:
    if workflow is None:
        return False, "This project is not part of the V8.1 project workflow"
    key = _status_key(workflow)
    if key in _EARLY_STATES:
        return False, "Billing basis can be confirmed once the project team is assigned and work is under way"
    if key in _INVOICED_STATES:
        return False, "An invoice has already been raised, so the billing basis is closed"
    return True, None


def _operational_reference(db: Session, project: FinanceProject, workflow: ProjectWorkflow | None) -> dict:
    """Existing operational data the PM can lean on (work packages, planned quantity): reused, never duplicated."""
    packages = list(db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.project_id == project.id,
        OrthoWorkPackage.rework_cycle_id.is_(None),
    )).all())
    delivered = [pkg for pkg in packages if pkg.current_stage == "delivered"]
    total_area = sum((Decimal(pkg.area) for pkg in packages if pkg.area is not None), Decimal("0"))
    delivered_area = sum((Decimal(pkg.area) for pkg in delivered if pkg.area is not None), Decimal("0"))
    units = {pkg.area_unit for pkg in packages if pkg.area_unit}
    return {
        "work_packages_total": len(packages),
        "work_packages_delivered": len(delivered),
        "completion_percent_by_packages": float((Decimal(len(delivered)) / Decimal(len(packages)) * Decimal("100")).quantize(Decimal("0.01"))) if packages else None,
        "total_area": float(total_area) if packages else None,
        "delivered_area": float(delivered_area) if packages else None,
        "area_unit": next(iter(units)) if len(units) == 1 else None,
        "planned_quantity": float(workflow.quantity) if workflow is not None and workflow.quantity is not None else None,
        "planned_quantity_unit": workflow.quantity_unit if workflow is not None else None,
        "operational_completed_at": workflow.operational_completed_at.isoformat() if workflow is not None and workflow.operational_completed_at else None,
        "completion_date": workflow.completion_date.isoformat() if workflow is not None and workflow.completion_date else None,
    }


def _basis_payload(db: Session, row: ProjectBillingBasis) -> dict:
    user = db.get(User, row.confirmed_by_id)
    return {
        "id": row.id,
        "project_id": row.project_id,
        "entry_no": row.entry_no,
        "estimate_revision_id": row.estimate_revision_id,
        "billing_type": row.billing_type,
        "cumulative_billable_quantity": float(row.cumulative_billable_quantity) if row.cumulative_billable_quantity is not None else None,
        "quantity_unit": row.quantity_unit,
        "milestone_id": row.milestone_id,
        "milestone_name": row.milestone_name,
        "completion_percent": float(row.completion_percent) if row.completion_percent is not None else None,
        "delivery_accepted": bool(row.delivery_accepted),
        "acceptance_reference": row.acceptance_reference,
        "pm_remarks": row.pm_remarks,
        "billing_readiness_date": row.billing_readiness_date.isoformat() if row.billing_readiness_date else None,
        "confirmed_by_id": row.confirmed_by_id,
        "confirmed_by_name": user.full_name if user else None,
        "confirmed_at": row.confirmed_at.isoformat(),
    }


def list_billing_basis(db: Session, *, project_id: int) -> list[dict]:
    rows = list(db.scalars(select(ProjectBillingBasis).where(
        ProjectBillingBasis.project_id == project_id
    ).order_by(ProjectBillingBasis.entry_no.desc())).all())
    return [_basis_payload(db, row) for row in rows]


def _project_invoices(db: Session, project_id: int) -> list[ProjectInvoice]:
    return list(db.scalars(select(ProjectInvoice).where(ProjectInvoice.project_id == project_id).order_by(ProjectInvoice.id)).all())


def _invoiced_quantity(invoices: list[ProjectInvoice], *, exclude_invoice_id: int | None = None) -> Decimal:
    return sum(
        (Decimal(inv.billed_quantity) for inv in invoices if inv.billed_quantity is not None and inv.id != exclude_invoice_id),
        Decimal("0"),
    )


def pm_billing_basis_view(db: Session, *, actor: User, project_id: int) -> dict:
    """What the assigned PM sees: billing TYPE, unit and milestone NAMES only. No rate, value, FX or margin."""
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    assert_pm_billing_authority(project, actor)
    revision = current_approved_estimate(db, project_id)
    allowed, reason = billing_basis_window(workflow)
    milestones = []
    if revision is not None and revision.billing_type == "milestone":
        milestones = [{"id": m.id, "sequence": m.sequence, "name": m.milestone_name} for m in _milestone_rows(db, revision.id)]
    return {
        "project_id": project.id,
        "project_code": project.project_code,
        "project_name": project.project_name,
        "workflow_status": workflow.status if workflow is not None else None,
        "billing_type": revision.billing_type if revision is not None else None,
        "billing_type_label": BILLING_TYPES.get(revision.billing_type, revision.billing_type) if revision is not None else None,
        "quantity_unit": revision.quantity_unit if revision is not None else None,
        "milestones": milestones,
        "entries": list_billing_basis(db, project_id=project_id),
        "operational_reference": _operational_reference(db, project, workflow),
        "can_submit": allowed,
        "cannot_submit_reason": reason,
        "commercial_values_visible": False,
    }


def record_billing_basis(db: Session, *, actor: User, project_id: int, payload: BillingBasisInput) -> ProjectBillingBasis:
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    assert_pm_billing_authority(project, actor)
    allowed, reason = billing_basis_window(workflow)
    if not allowed:
        raise ValueError(reason or "Billing basis cannot be recorded now")
    revision = current_approved_estimate(db, project_id)
    billing_type = revision.billing_type if revision is not None else "other"
    invoices = _project_invoices(db, project_id)
    quantity = payload.cumulative_billable_quantity
    unit = payload.quantity_unit
    completion = payload.completion_percent
    milestone: ProjectCommercialMilestone | None = None

    if revision is not None and billing_type in QUANTITY_BILLING_TYPES:
        if quantity is None:
            raise ValueError("Enter the accepted (cumulative) billable quantity")
        unit = revision.quantity_unit or unit
        invoiced = _invoiced_quantity(invoices)
        if quantity < invoiced:
            raise ValueError(f"Billable quantity cannot be lower than the {invoiced} already invoiced")
    elif revision is not None and billing_type == "milestone":
        if payload.milestone_id is None:
            raise ValueError("Select the milestone that has been achieved")
        milestone = db.get(ProjectCommercialMilestone, payload.milestone_id)
        if milestone is None or milestone.revision_id != revision.id:
            raise ValueError("The milestone does not belong to this project's approved commercial basis")
        if not payload.delivery_accepted:
            raise ValueError("Confirm that the milestone has been achieved and accepted")
        if any(inv.billed_milestone_id == milestone.id for inv in invoices):
            raise ValueError("This milestone has already been invoiced")
    elif revision is not None and billing_type == "fixed_price":
        if completion is None and not payload.delivery_accepted:
            raise ValueError("Confirm the completion percentage or that delivery has been accepted")
        if completion is None:
            completion = Decimal("100.00")
    else:
        if not payload.pm_remarks and quantity is None:
            raise ValueError("Describe the billable work in the remarks or enter a quantity")

    entry_no = int(db.scalar(select(func.coalesce(func.max(ProjectBillingBasis.entry_no), 0)).where(
        ProjectBillingBasis.project_id == project_id
    )) or 0) + 1
    row = ProjectBillingBasis(
        project_id=project_id,
        entry_no=entry_no,
        estimate_revision_id=revision.id if revision is not None else None,
        billing_type=billing_type,
        cumulative_billable_quantity=quantity,
        quantity_unit=unit,
        milestone_id=milestone.id if milestone is not None else None,
        milestone_name=milestone.milestone_name if milestone is not None else None,
        completion_percent=completion,
        delivery_accepted=bool(payload.delivery_accepted),
        acceptance_reference=payload.acceptance_reference,
        pm_remarks=payload.pm_remarks,
        billing_readiness_date=payload.billing_readiness_date,
        confirmed_by_id=actor.id,
    )
    db.add(row)
    db.flush()

    from app.modules.notifications.service import create_global_notification
    from app.modules.operations.lifecycle_service import add_timeline_event

    summary = "; ".join(part for part in [
        f"{quantity} {unit or ''}".strip() if quantity is not None else "",
        f"milestone {milestone.milestone_name}" if milestone is not None else "",
        f"{completion}% complete" if completion is not None and milestone is None else "",
        "delivery accepted" if payload.delivery_accepted else "",
    ] if part)
    add_timeline_event(
        db, project_id=project_id, event_type="pm_billing_basis_confirmed",
        title="PM confirmed billing basis", status=None, actor_user_id=actor.id,
        details=summary or "Billing basis recorded",
    )
    create_global_notification(
        db,
        event_type="commercial.billing_basis_confirmed",
        title=f"Billing basis confirmed: {project.project_code}",
        message=f"The Project Manager confirmed the billable basis for {project.project_code}" + (f" ({summary})." if summary else "."),
        category="approval",
        target_url="/finance/billing",
        recipient_roles=["finance"],
        dedupe_key=f"commercial:billing-basis:{row.id}",
    )
    return row


def billing_recommendation(db: Session, *, project_id: int) -> dict:
    """Finance / BD / Management view: approved commercial basis + PM billing basis + a RECOMMENDED taxable amount.

    Only an APPROVED revision is the active commercial basis. The recommendation is advisory: Finance still
    verifies tax, date, PO and evidence and explicitly creates and raises the invoice.
    """
    project = _project(db, project_id)
    workflow = _workflow(db, project_id)
    revision = current_approved_estimate(db, project_id)
    entries = list(db.scalars(select(ProjectBillingBasis).where(
        ProjectBillingBasis.project_id == project_id
    ).order_by(ProjectBillingBasis.entry_no)).all())
    latest = entries[-1] if entries else None
    invoices = _project_invoices(db, project_id)
    warnings: list[str] = []
    recommendation: dict | None = None
    commercial_basis: dict | None = None
    invoiced_base = Decimal("0.00")
    invoiced_quantity = _invoiced_quantity(invoices)
    invoiced_milestones = sorted({inv.billed_milestone_id for inv in invoices if inv.billed_milestone_id})

    if revision is None:
        warnings.append("No Finance-approved commercial revision exists for this project (legacy project): enter the invoice manually.")
    else:
        commercial_basis = _estimate_payload(revision)
        invoiced_base = sum((money(inv.amount) for inv in invoices if (inv.currency or "").upper() == revision.currency_code), Decimal("0.00"))
        if any((inv.currency or "").upper() != revision.currency_code for inv in invoices):
            warnings.append(f"Some invoices are not in {revision.currency_code}; only {revision.currency_code} invoices are netted off.")
        billing_type = revision.billing_type
        tax_percent = Decimal(revision.tax_percent)
        currency = revision.currency_code

        def finish(base: Decimal, method: str, formula: str, **extra) -> dict:
            base = money(base)
            tax = money(base * tax_percent / Decimal("100"))
            return {
                "method": method,
                "currency_code": currency,
                "base_amount": float(base),
                "tax_percent": float(tax_percent),
                "tax_amount": float(tax),
                "gross_amount": float(money(base + tax)),
                "formula": formula,
                "estimate_revision_id": revision.id,
                "billing_basis_id": latest.id if latest is not None else None,
                **extra,
            }

        if billing_type in QUANTITY_BILLING_TYPES and revision.unit_rate is not None:
            unit = revision.quantity_unit or ""
            if latest is None or latest.cumulative_billable_quantity is None:
                warnings.append("The Project Manager has not confirmed a billable quantity yet.")
            else:
                pm_quantity = Decimal(latest.cumulative_billable_quantity)
                net = max(pm_quantity - invoiced_quantity, Decimal("0"))
                if net <= 0:
                    warnings.append("The PM-confirmed quantity has already been fully invoiced.")
                else:
                    rate = Decimal(revision.unit_rate)
                    recommendation = finish(
                        net * rate, "UNIT_RATE",
                        f"{net.normalize():f} {unit} x {currency} {rate.normalize():f} per {unit}".strip(),
                        quantity=float(net), quantity_unit=unit, unit_rate=float(rate),
                        pm_cumulative_quantity=float(pm_quantity), invoiced_quantity=float(invoiced_quantity),
                    )
        elif billing_type == "milestone":
            milestones = _milestone_rows(db, revision.id)
            latest_by_milestone: dict[int, ProjectBillingBasis] = {}
            for entry in entries:
                if entry.milestone_id is not None:
                    latest_by_milestone[entry.milestone_id] = entry
            waiting = [
                m for m in milestones
                if m.id in latest_by_milestone and latest_by_milestone[m.id].delivery_accepted and m.id not in invoiced_milestones
            ]
            if not waiting:
                warnings.append("No PM-confirmed milestone is waiting to be invoiced.")
            else:
                first = waiting[0]
                recommendation = finish(
                    Decimal(first.amount or 0), "MILESTONE",
                    f"Milestone {first.sequence}: {first.milestone_name}" + (f" ({first.percent}% of approved base)" if first.percent is not None else ""),
                    milestone_id=first.id, milestone_name=first.milestone_name, milestone_sequence=first.sequence,
                    billing_basis_id=latest_by_milestone[first.id].id,
                    other_confirmed_milestones=[{"id": m.id, "name": m.milestone_name} for m in waiting[1:]],
                )
        elif billing_type == "fixed_price":
            percent = None
            if latest is not None:
                percent = latest.completion_percent if latest.completion_percent is not None else (Decimal("100") if latest.delivery_accepted else None)
            if percent is None:
                warnings.append("The Project Manager has not confirmed completion / delivery acceptance yet.")
            else:
                percent = Decimal(percent)
                earned = money(Decimal(revision.taxable_base_amount) * percent / Decimal("100"))
                net = max(earned - invoiced_base, Decimal("0.00"))
                if net <= 0:
                    warnings.append("The approved value earned so far has already been invoiced.")
                else:
                    recommendation = finish(
                        net, "FIXED_PRICE",
                        f"{percent.normalize():f}% of approved base {currency} {money(revision.taxable_base_amount)} less {currency} {invoiced_base} already invoiced",
                        completion_percent=float(percent), invoiced_base=float(invoiced_base),
                    )
        else:
            warnings.append("This billing type has no automatic calculation: use the approved commercial basis and the PM remarks.")

    return {
        "project_id": project.id,
        "project_code": project.project_code,
        "workflow_status": workflow.status if workflow is not None else None,
        "commercial_basis": commercial_basis,
        "pm_basis": _basis_payload(db, latest) if latest is not None else None,
        "pm_basis_entries": [_basis_payload(db, row) for row in reversed(entries)],
        "invoiced_to_date": {
            "base_amount": float(invoiced_base),
            "quantity": float(invoiced_quantity),
            "milestone_ids": invoiced_milestones,
            "invoice_count": len(invoices),
        },
        "recommendation": recommendation,
        "warnings": warnings,
        "operational_reference": _operational_reference(db, project, workflow),
    }


def apply_invoice_billing_links(
    db: Session,
    *,
    invoice: ProjectInvoice,
    estimate_revision_id: int | None,
    billing_basis_id: int | None,
    billed_quantity: Decimal | None,
    billed_milestone_id: int | None,
) -> None:
    """Record which approved revision / PM basis a client invoice was prepared from, and stop over-billing.

    Finance still types the invoice amount; this only validates the traceability links it chose to attach.
    """
    if estimate_revision_id is None and billing_basis_id is None and billed_quantity is None and billed_milestone_id is None:
        return
    project_id = invoice.project_id
    revision: ProjectCommercialEstimateRevision | None
    if estimate_revision_id is not None:
        revision = db.get(ProjectCommercialEstimateRevision, estimate_revision_id)
        if revision is None or revision.project_id != project_id or revision.status != "APPROVED":
            raise ValueError("The invoice basis must be an approved commercial revision of this project")
    else:
        revision = current_approved_estimate(db, project_id)
    if billing_basis_id is not None:
        basis = db.get(ProjectBillingBasis, billing_basis_id)
        if basis is None or basis.project_id != project_id:
            raise ValueError("The PM billing basis entry does not belong to this project")
    invoices = [inv for inv in _project_invoices(db, project_id) if inv.id != invoice.id]
    if billed_milestone_id is not None:
        milestone = db.get(ProjectCommercialMilestone, billed_milestone_id)
        if milestone is None or milestone.project_id != project_id or (revision is not None and milestone.revision_id != revision.id):
            raise ValueError("The milestone does not belong to the approved commercial basis")
        confirmed = db.scalar(select(ProjectBillingBasis).where(
            ProjectBillingBasis.project_id == project_id,
            ProjectBillingBasis.milestone_id == milestone.id,
        ).order_by(ProjectBillingBasis.entry_no.desc()).limit(1))
        if confirmed is None or not confirmed.delivery_accepted:
            raise ValueError("The Project Manager has not confirmed this milestone as achieved")
        if any(inv.billed_milestone_id == milestone.id for inv in invoices):
            raise ValueError("This milestone has already been invoiced")
    if billed_quantity is not None:
        if revision is None or revision.billing_type not in QUANTITY_BILLING_TYPES:
            raise ValueError("A billed quantity applies only to quantity-based billing")
        latest = db.scalar(select(ProjectBillingBasis).where(
            ProjectBillingBasis.project_id == project_id,
            ProjectBillingBasis.cumulative_billable_quantity.is_not(None),
        ).order_by(ProjectBillingBasis.entry_no.desc()).limit(1))
        if latest is None:
            raise ValueError("The Project Manager has not confirmed a billable quantity yet")
        already = _invoiced_quantity(invoices)
        if already + Decimal(billed_quantity) > Decimal(latest.cumulative_billable_quantity):
            raise ValueError(
                f"Billed quantity exceeds the PM-confirmed billable quantity ({latest.cumulative_billable_quantity} confirmed, {already} already invoiced)"
            )
    invoice.estimate_revision_id = revision.id if revision is not None else None
    invoice.billing_basis_id = billing_basis_id
    invoice.billed_quantity = billed_quantity
    invoice.billed_milestone_id = billed_milestone_id


def commercial_summary(db: Session, *, project_id: int) -> dict:
    """Compact Revision 1 / latest-approved snapshot for project registers and the Finance review header."""
    rows = list(db.scalars(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id
    ).order_by(ProjectCommercialEstimateRevision.revision_no)).all())
    if not rows:
        return {"has_commercial": False, "baseline": None, "latest_approved": None, "revision_count": 0}

    def brief(row: ProjectCommercialEstimateRevision | None) -> dict | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "revision_no": row.revision_no,
            "status": row.status,
            "is_locked": row.is_locked,
            "is_baseline": row.is_baseline,
            "currency_code": row.currency_code,
            "estimated_amount": float(row.estimated_amount),
            "billing_type_label": BILLING_TYPES.get(row.billing_type, row.billing_type),
            "payment_terms": row.payment_terms,
        }

    baseline = next((row for row in rows if row.revision_no == 1), None)
    approved = [row for row in rows if row.status == "APPROVED"]
    return {
        "has_commercial": True,
        "baseline": brief(baseline),
        "latest_approved": brief(approved[-1] if approved else None),
        "revision_count": len(rows),
    }
