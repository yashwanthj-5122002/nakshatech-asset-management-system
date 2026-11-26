"""Client Advance <-> Project Collection / Invoice Settlement (Finance V8 Phase 5).

WHY THIS MODULE EXISTS
----------------------
A client advance is money received BEFORE billing. When Finance records it, the
project has genuinely collected money even though no invoice exists yet, so the
project-level collection view must show ``Partial Payment`` instead of
``Invoice Not Raised``. It still must never become Revenue on its own.

SINGLE SOURCE OF TRUTH
----------------------
``project_collection_summary`` is the one helper that answers "how much has this
project collected?". Every consumer (Finance Command Center cards, invoice
settlement guards, revenue recognition) reads the same breakdown:

    advance_received        = SUM(client_advance_transactions.amount_inr)      [active rows]
    advance_applied         = SUM(client_advance_transactions.adjusted_amount_inr)
    advance_unapplied       = advance_received - advance_applied
    invoice_cash_payments   = SUM(project_invoice_payments.amount)
    total_collected         = advance_received + invoice_cash_payments
    remaining_project_balance = MAX(project_value - total_collected, 0)

NO DOUBLE COUNTING
------------------
``advance_applied`` is a *memo of consumption*, never a second receipt. The
applied amount stays on the advance ledger (``adjusted_invoice_id`` /
``adjusted_amount_inr`` / ``adjusted_at``) and is deliberately NOT copied into
``project_invoice_payments``. Therefore:

* before application  -> total_collected = advance_received + invoice_cash
* after  application  -> the applied part is counted exactly once, as advance,
                         and the invoice balance shrinks by the same amount.

The invoice settlement readers (``invoice_settled_total`` and its batch twin)
add ``advance_applied`` to the invoice's cash payments so an invoice that was
fully settled with an advance is neither reported as unpaid nor closed short.

FROZEN SAFETY RULES
-------------------
* Project / commercial value is never modified.
* Invoice face value is NEVER reduced: applying an advance only settles it.
* Revenue is still recognized only for a CLOSED, fully settled invoice; this
  module never recognizes revenue and never writes to ``project_invoice_payments``.
* Employee Advance (expense claims) and operational workflow gates are untouched.
* Project/commercial value, tax, Sales, Revenue and Outstanding logic are not
  re-implemented here: this module only reads them.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.models.entities import User, utc_now
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.advance_service import (
    _load_context,
    _project_value_inr,
    _record_status_change,
    _snapshot,
    _transaction_inr,
    resolve_advance_access,
    _writable_project_context,
)
from app.modules.finance.models import FinanceProject
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment

MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0")

COLLECTION_NOT_STARTED = "Not Started"
COLLECTION_PARTIAL = "Partial Payment"
COLLECTION_COMPLETE = "Fully Collected"
INVOICE_NOT_RAISED = "Invoice Not Raised"


def _money(value: object | None) -> Decimal:
    return Decimal(str(value if value is not None else 0)).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _decimal(value: object | None) -> Decimal:
    return Decimal(str(value)) if value is not None else ZERO


# Some read-model consumers run against a deliberately reduced schema (isolated test
# engines, legacy deployments created before the client-advance tables). A missing table
# simply means "no advance has ever been applied", so the lookup degrades instead of
# failing the whole Finance read model.
_ADVANCE_TABLE_PRESENT: dict[int, bool] = {}


def _advance_table_present(db: Session) -> bool:
    bind = db.get_bind()
    key = id(bind)
    if key not in _ADVANCE_TABLE_PRESENT:
        try:
            _ADVANCE_TABLE_PRESENT[key] = inspect(bind).has_table(ClientAdvanceTransaction.__tablename__)
        except Exception:  # noqa: BLE001 - never let schema introspection break a read model
            _ADVANCE_TABLE_PRESENT[key] = False
    return _ADVANCE_TABLE_PRESENT[key]

def invoice_total_original(invoice: ProjectInvoice) -> Decimal:
    """Invoice face value in its own currency (amount + tax). Never modified here."""
    return _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def invoice_rate_to_inr(invoice: ProjectInvoice) -> Decimal:
    """Locked accounting rate for the invoice; INR invoices resolve at 1."""
    rate = _decimal(invoice.fx_rate_to_inr)
    if rate > 0:
        return rate
    return Decimal("1") if (invoice.currency or "INR").upper() == "INR" else ZERO


def invoice_total_inr(invoice: ProjectInvoice) -> Decimal:
    recorded = invoice.total_inr
    if recorded is not None:
        return _money(recorded)
    return _money(invoice_total_original(invoice) * invoice_rate_to_inr(invoice))


def advance_applied_by_invoice(db: Session, invoice_ids: list[int]) -> dict[int, Decimal]:
    """INR already applied from the client-advance ledger to each invoice.

    Reads only ``client_advance_transactions.adjusted_amount_inr``; it never
    creates or reads a duplicate ``project_invoice_payments`` row.
    """
    ids = [int(value) for value in invoice_ids]
    if not ids or not _advance_table_present(db):
        return {}
    rows = db.execute(
        select(
            ClientAdvanceTransaction.adjusted_invoice_id,
            func.sum(ClientAdvanceTransaction.adjusted_amount_inr),
        )
        .where(
            ClientAdvanceTransaction.adjusted_invoice_id.in_(ids),
            ClientAdvanceTransaction.is_reversed.is_(False),
        )
        .group_by(ClientAdvanceTransaction.adjusted_invoice_id)
    ).all()
    return {int(invoice_id): _money(total) for invoice_id, total in rows if invoice_id is not None}


def advance_applied_original_by_invoice(
    db: Session, invoices_by_id: dict[int, ProjectInvoice]
) -> dict[int, Decimal]:
    """Applied advance expressed in each invoice's own currency (for balance math)."""
    applied_inr = advance_applied_by_invoice(db, list(invoices_by_id))
    result: dict[int, Decimal] = {}
    for invoice_id, invoice in invoices_by_id.items():
        value_inr = applied_inr.get(int(invoice_id), ZERO)
        result[int(invoice_id)] = _money(value_inr / invoice_rate_to_inr(invoice))
    return result


def invoice_cash_payments_by_invoice(db: Session, invoice_ids: list[int]) -> dict[int, Decimal]:
    """Normal client payments already recorded against each invoice (original currency)."""
    ids = [int(value) for value in invoice_ids]
    if not ids:
        return {}
    rows = db.execute(
        select(ProjectInvoicePayment.invoice_id, func.sum(ProjectInvoicePayment.amount))
        .where(ProjectInvoicePayment.invoice_id.in_(ids))
        .group_by(ProjectInvoicePayment.invoice_id)
    ).all()
    return {int(invoice_id): _money(total) for invoice_id, total in rows}


def invoice_settled_total(db: Session, invoice: ProjectInvoice) -> Decimal:
    """Cash payments PLUS advance already applied to this invoice (original currency).

    This is what "settled" means for an invoice, and it is the value the existing
    payment-status and closure guards must compare against the unchanged face value.
    """
    cash = invoice_cash_payments_by_invoice(db, [invoice.id]).get(int(invoice.id), ZERO)
    applied = advance_applied_original_by_invoice(db, {int(invoice.id): invoice}).get(int(invoice.id), ZERO)
    return _money(cash + applied)
def derive_collection_status(*, total_collected: Decimal, remaining: Decimal) -> str:
    """Project-level collection label. Independent of invoice status and of Sales."""
    if remaining <= 0 and total_collected > 0:
        return COLLECTION_COMPLETE
    if total_collected > 0:
        return COLLECTION_PARTIAL
    return COLLECTION_NOT_STARTED


def project_collection_summary(
    db: Session,
    *,
    project_id: int,
    user: User,
    effective_role: str,
) -> dict:
    """Central project collection read model (Advance Collection + Project Collection).

    Access follows the existing Client Advance matrix so this endpoint can never
    widen visibility: PM roles get counts/status with every amount redacted.
    """
    access = resolve_advance_access(db, user=user, effective_role=effective_role)
    context = _load_context(db, access=access, project_id=project_id, include_details=True)
    if not context.projects:
        raise LookupError("Project not found")
    project = context.projects[0]
    snapshot = _snapshot(context, project)
    revision = context.revisions.get(project.id)
    workflow = context.workflows.get(project.id)

    invoices = list(db.scalars(
        select(ProjectInvoice)
        .where(ProjectInvoice.project_id == project.id)
        .order_by(ProjectInvoice.id)
    ).all())
    invoices_by_id = {int(invoice.id): invoice for invoice in invoices}
    applied_inr = advance_applied_by_invoice(db, list(invoices_by_id))
    applied_original = advance_applied_original_by_invoice(db, invoices_by_id)
    cash_original = invoice_cash_payments_by_invoice(db, list(invoices_by_id))

    rate_by_id = {int(invoice.id): invoice_rate_to_inr(invoice) for invoice in invoices}
    cash_inr = ZERO
    applied_total_inr = ZERO
    cash_total_original = ZERO
    applied_total_original = ZERO
    for invoice_id, invoice in invoices_by_id.items():
        rate = rate_by_id[invoice_id] or Decimal("1")
        cash_inr += cash_original.get(invoice_id, ZERO) * rate
        applied_total_inr += applied_inr.get(invoice_id, ZERO)
        cash_total_original += cash_original.get(invoice_id, ZERO)
        applied_total_original += applied_original.get(invoice_id, ZERO)

    advance_received_inr = _decimal(snapshot["received_amount"])
    advance_applied_inr = _money(applied_total_inr)
    advance_unapplied_inr = _money(max(advance_received_inr - advance_applied_inr, ZERO))
    # advance_received already includes the applied part and invoice cash never
    # includes it, so this sum counts every rupee exactly once.
    total_collected_inr = _money(advance_received_inr + cash_inr)
    project_value_inr = _money(_project_value_inr(revision, workflow))
    remaining_inr = _money(max(project_value_inr - total_collected_inr, ZERO))
    collection_status = derive_collection_status(
        total_collected=total_collected_inr, remaining=remaining_inr,
    )

    if not invoices:
        invoice_status = INVOICE_NOT_RAISED
    elif all((invoice.status or "").upper() == "INVOICE_CLOSED" for invoice in invoices):
        invoice_status = "Closed"
    else:
        invoice_status = "Open"

    visible = access.financial_amounts_visible
    invoice_payloads = []
    for invoice in invoices:
        total_original = invoice_total_original(invoice)
        settled_original = _money(cash_original.get(int(invoice.id), ZERO) + applied_original.get(int(invoice.id), ZERO))
        invoice_payloads.append({
            "invoice_id": int(invoice.id),
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "currency": invoice.currency,
            "invoice_total": _money(total_original) if visible else None,
            "cash_payments": _money(cash_original.get(int(invoice.id), ZERO)) if visible else None,
            "advance_applied": _money(applied_original.get(int(invoice.id), ZERO)) if visible else None,
            "settled_total": settled_original if visible else None,
            "balance": _money(max(total_original - settled_original, ZERO)) if visible else None,
        })

    return {
        "project_id": int(project.id),
        "project_name": snapshot["project_name"],
        "financial_amounts_visible": visible,
        # --- ADVANCE COLLECTION card ---
        "advance_expected_inr": _money(snapshot["advance_amount"]) if visible else None,
        "advance_received_inr": _money(advance_received_inr) if visible else None,
        "advance_pending_inr": _money(snapshot["pending_amount"]) if visible else None,
        "advance_status": snapshot["status"],
        "advance_status_label": snapshot["status_label"],
        # --- PROJECT COLLECTION card ---
        "project_value_inr": project_value_inr if visible else None,
        "advance_applied_inr": advance_applied_inr if visible else None,
        "advance_unapplied_inr": advance_unapplied_inr if visible else None,
        "invoice_cash_payments_inr": _money(cash_inr) if visible else None,
        "total_collected_inr": total_collected_inr if visible else None,
        "remaining_project_balance_inr": remaining_inr if visible else None,
        "collection_status": collection_status,
        "invoice_status": invoice_status,
        "invoice_count": len(invoices),
        "invoices": invoice_payloads,
    }



def invoice_balance_after_settlement(db: Session, invoice: ProjectInvoice) -> Decimal:
    return _money(max(invoice_total_original(invoice) - invoice_settled_total(db, invoice), ZERO))

def available_unapplied_advance(db: Session, *, project_id: int, revision=None) -> Decimal:
    """Received advance that has not been applied to any invoice yet (INR)."""
    rows = db.scalars(
        select(ClientAdvanceTransaction)
        .where(
            ClientAdvanceTransaction.project_id == project_id,
            ClientAdvanceTransaction.is_reversed.is_(False),
        )
        .order_by(ClientAdvanceTransaction.sequence, ClientAdvanceTransaction.id)
    ).all()
    received = ZERO
    applied = ZERO
    for row in rows:
        received += _transaction_inr(row, revision)
        if row.adjusted_amount_inr is not None:
            applied += _decimal(row.adjusted_amount_inr)
    return _money(max(received - applied, ZERO))


def apply_advance_to_invoice(
    db: Session,
    *,
    project_id: int,
    invoice_id: int,
    amount_inr: Decimal,
    actor: User,
    effective_role: str,
    remarks: str | None = None,
) -> dict:
    """Settle an invoice with money already received as a client advance.

    The advance row is never duplicated: the allocation is written back onto the
    existing ``client_advance_transactions`` rows (``adjusted_invoice_id``,
    ``adjusted_amount_inr``, ``adjusted_at``), oldest receipt first. The invoice
    face value, tax, Sales, Revenue and Outstanding are never modified; only the
    invoice's *settled* amount grows, which is what its balance/status derive from.
    """
    access, context, project = _writable_project_context(
        db, project_id=project_id, user=actor, effective_role=effective_role
    )
    revision = context.revisions.get(project.id)
    before_status = _snapshot(context, project)["status"]
    amount = _money(amount_inr)
    if amount <= 0:
        raise ValueError("Enter an amount greater than zero to apply")
    if revision is None:
        raise ValueError("Client advance terms are not configured for this project")

    invoice = db.get(ProjectInvoice, invoice_id)
    if invoice is None or int(invoice.project_id) != int(project.id):
        raise ValueError("Invoice not found for this project")
    if (invoice.status or "").upper() == "INVOICE_CLOSED":
        raise ValueError("Advance cannot be applied to a closed invoice")

    available = available_unapplied_advance(db, project_id=project.id, revision=revision)
    if amount > available:
        raise ValueError("Amount exceeds the unapplied advance available")

    invoice_total = invoice_total_original(invoice)
    balance_before = invoice_balance_after_settlement(db, invoice)
    if amount > balance_before:
        raise ValueError("Amount exceeds the outstanding invoice balance")

    rate = invoice_rate_to_inr(invoice)
    remaining_to_apply = amount
    allocations: list[dict] = []
    rows = db.scalars(
        select(ClientAdvanceTransaction)
        .where(
            ClientAdvanceTransaction.project_id == project.id,
            ClientAdvanceTransaction.is_reversed.is_(False),
        )
        .order_by(ClientAdvanceTransaction.sequence, ClientAdvanceTransaction.id)
    ).all()
    for row in rows:
        if remaining_to_apply <= 0:
            break
        if row.adjusted_invoice_id is not None:
            continue
        row_received = _transaction_inr(row, revision)
        row_applied = _decimal(row.adjusted_amount_inr)
        unapplied = _money(max(row_received - row_applied, ZERO))
        if unapplied <= 0:
            continue
        take = _money(min(unapplied, remaining_to_apply))
        row.adjusted_amount_inr = _money(row_applied + take)
        row.adjusted_invoice_id = int(invoice.id)
        row.adjusted_at = utc_now()
        remaining_to_apply = _money(remaining_to_apply - take)
        allocations.append({
            "transaction_id": int(row.id),
            "sequence": int(row.sequence),
            "amount_inr": take,
            "amount_original": _money(take / rate) if rate > 0 else ZERO,
        })
    db.flush()

    if remaining_to_apply > 0:
        raise ValueError("Amount exceeds the unapplied advance available")

# The invoice is settled by cash + applied advance; its face value is untouched.
    from app.modules.operations.lifecycle_service import (  # lazy: avoids import cycle
        _maybe_finance_closure_pending,
        _transition,
        _workflow,
        compute_invoice_payment_status,
    )

    settled = invoice_settled_total(db, invoice)
    previous_invoice_status = invoice.status
    new_invoice_status = compute_invoice_payment_status(invoice_total=invoice_total, paid_total=settled)
    invoice.status = new_invoice_status
    complete = new_invoice_status == "INVOICE_CLOSED"
    if complete:
        invoice.closed_by_id = actor.id
        invoice.closed_at = utc_now()
    workflow = _workflow(db, project.id)
    if workflow is not None:
        _transition(
            db,
            workflow=workflow,
            actor=actor,
            status=new_invoice_status,
            event_type="invoice_advance_applied",
            title="Client Advance Applied to Invoice",
            comments=f"{invoice.invoice_number}: {amount} INR applied from client advance",
        )
        if complete:
            _maybe_finance_closure_pending(db, actor=actor, workflow=workflow, exclude_invoice_id=invoice.id)
    db.flush()

    refreshed = _load_context(db, access=access, project_id=project.id, include_details=True)
    after = _snapshot(refreshed, refreshed.projects[0])
    _record_status_change(
        db,
        project_id=project.id,
        revision_id=revision.id,
        old_status=before_status,
        new_status=after["status"],
        actor=actor,
        remarks=remarks or f"Advance applied to invoice {invoice.invoice_number}",
    )
    db.flush()

    return {
        "invoice_id": int(invoice.id),
        "invoice_number": invoice.invoice_number,
        "invoice_total": _money(invoice_total),
        "currency": invoice.currency,
        "applied_inr": amount,
        "allocations": allocations,
        "previous_invoice_status": previous_invoice_status,
        "invoice_status": invoice.status,
        "invoice_settled_total": settled,
        "invoice_balance": _money(max(invoice_total - settled, ZERO)),
        "advance_status": after["status"],
        "advance_status_label": after["status_label"],
        "advance_applied_inr": _money(sum((_decimal(item["amount_inr"]) for item in allocations), ZERO)),
    }
