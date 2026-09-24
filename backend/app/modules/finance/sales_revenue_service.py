from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.departments import department_label, normalize_department_code, normalize_department_code_or_default
from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.finance.models import FinanceProject
from app.modules.finance.visibility import exclude_hidden_projects
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkflow

logger = logging.getLogger(__name__)

INVOICE_CLOSED = "INVOICE_CLOSED"
PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
PARTIALLY_PAID = "PARTIALLY_PAID"
PAYMENT_PENDING = "PAYMENT_PENDING"
INVOICE_RAISED = "INVOICE_RAISED"
INVOICE_DRAFT = "INVOICE_DRAFT"

# Open Sales Pipeline must equal the sum of these mutually exclusive categories (INR).
OPEN_SALES_CATEGORIES: tuple[str, ...] = (
    "invoice_not_raised_inr",
    "payment_pending_inr",
    "partial_payment_inr",
    "payment_received_closure_pending_inr",
    "other_open_inr",
)

_MONEY_QUANT = Decimal("0.01")
_RECON_TOLERANCE = Decimal("0.01")


def _decimal(value: object | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _money(value: object | None) -> float:
    return float(_decimal(value))


def _invoice_total(invoice: ProjectInvoice) -> Decimal:
    return _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def _invoice_total_inr(invoice: ProjectInvoice) -> Decimal:
    if invoice.total_inr is not None:
        return _decimal(invoice.total_inr)
    total = _invoice_total(invoice)
    rate = _decimal(invoice.fx_rate_to_inr)
    if rate > 0:
        return (total * rate).quantize(Decimal("0.01"))
    if (invoice.currency or "INR").upper() == "INR":
        return total
    return Decimal("0")


def _payment_inr(payment: ProjectInvoicePayment, invoice: ProjectInvoice) -> Decimal:
    if payment.inr_equivalent is not None:
        return _decimal(payment.inr_equivalent)
    rate = _decimal(payment.fx_rate_to_inr)
    if rate > 0:
        return (_decimal(payment.amount) * rate).quantize(Decimal("0.01"))
    if (payment.payment_currency or invoice.currency or "INR").upper() == "INR":
        return _decimal(payment.amount)
    return Decimal("0")


def _baseline_revision(rows: list[ProjectCommercialEstimateRevision]) -> ProjectCommercialEstimateRevision | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: (row.revision_no, row.id))
    baseline = [row for row in ordered if bool(row.is_baseline)]
    if baseline:
        return baseline[-1]
    revision_one = [row for row in ordered if row.revision_no == 1]
    if revision_one:
        return revision_one[-1]
    approved = [row for row in ordered if (row.status or "").upper() == "APPROVED"]
    if approved:
        return approved[-1]
    return ordered[-1]


def _baseline_sales_inr(
    baseline: ProjectCommercialEstimateRevision | None,
    workflow: ProjectWorkflow | None,
) -> Decimal:
    if baseline is not None:
        if baseline.gross_inr is not None:
            return _decimal(baseline.gross_inr)
        if baseline.estimated_inr is not None:
            return _decimal(baseline.estimated_inr)
        if baseline.currency_code.upper() == "INR":
            return _decimal(baseline.expected_gross or baseline.estimated_amount)
    if workflow is not None and (workflow.currency or "INR").upper() == "INR":
        return _decimal(workflow.commercial_value)
    return Decimal("0")


def _baseline_sales_original(
    baseline: ProjectCommercialEstimateRevision | None,
    workflow: ProjectWorkflow | None,
) -> Decimal:
    if baseline is not None:
        return _decimal(baseline.expected_gross or baseline.estimated_amount)
    if workflow is not None:
        return _decimal(workflow.commercial_value)
    return Decimal("0")


def _sales_status(invoices: list[ProjectInvoice], open_invoices: list[ProjectInvoice]) -> str:
    if not invoices:
        return "Not Invoiced"
    if not open_invoices:
        return "Moved to Revenue"
    statuses = {(row.status or "").upper() for row in open_invoices}
    if PAYMENT_OVERDUE in statuses:
        return "Overdue"
    if PARTIALLY_PAID in statuses:
        return "Partially Paid"
    if PAYMENT_RECEIVED in statuses:
        return "Payment Received / Awaiting Closure"
    if PAYMENT_PENDING in statuses or INVOICE_RAISED in statuses:
        return "Payment Pending"
    if INVOICE_DRAFT in statuses:
        return "Invoice Draft"
    return "Open"


def _date_iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT, rounding=ROUND_HALF_UP)


def _empty_open_sales_categories() -> dict[str, Decimal]:
    return {key: Decimal("0") for key in OPEN_SALES_CATEGORIES}


def classify_open_invoice(
    *,
    status: str | None,
    paid_original: Decimal,
    balance_original: Decimal,
    total_original: Decimal,
) -> str:
    """Classify an open (non-revenue) invoice into an Open Sales category.

    Classification uses original-currency paid/balance so FX conversion cannot
    invent or hide a payment state. Category amounts are still booked in INR.
    """
    normalized = (status or "").strip().upper()
    if normalized == INVOICE_DRAFT or total_original <= 0:
        return "other_open_inr"
    if paid_original <= 0:
        return "payment_pending_inr"
    if balance_original > 0:
        return "partial_payment_inr"
    if paid_original >= total_original:
        return "payment_received_closure_pending_inr"
    return "other_open_inr"


def _categories_payload(categories: dict[str, Decimal]) -> dict[str, float]:
    return {key: _money(_quantize_money(categories[key])) for key in OPEN_SALES_CATEGORIES}


def _categories_sum(categories: dict[str, Decimal]) -> Decimal:
    return sum((categories[key] for key in OPEN_SALES_CATEGORIES), Decimal("0"))


def _reconcile_open_sales(
    *,
    open_sales_inr: Decimal,
    categories: dict[str, Decimal],
    project: FinanceProject | None = None,
    department_scope: str | None = None,
) -> tuple[Decimal, bool]:
    categories_sum = _categories_sum(categories)
    difference = _quantize_money(open_sales_inr - categories_sum)
    matched = abs(difference) <= _RECON_TOLERANCE
    if not matched:
        logger.error(
            "Finance KPI reconciliation failed: Department=%s ProjectId=%s ProjectCode=%s ProjectName=%s Amount=%s Expected=%s Calculated=%s Difference=%s",
            department_scope or "all",
            project.id if project is not None else None,
            project.project_code if project is not None else "N/A",
            project.project_name if project is not None else "N/A",
            open_sales_inr,
            open_sales_inr,
            categories_sum,
            difference,
        )
    return difference, matched


def _empty_kpi_summary() -> dict:
    return {
        "open_sales_inr": 0.0,
        "categories": {key: 0.0 for key in OPEN_SALES_CATEGORIES},
        "categories_sum_inr": 0.0,
        "reconciliation_difference_inr": 0.0,
        "reconciled": True,
        "realized_revenue_inr": 0.0,
        "outstanding_inr": 0.0,
        "received_against_open_sales_inr": 0.0,
        "open_invoice_total_inr": 0.0,
        "open_invoice_balance_inr": 0.0,
        "unbilled_open_sales_inr": 0.0,
        "counts": {
            "open_sales_projects": 0,
            "revenue_events": 0,
            "partial_projects": 0,
            "overdue_projects": 0,
            "payment_pending_invoices": 0,
            "partial_invoices": 0,
            "invoice_not_raised_projects": 0,
        },
        "collection": {
            "payment_pending_amount_inr": 0.0,
            "partial_payment_balance_inr": 0.0,
            "invoice_not_raised_amount_inr": 0.0,
        },
    }


def sales_revenue_overview(db: Session, *, department_scope: str | None = None) -> dict:
    """Return one authoritative read model for Finance Sales and Revenue analytics.

    Sales is the still-open commercial pipeline. A project's commercial value remains in Sales
    until an invoice has been fully paid AND Finance closes that invoice. Revenue contains only
    payments attached to closed invoices. This keeps dashboards read-only and reuses the existing
    Commercial -> Billing -> Payment -> Invoice Close lifecycle instead of creating a second ledger.

    ``department_scope`` (canonical code) restricts the payload to that performing department so
    technical PM roles never receive other departments' projects from this API.
    """

    project_query = exclude_hidden_projects(db, select(FinanceProject).order_by(FinanceProject.id))
    projects = list(db.scalars(project_query).unique().all())
    if not projects:
        return {"projects": [], "revenue_events": [], "kpi_summary": _empty_kpi_summary()}

    project_ids = [row.id for row in projects]
    workflows = {
        row.project_id: row
        for row in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()
    }

    if department_scope is not None:
        scoped = normalize_department_code(department_scope)
        if scoped is None:
            return {"projects": [], "revenue_events": [], "kpi_summary": _empty_kpi_summary()}
        projects = [
            project
            for project in projects
            if normalize_department_code_or_default(
                workflows[project.id].performing_department_code if project.id in workflows else None
            )
            == scoped
        ]
        if not projects:
            return {"projects": [], "revenue_events": [], "kpi_summary": _empty_kpi_summary()}
        project_ids = [row.id for row in projects]
        workflows = {pid: row for pid, row in workflows.items() if pid in set(project_ids)}

    revisions_by_project: dict[int, list[ProjectCommercialEstimateRevision]] = defaultdict(list)
    for row in db.scalars(
        select(ProjectCommercialEstimateRevision)
        .where(ProjectCommercialEstimateRevision.project_id.in_(project_ids))
        .order_by(ProjectCommercialEstimateRevision.project_id, ProjectCommercialEstimateRevision.revision_no)
    ).all():
        revisions_by_project[row.project_id].append(row)

    invoices_by_project: dict[int, list[ProjectInvoice]] = defaultdict(list)
    invoices = list(
        db.scalars(
            select(ProjectInvoice)
            .where(ProjectInvoice.project_id.in_(project_ids))
            .order_by(ProjectInvoice.project_id, ProjectInvoice.invoice_date, ProjectInvoice.id)
        ).all()
    )
    for invoice in invoices:
        invoices_by_project[invoice.project_id].append(invoice)

    payments_by_invoice: dict[int, list[ProjectInvoicePayment]] = defaultdict(list)
    if invoices:
        invoice_ids = [row.id for row in invoices]
        for payment in db.scalars(
            select(ProjectInvoicePayment)
            .where(ProjectInvoicePayment.invoice_id.in_(invoice_ids))
            .order_by(ProjectInvoicePayment.invoice_id, ProjectInvoicePayment.payment_date, ProjectInvoicePayment.id)
        ).all():
            payments_by_invoice[payment.invoice_id].append(payment)

    user_ids: set[int] = set()
    for workflow in workflows.values():
        if workflow.bd_owner_user_id:
            user_ids.add(workflow.bd_owner_user_id)
    for project in projects:
        profile = project.master_profile
        if profile and profile.project_manager_id:
            user_ids.add(profile.project_manager_id)
    users = {
        row.id: row
        for row in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}

    payload_projects: list[dict] = []
    revenue_events: list[dict] = []

    kpi_open_sales = Decimal("0")
    kpi_categories = _empty_open_sales_categories()
    kpi_realized_revenue = Decimal("0")
    kpi_outstanding = Decimal("0")
    kpi_open_received = Decimal("0")
    kpi_open_invoice_total = Decimal("0")
    kpi_open_invoice_balance = Decimal("0")
    kpi_unbilled = Decimal("0")
    kpi_partial_balance = Decimal("0")
    kpi_payment_pending_invoices = 0
    kpi_partial_invoices = 0
    kpi_invoice_not_raised_projects = 0
    kpi_partial_projects = 0
    kpi_overdue_projects = 0

    for project in projects:
        workflow = workflows.get(project.id)
        baseline = _baseline_revision(revisions_by_project.get(project.id, []))
        project_invoices = invoices_by_project.get(project.id, [])
        # Revenue is deliberately stricter than a status label: the invoice must be CLOSED and
        # its recorded payments must cover the full invoice total. This defensive check prevents
        # inconsistent/legacy rows from being presented as realized revenue.
        revenue_invoice_ids = {
            row.id
            for row in project_invoices
            if (row.status or "").upper() == INVOICE_CLOSED
            and sum((_decimal(payment.amount) for payment in payments_by_invoice.get(row.id, [])), Decimal("0")) >= _invoice_total(row)
        }
        closed_invoices = [row for row in project_invoices if row.id in revenue_invoice_ids]
        open_invoices = [row for row in project_invoices if row.id not in revenue_invoice_ids]

        client = project.client
        client_profile = client.master_profile if client else None
        project_profile = project.master_profile
        pm = users.get(project_profile.project_manager_id) if project_profile and project_profile.project_manager_id else None
        bd = users.get(workflow.bd_owner_user_id) if workflow and workflow.bd_owner_user_id else None

        department_code = normalize_department_code_or_default(
            workflow.performing_department_code if workflow else None
        )
        sales_currency = (
            baseline.currency_code
            if baseline is not None
            else ((workflow.currency if workflow else None) or "INR")
        ).upper()
        sales_value = _baseline_sales_original(baseline, workflow)
        sales_value_inr = _baseline_sales_inr(baseline, workflow)

        invoice_payloads: list[dict] = []
        closed_revenue_inr = Decimal("0")
        closed_sales_value_inr = Decimal("0")
        open_received_inr = Decimal("0")
        open_invoice_total_inr = Decimal("0")
        open_invoice_balance_inr = Decimal("0")
        open_categories = _empty_open_sales_categories()
        open_partial_balance_inr = Decimal("0")
        open_payment_pending_count = 0
        open_partial_count = 0

        for invoice in project_invoices:
            payments = payments_by_invoice.get(invoice.id, [])
            invoice_total = _invoice_total(invoice)
            paid_original = sum((_decimal(row.amount) for row in payments), Decimal("0"))
            balance_original = max(invoice_total - paid_original, Decimal("0"))
            total_inr = _invoice_total_inr(invoice)
            payment_inr_values = [_payment_inr(row, invoice) for row in payments]
            paid_inr = sum(payment_inr_values, Decimal("0"))
            if paid_inr == 0 and paid_original == invoice_total and total_inr > 0:
                paid_inr = total_inr
            balance_inr = max(total_inr - paid_inr, Decimal("0")) if total_inr > 0 else Decimal("0")
            qualifies_as_revenue = invoice.id in revenue_invoice_ids
            open_sales_category: str | None = None

            if qualifies_as_revenue:
                # Remove the invoice's locked accounting value from the open Sales pipeline,
                # but recognize Revenue using actual realized payment INR. Keeping those two
                # measures separate avoids FX movement corrupting open-sales balances.
                closed_sales_value_inr += total_inr
                closed_revenue_inr += paid_inr if paid_inr > 0 else total_inr
            else:
                open_sales_category = classify_open_invoice(
                    status=invoice.status,
                    paid_original=paid_original,
                    balance_original=balance_original,
                    total_original=invoice_total,
                )
                open_categories[open_sales_category] += total_inr
                if open_sales_category == "payment_pending_inr":
                    open_payment_pending_count += 1
                elif open_sales_category == "partial_payment_inr":
                    open_partial_count += 1
                    open_partial_balance_inr += balance_inr
                open_received_inr += paid_inr
                open_invoice_total_inr += total_inr
                open_invoice_balance_inr += balance_inr

            payment_rows = []
            for payment, realized_inr in zip(payments, payment_inr_values, strict=True):
                payment_rows.append({
                    "id": payment.id,
                    "payment_reference": payment.payment_reference,
                    "payment_date": payment.payment_date.isoformat(),
                    "amount": _money(payment.amount),
                    "currency": (payment.payment_currency or invoice.currency or "INR").upper(),
                    "amount_inr": _money(realized_inr),
                    "payment_mode": payment.payment_mode,
                    "comments": payment.comments,
                })

            invoice_row = {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "status": invoice.status,
                "invoice_date": invoice.invoice_date.isoformat(),
                "due_date": invoice.due_date.isoformat(),
                "currency": (invoice.currency or "INR").upper(),
                "base_amount": _money(invoice.amount),
                "tax_amount": _money(invoice.tax_amount),
                "total_amount": _money(invoice_total),
                "total_inr": _money(total_inr),
                "paid_amount": _money(paid_original),
                "paid_inr": _money(paid_inr),
                "balance": _money(balance_original),
                "balance_inr": _money(balance_inr),
                "raised_at": invoice.raised_at.isoformat() if invoice.raised_at else None,
                "closed_at": invoice.closed_at.isoformat() if invoice.closed_at else None,
                "notes": invoice.notes,
                "open_sales_category": open_sales_category,
                "payments": payment_rows,
            }
            invoice_payloads.append(invoice_row)

            if qualifies_as_revenue:
                revenue_date = (
                    max((row.payment_date for row in payments), default=None)
                    or (invoice.closed_at.date() if invoice.closed_at else None)
                    or invoice.invoice_date
                )
                event_revenue_inr = paid_inr if paid_inr > 0 else total_inr
                revenue_events.append({
                    "project_id": project.id,
                    "project_code": project.project_code,
                    "project_name": project.project_name,
                    "client_code": client.client_code if client else None,
                    "client_name": client.client_name if client else (project.client_name or ""),
                    "bd_name": (
                        (client_profile.bd_name if client_profile else None)
                        or (bd.full_name if bd else None)
                        or project.project_source_person_name
                        or "Unassigned"
                    ),
                    "department_code": department_code,
                    "department_label": department_label(department_code),
                    "project_manager_name": pm.full_name if pm else "Unassigned",
                    "currency": (invoice.currency or "INR").upper(),
                    "finance_invoice_number": invoice.invoice_number,
                    "finance_invoice_date": invoice.invoice_date.isoformat(),
                    "finance_invoice_amount": _money(invoice_total),
                    "finance_invoice_amount_inr": _money(total_inr),
                    "revenue_amount_inr": _money(event_revenue_inr),
                    "revenue_date": revenue_date.isoformat(),
                    "final_payment_date": max((row.payment_date for row in payments), default=None).isoformat() if payments else None,
                    "invoice_closed_at": invoice.closed_at.isoformat() if invoice.closed_at else None,
                    "payment_references": [row.payment_reference for row in payments],
                    "remarks": invoice.notes,
                })

        baseline_open_sales_inr = max(sales_value_inr - closed_sales_value_inr, Decimal("0"))
        # Open invoices can legitimately exceed Revision 1 after an approved change request, so
        # never hide a larger current receivable behind the original baseline value.
        open_sales_inr = max(baseline_open_sales_inr, open_invoice_total_inr)
        unbilled_open_sales_inr = max(baseline_open_sales_inr - open_invoice_total_inr, Decimal("0"))
        outstanding_inr = unbilled_open_sales_inr + open_invoice_balance_inr
        if sales_value_inr == 0 and open_invoice_total_inr > 0:
            open_sales_inr = open_invoice_total_inr
            outstanding_inr = open_invoice_balance_inr

        # Open Sales Pipeline identity: open_sales = unbilled (invoice not raised) + open invoice categories.
        open_categories["invoice_not_raised_inr"] = unbilled_open_sales_inr
        recon_difference, recon_matched = _reconcile_open_sales(
            open_sales_inr=_quantize_money(open_sales_inr),
            categories={key: _quantize_money(value) for key, value in open_categories.items()},
            project=project,
            department_scope=department_scope,
        )

        sales_date = (
            baseline.estimate_date if baseline is not None
            else project.project_award_date
            or project.start_date
            or project.created_at.date()
        )
        projected_payment_date = (
            (baseline.projected_payment_date if baseline is not None else None)
            or min((row.due_date for row in open_invoices), default=None)
            or project.end_date
        )
        sales_reference = None
        if baseline is not None:
            sales_reference = baseline.quotation_reference or f"{project.project_code}-REV{baseline.revision_no}"

        sales_status = _sales_status(project_invoices, open_invoices)
        invoice_not_raised = bool(not project_invoices and open_sales_inr > 0) or unbilled_open_sales_inr > 0
        if open_sales_inr > 0:
            kpi_open_sales += open_sales_inr
            for key in OPEN_SALES_CATEGORIES:
                kpi_categories[key] += open_categories[key]
            kpi_outstanding += outstanding_inr
            kpi_open_received += open_received_inr
            kpi_open_invoice_total += open_invoice_total_inr
            kpi_open_invoice_balance += open_invoice_balance_inr
            kpi_unbilled += unbilled_open_sales_inr
            kpi_partial_balance += open_partial_balance_inr
            kpi_payment_pending_invoices += open_payment_pending_count
            kpi_partial_invoices += open_partial_count
            if invoice_not_raised:
                kpi_invoice_not_raised_projects += 1
            if sales_status == "Partially Paid":
                kpi_partial_projects += 1
            if sales_status == "Overdue":
                kpi_overdue_projects += 1
        kpi_realized_revenue += closed_revenue_inr

        payload_projects.append({
            "project_id": project.id,
            "project_code": project.project_code,
            "project_name": project.project_name,
            "client_code": client.client_code if client else None,
            "client_name": client.client_name if client else (project.client_name or ""),
            "bd_name": (
                (client_profile.bd_name if client_profile else None)
                or (bd.full_name if bd else None)
                or project.project_source_person_name
                or "Unassigned"
            ),
            "department_code": department_code,
            "department_label": department_label(department_code),
            "project_manager_name": pm.full_name if pm else "Unassigned",
            "currency": sales_currency,
            "sales_date": sales_date.isoformat(),
            "projected_payment_date": _date_iso(projected_payment_date),
            "completion_date": _date_iso(project.end_date),
            "project_created_at": project.created_at.date().isoformat() if project.created_at else None,
            "project_status": (
                project_profile.project_status
                if project_profile is not None
                else ("active" if project.is_active else "inactive")
            ),
            "sales_value": _money(sales_value),
            "sales_value_inr": _money(sales_value_inr),
            "open_sales_inr": _money(open_sales_inr),
            "open_sales_categories": _categories_payload(open_categories),
            "open_sales_reconciliation_difference_inr": _money(recon_difference),
            "open_sales_reconciled": recon_matched,
            "unbilled_open_sales_inr": _money(unbilled_open_sales_inr),
            "partial_payment_balance_inr": _money(open_partial_balance_inr),
            "open_payment_pending_invoice_count": open_payment_pending_count,
            "open_partial_invoice_count": open_partial_count,
            "received_against_open_sales_inr": _money(open_received_inr),
            "outstanding_inr": _money(outstanding_inr),
            "closed_revenue_inr": _money(closed_revenue_inr),
            "sales_status": sales_status,
            "invoice_not_raised": invoice_not_raised,
            "sales_visible": bool(open_sales_inr > 0 or open_invoices or not closed_invoices),
            "revenue_visible": bool(closed_invoices),
            "bd_sales_invoice": {
                "reference": sales_reference,
                "revision_no": baseline.revision_no if baseline is not None else None,
                "status": baseline.status if baseline is not None else None,
                "is_locked": bool(baseline.is_locked) if baseline is not None else False,
                "date": baseline.estimate_date.isoformat() if baseline is not None else sales_date.isoformat(),
                "currency": sales_currency,
                "amount": _money(sales_value),
                "amount_inr": _money(sales_value_inr),
                "payment_terms": baseline.payment_terms if baseline is not None else None,
                "po_wo_reference": baseline.po_wo_reference if baseline is not None else (workflow.po_wo_number if workflow else None),
                "billing_type": baseline.billing_type if baseline is not None else None,
                "expected_billing_milestone": baseline.expected_billing_milestone if baseline is not None else None,
                "projected_payment_date": baseline.projected_payment_date.isoformat() if baseline is not None and baseline.projected_payment_date else None,
                "notes": baseline.notes if baseline is not None else None,
            },
            "invoice_count": len(project_invoices),
            "open_invoice_count": len(open_invoices),
            "closed_invoice_count": len(closed_invoices),
            "invoices": invoice_payloads,
        })

    kpi_categories_sum = _quantize_money(_categories_sum(kpi_categories))
    kpi_open_sales_quantized = _quantize_money(kpi_open_sales)
    kpi_difference = _quantize_money(kpi_open_sales_quantized - kpi_categories_sum)
    kpi_reconciled = abs(kpi_difference) <= _RECON_TOLERANCE
    if not kpi_reconciled:
        logger.error(
            "Finance KPI summary reconciliation failed: Department=%s ProjectId=%s ProjectCode=%s ProjectName=%s Amount=%s Expected=%s Calculated=%s Difference=%s",
            department_scope or "all",
            None,
            "ALL",
            "ALL",
            kpi_open_sales_quantized,
            kpi_open_sales_quantized,
            kpi_categories_sum,
            kpi_difference,
        )

    kpi_summary = {
        "open_sales_inr": _money(kpi_open_sales_quantized),
        "categories": _categories_payload(kpi_categories),
        "categories_sum_inr": _money(kpi_categories_sum),
        "reconciliation_difference_inr": _money(kpi_difference),
        "reconciled": kpi_reconciled,
        "realized_revenue_inr": _money(_quantize_money(kpi_realized_revenue)),
        "outstanding_inr": _money(_quantize_money(kpi_outstanding)),
        "received_against_open_sales_inr": _money(_quantize_money(kpi_open_received)),
        "open_invoice_total_inr": _money(_quantize_money(kpi_open_invoice_total)),
        "open_invoice_balance_inr": _money(_quantize_money(kpi_open_invoice_balance)),
        "unbilled_open_sales_inr": _money(_quantize_money(kpi_unbilled)),
        "counts": {
            "open_sales_projects": sum(1 for row in payload_projects if row["sales_visible"]),
            "revenue_events": len(revenue_events),
            "partial_projects": kpi_partial_projects,
            "overdue_projects": kpi_overdue_projects,
            "payment_pending_invoices": kpi_payment_pending_invoices,
            "partial_invoices": kpi_partial_invoices,
            "invoice_not_raised_projects": kpi_invoice_not_raised_projects,
        },
        "collection": {
            "payment_pending_amount_inr": _money(kpi_categories["payment_pending_inr"]),
            "partial_payment_balance_inr": _money(_quantize_money(kpi_partial_balance)),
            "invoice_not_raised_amount_inr": _money(kpi_categories["invoice_not_raised_inr"]),
        },
    }

    return {
        "projects": payload_projects,
        "revenue_events": sorted(revenue_events, key=lambda row: (row["revenue_date"], row["project_code"]), reverse=True),
        "kpi_summary": kpi_summary,
    }
