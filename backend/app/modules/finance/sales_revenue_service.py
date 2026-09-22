from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.departments import department_label, normalize_department_code_or_default
from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.finance.models import FinanceProject
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkflow


INVOICE_CLOSED = "INVOICE_CLOSED"
PAYMENT_RECEIVED = "PAYMENT_RECEIVED"
PAYMENT_OVERDUE = "PAYMENT_OVERDUE"
PARTIALLY_PAID = "PARTIALLY_PAID"
PAYMENT_PENDING = "PAYMENT_PENDING"
INVOICE_RAISED = "INVOICE_RAISED"
INVOICE_DRAFT = "INVOICE_DRAFT"


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


def sales_revenue_overview(db: Session) -> dict:
    """Return one authoritative read model for Finance Sales and Revenue analytics.

    Sales is the still-open commercial pipeline. A project's commercial value remains in Sales
    until an invoice has been fully paid AND Finance closes that invoice. Revenue contains only
    payments attached to closed invoices. This keeps dashboards read-only and reuses the existing
    Commercial -> Billing -> Payment -> Invoice Close lifecycle instead of creating a second ledger.
    """

    projects = list(db.scalars(select(FinanceProject).order_by(FinanceProject.id)).unique().all())
    if not projects:
        return {"projects": [], "revenue_events": []}

    project_ids = [row.id for row in projects]
    workflows = {
        row.project_id: row
        for row in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()
    }

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

    for project in projects:
        workflow = workflows.get(project.id)
        baseline = _baseline_revision(revisions_by_project.get(project.id, []))
        project_invoices = invoices_by_project.get(project.id, [])
        open_invoices = [row for row in project_invoices if (row.status or "").upper() != INVOICE_CLOSED]
        closed_invoices = [row for row in project_invoices if (row.status or "").upper() == INVOICE_CLOSED]

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
        open_received_inr = Decimal("0")
        open_invoice_total_inr = Decimal("0")
        open_invoice_balance_inr = Decimal("0")

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
            is_closed = (invoice.status or "").upper() == INVOICE_CLOSED

            if is_closed:
                closed_revenue_inr += paid_inr if paid_inr > 0 else total_inr
            else:
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
                "payments": payment_rows,
            }
            invoice_payloads.append(invoice_row)

            if is_closed:
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

        open_sales_inr = max(sales_value_inr - closed_revenue_inr, Decimal("0"))
        outstanding_inr = max(open_sales_inr - open_received_inr, Decimal("0"))
        if sales_value_inr == 0 and open_invoice_total_inr > 0:
            open_sales_inr = open_invoice_total_inr
            outstanding_inr = open_invoice_balance_inr

        sales_date = (
            baseline.estimate_date if baseline is not None
            else project.project_award_date
            or project.start_date
            or project.created_at.date()
        )
        projected_payment_date = min((row.due_date for row in open_invoices), default=None) or project.end_date
        sales_reference = None
        if baseline is not None:
            sales_reference = baseline.quotation_reference or f"{project.project_code}-REV{baseline.revision_no}"

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
            "sales_value": _money(sales_value),
            "sales_value_inr": _money(sales_value_inr),
            "open_sales_inr": _money(open_sales_inr),
            "received_against_open_sales_inr": _money(open_received_inr),
            "outstanding_inr": _money(outstanding_inr),
            "closed_revenue_inr": _money(closed_revenue_inr),
            "sales_status": _sales_status(project_invoices, open_invoices),
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
                "notes": baseline.notes if baseline is not None else None,
            },
            "invoice_count": len(project_invoices),
            "open_invoice_count": len(open_invoices),
            "closed_invoice_count": len(closed_invoices),
            "invoices": invoice_payloads,
        })

    return {
        "projects": payload_projects,
        "revenue_events": sorted(revenue_events, key=lambda row: (row["revenue_date"], row["project_code"]), reverse=True),
    }
