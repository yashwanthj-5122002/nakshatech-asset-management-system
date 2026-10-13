from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.departments import department_label, is_technical_pm_role, normalize_department_code_or_default
from app.core.roles import ADMIN_ROLE, BD_ROLE, FINANCE_ROLE, MANAGEMENT_ROLE, SOFTWARE_TEAM_ROLE
from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.finance.advance import (
    ADVANCE_STATUS_LABELS,
    ADVANCE_STATUSES,
    ClientAdvanceFollowUp,
    ClientAdvanceStatusHistory,
    ClientAdvanceTransaction,
)
from app.modules.finance.advance_schemas import ClientAdvanceFollowUpCreate, ClientAdvanceTransactionCreate
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.finance.visibility import exclude_hidden_projects
from app.modules.operations.lifecycle_models import ProjectInvoice
from app.modules.operations.models import ProjectWorkflow

_MONEY_QUANT = Decimal("0.01")
_FULL_ACCESS_ROLES = {FINANCE_ROLE, ADMIN_ROLE, SOFTWARE_TEAM_ROLE}


@dataclass(frozen=True)
class AdvanceAccess:
    kind: str
    user_id: int
    financial_amounts_visible: bool
    can_write: bool


@dataclass
class AdvanceContext:
    projects: list[FinanceProject]
    workflows: dict[int, ProjectWorkflow]
    revisions: dict[int, ProjectCommercialEstimateRevision]
    transactions: dict[int, list[ClientAdvanceTransaction]]
    followups: dict[int, list[ClientAdvanceFollowUp]]
    histories: dict[int, list[ClientAdvanceStatusHistory]]
    invoices: dict[int, list[ProjectInvoice]]
    users: dict[int, User]


def _decimal(value: object | None) -> Decimal:
    return Decimal(str(value)) if value is not None else Decimal("0")


def _money(value: object | None) -> float:
    return float(_decimal(value).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP))


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def resolve_advance_access(db: Session, *, user: User, effective_role: str) -> AdvanceAccess:
    role = (effective_role or user.role or "").strip().lower()
    if role in _FULL_ACCESS_ROLES:
        return AdvanceAccess("full", user.id, True, True)
    if role == MANAGEMENT_ROLE:
        return AdvanceAccess("management", user.id, True, False)
    if role == BD_ROLE:
        return AdvanceAccess("bd", user.id, True, False)
    if is_technical_pm_role(role):
        return AdvanceAccess("pm", user.id, False, False)

    # A PM can retain employee-role credentials while being assigned explicitly in
    # Project Master. Production/QC/QA members have no such assignment and are denied.
    is_assigned_pm = db.scalar(
        select(FinanceProjectMasterProfile.project_id)
        .where(FinanceProjectMasterProfile.project_manager_id == user.id)
        .limit(1)
    )
    if is_assigned_pm is not None:
        return AdvanceAccess("pm", user.id, False, False)
    raise PermissionError("Insufficient permission for Client Advance Payment")


def _baseline_revision(rows: list[ProjectCommercialEstimateRevision]) -> ProjectCommercialEstimateRevision | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: (row.revision_no, row.id))
    baseline = [row for row in ordered if bool(row.is_baseline)]
    if baseline:
        return baseline[-1]
    approved = [row for row in ordered if (row.status or "").upper() == "APPROVED"]
    if approved:
        return approved[-1]
    revision_one = [row for row in ordered if row.revision_no == 1]
    return revision_one[-1] if revision_one else ordered[-1]


def _terms_exist(revision: ProjectCommercialEstimateRevision | None) -> bool:
    if revision is None:
        return False
    return any((
        revision.advance_required is not None,
        bool(revision.advance_payment_type),
        revision.advance_percent is not None,
        revision.advance_amount is not None,
        revision.expected_advance_date is not None,
        revision.final_advance_date is not None,
    ))


def _advance_required(revision: ProjectCommercialEstimateRevision | None) -> bool:
    if revision is None or not _terms_exist(revision):
        return False
    if revision.advance_required is not None:
        return bool(revision.advance_required)
    return (revision.advance_payment_type or "").lower() != "no_advance"


def _expected_original(revision: ProjectCommercialEstimateRevision | None) -> Decimal:
    if revision is None or not _advance_required(revision):
        return Decimal("0")
    if revision.advance_amount is not None:
        return max(_decimal(revision.advance_amount), Decimal("0"))
    if revision.advance_percent is not None:
        base = _decimal(revision.advance_base_amount or revision.taxable_base_amount)
        return max(base * _decimal(revision.advance_percent) / Decimal("100"), Decimal("0"))
    return Decimal("0")


def _currency(revision: ProjectCommercialEstimateRevision | None) -> str:
    return ((revision.advance_currency_code if revision else None) or (revision.currency_code if revision else None) or "INR").upper()


def _expected_inr(revision: ProjectCommercialEstimateRevision | None) -> Decimal:
    if revision is None or not _advance_required(revision):
        return Decimal("0")
    if revision.advance_amount is None and revision.advance_percent is not None and revision.advance_base_amount is None:
        return max(
            _decimal(revision.base_inr) * _decimal(revision.advance_percent) / Decimal("100"),
            Decimal("0"),
        ).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    amount = _expected_original(revision)
    currency = _currency(revision)
    if currency == "INR":
        return amount.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    if currency == (revision.currency_code or "").upper() and _decimal(revision.fx_rate_to_inr) > 0:
        return (amount * _decimal(revision.fx_rate_to_inr)).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    return Decimal("0")


def _project_value_inr(
    revision: ProjectCommercialEstimateRevision | None,
    workflow: ProjectWorkflow | None,
) -> Decimal:
    if revision is not None:
        if revision.gross_inr is not None:
            return _decimal(revision.gross_inr)
        if revision.estimated_inr is not None:
            return _decimal(revision.estimated_inr)
        if (revision.currency_code or "INR").upper() == "INR":
            return _decimal(revision.expected_gross or revision.estimated_amount)
    if workflow is not None and (workflow.currency or "INR").upper() == "INR":
        return _decimal(workflow.commercial_value)
    return Decimal("0")


def _transaction_inr(
    transaction: ClientAdvanceTransaction,
    revision: ProjectCommercialEstimateRevision | None,
) -> Decimal:
    if transaction.amount_inr is not None:
        return _decimal(transaction.amount_inr)
    if (transaction.currency or "INR").upper() == "INR":
        return _decimal(transaction.amount)
    if _decimal(transaction.fx_rate) > 0:
        return _decimal(transaction.amount) * _decimal(transaction.fx_rate)
    if revision is not None and transaction.currency.upper() == revision.currency_code.upper():
        return _decimal(transaction.amount) * _decimal(revision.fx_rate_to_inr)
    return Decimal("0")


def derive_advance_status(
    *,
    advance_required: bool,
    terms_exist: bool,
    expected_inr: Decimal,
    received_inr: Decimal,
    adjusted_inr: Decimal,
    expected_date: date | None,
    final_date: date | None,
    invoice_closed: bool,
    as_of: date | None = None,
) -> str:
    today = as_of or date.today()
    expected = max(_decimal(expected_inr), Decimal("0"))
    received = max(_decimal(received_inr), Decimal("0"))
    adjusted = max(_decimal(adjusted_inr), Decimal("0"))
    pending = max(expected - received, Decimal("0"))

    if not advance_required:
        return "not_required"
    if invoice_closed and expected > 0 and received >= expected and adjusted >= expected:
        return "closed"
    if adjusted > 0:
        return "adjusted"
    if expected > 0 and received >= expected:
        return "received"
    if pending > 0 and final_date is not None and today > final_date:
        return "overdue"
    if received > 0 and received < expected:
        return "partial_received"
    if expected > 0 and expected_date is not None and today >= expected_date and received == 0:
        return "pending"
    if terms_exist:
        return "requested"
    return "not_required"


def _load_context(
    db: Session,
    *,
    access: AdvanceAccess,
    project_id: int | None = None,
    include_details: bool = False,
) -> AdvanceContext:
    query = select(FinanceProject).options(
        selectinload(FinanceProject.client).selectinload(FinanceClient.master_profile),
        selectinload(FinanceProject.master_profile),
    ).order_by(FinanceProject.id)
    if project_id is not None:
        query = query.where(FinanceProject.id == project_id)
    projects = list(db.scalars(exclude_hidden_projects(db, query)).unique().all())
    if not projects:
        return AdvanceContext([], {}, {}, {}, {}, {}, {}, {})

    project_ids = [row.id for row in projects]
    workflows = {
        row.project_id: row
        for row in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()
    }
    if access.kind == "bd":
        projects = [row for row in projects if workflows.get(row.id) and workflows[row.id].bd_owner_user_id == access.user_id]
    elif access.kind == "pm":
        projects = [
            row for row in projects
            if row.master_profile is not None and row.master_profile.project_manager_id == access.user_id
        ]
    project_ids = [row.id for row in projects]
    if not project_ids:
        return AdvanceContext([], {}, {}, {}, {}, {}, {}, {})
    workflows = {key: value for key, value in workflows.items() if key in set(project_ids)}

    revisions_by_project: dict[int, list[ProjectCommercialEstimateRevision]] = defaultdict(list)
    for row in db.scalars(
        select(ProjectCommercialEstimateRevision)
        .where(ProjectCommercialEstimateRevision.project_id.in_(project_ids))
        .order_by(ProjectCommercialEstimateRevision.project_id, ProjectCommercialEstimateRevision.revision_no)
    ).all():
        revisions_by_project[row.project_id].append(row)
    revisions = {key: value for key, rows in revisions_by_project.items() if (value := _baseline_revision(rows)) is not None}

    transactions: dict[int, list[ClientAdvanceTransaction]] = defaultdict(list)
    for row in db.scalars(
        select(ClientAdvanceTransaction)
        .where(ClientAdvanceTransaction.project_id.in_(project_ids))
        .order_by(ClientAdvanceTransaction.project_id, ClientAdvanceTransaction.payment_date, ClientAdvanceTransaction.id)
    ).all():
        transactions[row.project_id].append(row)

    invoices: dict[int, list[ProjectInvoice]] = defaultdict(list)
    for row in db.scalars(
        select(ProjectInvoice)
        .where(ProjectInvoice.project_id.in_(project_ids))
        .order_by(ProjectInvoice.project_id, ProjectInvoice.invoice_date, ProjectInvoice.id)
    ).all():
        invoices[row.project_id].append(row)

    followups: dict[int, list[ClientAdvanceFollowUp]] = defaultdict(list)
    histories: dict[int, list[ClientAdvanceStatusHistory]] = defaultdict(list)
    if include_details:
        for row in db.scalars(
            select(ClientAdvanceFollowUp)
            .where(ClientAdvanceFollowUp.project_id.in_(project_ids))
            .order_by(ClientAdvanceFollowUp.project_id, ClientAdvanceFollowUp.followup_date.desc(), ClientAdvanceFollowUp.id.desc())
        ).all():
            followups[row.project_id].append(row)
        for row in db.scalars(
            select(ClientAdvanceStatusHistory)
            .where(ClientAdvanceStatusHistory.project_id.in_(project_ids))
            .order_by(ClientAdvanceStatusHistory.project_id, ClientAdvanceStatusHistory.created_at.desc(), ClientAdvanceStatusHistory.id.desc())
        ).all():
            histories[row.project_id].append(row)

    user_ids: set[int] = set()
    for workflow in workflows.values():
        user_ids.add(workflow.bd_owner_user_id)
    for project in projects:
        if project.master_profile and project.master_profile.project_manager_id:
            user_ids.add(project.master_profile.project_manager_id)
    if include_details:
        for rows in transactions.values():
            user_ids.update(row.recorded_by_id for row in rows if row.recorded_by_id)
            user_ids.update(row.verified_by for row in rows if row.verified_by)
        for rows in followups.values():
            user_ids.update(row.created_by for row in rows if row.created_by)
        for rows in histories.values():
            user_ids.update(row.created_by for row in rows if row.created_by)
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}

    return AdvanceContext(projects, workflows, revisions, transactions, followups, histories, invoices, users)


def _snapshot(context: AdvanceContext, project: FinanceProject, *, as_of: date | None = None) -> dict:
    revision = context.revisions.get(project.id)
    workflow = context.workflows.get(project.id)
    active_transactions = [row for row in context.transactions.get(project.id, []) if not row.is_reversed]
    expected_inr = _expected_inr(revision)
    received_inr = sum((_transaction_inr(row, revision) for row in active_transactions), Decimal("0"))
    adjusted_inr = sum((_decimal(row.adjusted_amount_inr) for row in active_transactions), Decimal("0"))
    pending_inr = max(expected_inr - received_inr, Decimal("0"))
    terms_exist = _terms_exist(revision)
    required = _advance_required(revision)
    invoice_closed = any((row.status or "").upper() == "INVOICE_CLOSED" for row in context.invoices.get(project.id, []))
    status_key = derive_advance_status(
        advance_required=required,
        terms_exist=terms_exist,
        expected_inr=expected_inr,
        received_inr=received_inr,
        adjusted_inr=adjusted_inr,
        expected_date=revision.expected_advance_date if revision else None,
        final_date=revision.final_advance_date if revision else None,
        invoice_closed=invoice_closed,
        as_of=as_of,
    )
    profile = project.master_profile
    bd = context.users.get(workflow.bd_owner_user_id) if workflow else None
    pm = context.users.get(profile.project_manager_id) if profile and profile.project_manager_id else None
    department_code = normalize_department_code_or_default(
        workflow.performing_department_code if workflow else None
    )
    return {
        "project_id": project.id,
        "project_name": project.project_name,
        "client": project.client.client_name if project.client else project.client_name,
        "department": department_label(department_code),
        "department_code": department_code,
        "bd_person": bd.full_name if bd else (project.project_source_person_name or None),
        "project_manager": pm.full_name if pm else None,
        "project_value": _money(_project_value_inr(revision, workflow)),
        "advance_required": required,
        "advance_amount": _money(expected_inr),
        "received_amount": _money(received_inr),
        "pending_amount": _money(pending_inr),
        "adjusted_amount": _money(adjusted_inr),
        "advance_currency": _currency(revision),
        "expected_date": _date_iso(revision.expected_advance_date if revision else None),
        "final_date": _date_iso(revision.final_advance_date if revision else None),
        "status": status_key,
        "status_label": ADVANCE_STATUS_LABELS[status_key],
        "financial_amounts_visible": True,
    }


def _redact_for_pm(row: dict) -> dict:
    redacted = dict(row)
    for key in ("project_value", "advance_amount", "received_amount", "pending_amount", "adjusted_amount", "advance_currency"):
        redacted[key] = None
    redacted["financial_amounts_visible"] = False
    return redacted


def advance_projects(
    db: Session,
    *,
    user: User,
    effective_role: str,
    as_of: date | None = None,
) -> list[dict]:
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    context = _load_context(db, access=access)
    rows = [_snapshot(context, project, as_of=as_of) for project in context.projects]
    return rows if access.financial_amounts_visible else [_redact_for_pm(row) for row in rows]


def advance_summary(
    db: Session,
    *,
    user: User,
    effective_role: str,
    as_of: date | None = None,
) -> dict:
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    context = _load_context(db, access=access)
    rows = [_snapshot(context, project, as_of=as_of) for project in context.projects]
    counts = {status: 0 for status in ADVANCE_STATUSES}
    for row in rows:
        counts[row["status"]] += 1
    visible = access.financial_amounts_visible
    return {
        "currency": "INR" if visible else None,
        "financial_amounts_visible": visible,
        "total_advance_expected": _money(sum((_decimal(row["advance_amount"]) for row in rows), Decimal("0"))) if visible else None,
        "total_advance_received": _money(sum((_decimal(row["received_amount"]) for row in rows), Decimal("0"))) if visible else None,
        "total_advance_pending": _money(sum((_decimal(row["pending_amount"]) for row in rows), Decimal("0"))) if visible else None,
        "total_overdue_advance": _money(sum((_decimal(row["pending_amount"]) for row in rows if row["status"] == "overdue"), Decimal("0"))) if visible else None,
        "counts_by_status": counts,
    }


def advance_alert_rows(
    db: Session,
    *,
    user: User,
    effective_role: str,
    as_of: date | None = None,
) -> tuple[AdvanceAccess, list[dict]]:
    """Scoped, unredacted snapshot rows used by the Phase 4 advance alert service.

    Returns the resolved access together with the snapshot rows so callers can
    apply the same role policy as the rest of the Client Advance Payment module:
    Finance/Admin/Software Team see every project, Management and BD are scoped
    by ``_load_context`` (BD to own projects only), and Production/QC/QA are
    denied by ``resolve_advance_access`` before any row is loaded.
    """
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    context = _load_context(db, access=access)
    rows = [_snapshot(context, project, as_of=as_of) for project in context.projects]
    return access, rows


def _transaction_payload(row: ClientAdvanceTransaction, users: dict[int, User]) -> dict:
    recorder = users.get(row.recorded_by_id) if row.recorded_by_id else None
    verifier = users.get(row.verified_by) if row.verified_by else None
    return {
        "id": row.id,
        "amount": _money(row.amount),
        "currency": row.currency,
        "amount_inr": _money(row.amount_inr),
        "fx_rate": float(row.fx_rate) if row.fx_rate is not None else None,
        "payment_date": _date_iso(row.payment_date),
        "payment_mode": row.payment_mode,
        "reference_number": row.reference_number,
        "bank_reference": row.bank_reference,
        "attachment": row.attachment,
        "adjusted_amount_inr": _money(row.adjusted_amount_inr),
        "adjusted_invoice_id": row.adjusted_invoice_id,
        "recorded_by": recorder.full_name if recorder else None,
        "verified_by": verifier.full_name if verifier else None,
        "is_reversed": bool(row.is_reversed),
        "created_at": row.created_at.isoformat(),
    }


def _followup_payload(row: ClientAdvanceFollowUp, users: dict[int, User]) -> dict:
    creator = users.get(row.created_by) if row.created_by else None
    return {
        "id": row.id,
        "contact_person": row.contact_person,
        "communication_type": row.communication_type,
        "remarks": row.remarks,
        "followup_date": _date_iso(row.followup_date),
        "next_followup_date": _date_iso(row.next_followup_date),
        "created_by": creator.full_name if creator else None,
        "created_at": row.created_at.isoformat(),
    }


def _history_payload(row: ClientAdvanceStatusHistory, users: dict[int, User], *, status_only: bool = False) -> dict:
    creator = users.get(row.created_by) if row.created_by else None
    return {
        "id": row.id,
        "old_status": row.old_status,
        "old_status_label": ADVANCE_STATUS_LABELS.get(row.old_status) if row.old_status else None,
        "new_status": row.new_status,
        "new_status_label": ADVANCE_STATUS_LABELS.get(row.new_status, row.new_status.replace("_", " ").title()),
        "remarks": None if status_only else row.remarks,
        "created_by": None if status_only else (creator.full_name if creator else None),
        "created_at": row.created_at.isoformat(),
    }


def advance_project_detail(
    db: Session,
    *,
    project_id: int,
    user: User,
    effective_role: str,
    as_of: date | None = None,
) -> dict | None:
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    context = _load_context(db, access=access, project_id=project_id, include_details=True)
    if not context.projects:
        return None
    project = context.projects[0]
    snapshot = _snapshot(context, project, as_of=as_of)
    revision = context.revisions.get(project.id)
    if not access.financial_amounts_visible:
        snapshot = _redact_for_pm(snapshot)
        return {
            **snapshot,
            "payment_terms": None,
            "transactions": [],
            "followups": [],
            "status_history": [
                _history_payload(row, context.users, status_only=True)
                for row in context.histories.get(project.id, [])
            ],
        }
    return {
        **snapshot,
        "payment_terms": revision.payment_terms if revision else None,
        "transactions": [_transaction_payload(row, context.users) for row in context.transactions.get(project.id, [])],
        "followups": [_followup_payload(row, context.users) for row in context.followups.get(project.id, [])],
        "status_history": [_history_payload(row, context.users) for row in context.histories.get(project.id, [])],
    }


def advance_status_history(
    db: Session,
    *,
    project_id: int,
    user: User,
    effective_role: str,
) -> list[dict] | None:
    detail = advance_project_detail(
        db,
        project_id=project_id,
        user=user,
        effective_role=effective_role,
    )
    return None if detail is None else detail["status_history"]


def _writable_project_context(
    db: Session,
    *,
    project_id: int,
    user: User,
    effective_role: str,
) -> tuple[AdvanceAccess, AdvanceContext, FinanceProject]:
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    if not access.can_write:
        raise PermissionError("Only Finance may change Client Advance Payment records")
    context = _load_context(db, access=access, project_id=project_id, include_details=True)
    if not context.projects:
        raise LookupError("Project not found")
    return access, context, context.projects[0]


def _record_status_change(
    db: Session,
    *,
    project_id: int,
    revision_id: int | None,
    old_status: str,
    new_status: str,
    actor: User,
    remarks: str,
) -> None:
    if old_status == new_status:
        return
    db.add(ClientAdvanceStatusHistory(
        project_id=project_id,
        revision_id=revision_id,
        old_status=old_status,
        new_status=new_status,
        remarks=remarks,
        trigger_source="derived",
        created_by=actor.id,
    ))


def record_advance_transaction(
    db: Session,
    *,
    project_id: int,
    payload: ClientAdvanceTransactionCreate,
    actor: User,
    effective_role: str,
) -> dict:
    access, context, project = _writable_project_context(
        db, project_id=project_id, user=actor, effective_role=effective_role
    )
    revision = context.revisions.get(project.id)
    if revision is None or not _advance_required(revision):
        raise ValueError("Client advance terms are not configured for this project")
    before = _snapshot(context, project)
    currency = payload.currency.upper()
    if currency == "INR":
        fx_rate = Decimal("1")
    elif currency == (revision.currency_code or "").upper() and _decimal(revision.fx_rate_to_inr) > 0:
        fx_rate = _decimal(revision.fx_rate_to_inr)
    else:
        raise ValueError("No locked project FX rate is available for this advance currency")
    amount_inr = (payload.amount * fx_rate).quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)
    sequence = int(db.scalar(
        select(func.coalesce(func.max(ClientAdvanceTransaction.sequence), 0))
        .where(ClientAdvanceTransaction.project_id == project.id)
    ) or 0) + 1
    row = ClientAdvanceTransaction(
        project_id=project.id,
        client_id=project.client_id,
        revision_id=revision.id,
        sequence=sequence,
        amount=payload.amount,
        currency=currency,
        amount_inr=amount_inr,
        fx_rate=fx_rate,
        payment_date=payload.payment_date,
        payment_mode=payload.payment_mode,
        reference_number=payload.reference_number,
        bank_reference=payload.bank_reference,
        attachment=payload.attachment,
        recorded_by_id=actor.id,
    )
    db.add(row)
    db.flush()
    context = _load_context(db, access=access, project_id=project_id, include_details=True)
    after = _snapshot(context, context.projects[0])
    _record_status_change(
        db,
        project_id=project.id,
        revision_id=revision.id,
        old_status=before["status"],
        new_status=after["status"],
        actor=actor,
        remarks=f"Advance transaction {row.reference_number or row.id} recorded",
    )
    db.flush()
    return {"transaction": _transaction_payload(row, {actor.id: actor}), "status": after["status"], "status_label": after["status_label"]}


def add_advance_followup(
    db: Session,
    *,
    project_id: int,
    payload: ClientAdvanceFollowUpCreate,
    actor: User,
    effective_role: str,
) -> dict:
    _access, context, project = _writable_project_context(
        db, project_id=project_id, user=actor, effective_role=effective_role
    )
    revision = context.revisions.get(project.id)
    if revision is None or not _advance_required(revision):
        raise ValueError("Client advance terms are not configured for this project")
    row = ClientAdvanceFollowUp(
        project_id=project.id,
        client_id=project.client_id,
        revision_id=revision.id,
        contact_person=payload.contact_person,
        communication_type=payload.communication_type,
        remarks=payload.remarks,
        followup_date=date.today(),
        next_followup_date=payload.next_followup_date,
        created_by=actor.id,
    )
    db.add(row)
    db.flush()
    return _followup_payload(row, {actor.id: actor})
