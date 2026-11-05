from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.commercial.models import (
    ProjectCommercialEstimateRevision,
    ProjectExpense,
    ProjectVendorPayment,
)

IST = timezone(timedelta(hours=5, minutes=30))


def paise(value):
    return int(
        (Decimal(str(value or 0)) * 100).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def valid_period(start, end):
    today = datetime.now(IST).date()
    if start > end or end > today:
        raise HTTPException(
            status_code=422,
            detail="Choose a valid date range ending no later than today",
        )
    return today


def build_report(start, end):
    today = valid_period(start, end)
    current = end == today

    with SessionLocal() as db:
        source = sales_revenue_overview(db, department_scope=None)
        projects = source.get("projects", [])
        ids = [int(p["project_id"]) for p in projects]
        allowed_ids = set(ids)

        approvals = defaultdict(int)
        expenses = defaultdict(list)

        if ids:
            revisions = db.scalars(
                select(ProjectCommercialEstimateRevision).where(
                    ProjectCommercialEstimateRevision.project_id.in_(ids),
                    ProjectCommercialEstimateRevision.is_baseline.is_(True),
                    ProjectCommercialEstimateRevision.status == "APPROVED",
                )
            ).all()

            for revision in revisions:
                approved_at = revision.approved_at
                if not approved_at:
                    continue
                if start <= approved_at.date() <= end:
                    amount = (
                        revision.gross_inr
                        if revision.gross_inr is not None
                        else revision.estimated_inr
                    )
                    approvals[revision.project_id] += paise(amount)

            vendor_payments = db.scalars(
                select(ProjectVendorPayment).where(
                    ProjectVendorPayment.project_id.in_(ids),
                    ProjectVendorPayment.payment_date >= start,
                    ProjectVendorPayment.payment_date <= end,
                )
            ).all()

            for payment in vendor_payments:
                expenses[payment.project_id].append({
                    "id": "vendor-" + str(payment.id),
                    "date": payment.payment_date.isoformat(),
                    "type": "Vendor payment",
                    "reference": payment.payment_reference,
                    "amount_paise": paise(payment.amount_inr),
                })

            reimbursements = db.scalars(
                select(ProjectExpense).where(
                    ProjectExpense.project_id.in_(ids),
                    ProjectExpense.reimbursed_at.is_not(None),
                    ProjectExpense.linked_vendor_invoice_id.is_(None),
                )
            ).all()

            for expense in reimbursements:
                reimbursed = expense.reimbursed_at.date()
                if start <= reimbursed <= end:
                    amount = (
                        expense.approved_amount
                        if expense.approved_amount is not None
                        else expense.amount
                    )
                    expenses[expense.project_id].append({
                        "id": "expense-" + str(expense.id),
                        "date": reimbursed.isoformat(),
                        "type": "Employee reimbursement",
                        "reference": expense.expense_code,
                        "amount_paise": paise(amount),
                    })

        rows = []
        details = {}
        summary = {
            "sales_approved": 0,
            "invoiced": 0,
            "payments_received": 0,
            "partial_payments": 0 if current else None,
            "outstanding": 0 if current else None,
            "expenses": 0,
            "bad_debts": 0 if current else None,
        }

        for source_project in projects:
            pid = int(source_project["project_id"])
            if pid not in allowed_ids:
                continue

            invoices = source_project.get("invoices") or []
            receipts_in_period = 0
            partial_receipts = 0
            invoice_amount_in_period = 0
            finance_invoices = []
            payment_history = []
            bad_debts = []

            for invoice in invoices:
                invoice_date = invoice.get("invoice_date") or ""
                if invoice_date <= end.isoformat():
                    finance_invoices.append({
                        **invoice,
                        "date": invoice_date,
                        "amount_paise": paise(invoice.get("total_inr")),
                    })

                is_draft = (
                    str(invoice.get("status") or "").upper()
                    == "INVOICE_DRAFT"
                )
                if (
                    not is_draft
                    and start.isoformat() <= invoice_date <= end.isoformat()
                ):
                    invoice_amount_in_period += paise(
                        invoice.get("total_inr")
                    )

                payments = invoice.get("payments") or []
                cash_as_of_end = sum(
                    paise(payment.get("amount_inr"))
                    for payment in payments
                    if (payment.get("payment_date") or "") <= end.isoformat()
                )

                for payment in payments:
                    payment_date = payment.get("payment_date") or ""
                    if payment_date > end.isoformat():
                        continue

                    amount = paise(payment.get("amount_inr"))
                    payment_history.append({
                        **payment,
                        "date": payment_date,
                        "invoice_number": invoice.get("invoice_number"),
                        "amount_paise": amount,
                    })

                    if start.isoformat() <= payment_date <= end.isoformat():
                        receipts_in_period += amount
                        # "Partial Payments" is receipts against invoices that are
                        # still OPEN with a collectible balance. A closed invoice
                        # can still show a gross balance when it was resolved by
                        # an approved bad debt; those receipts are ordinary cash
                        # (already counted above) and must not inflate this KPI.
                        is_closed = (
                            str(invoice.get("status") or "").upper()
                            == "INVOICE_CLOSED"
                        )
                        collectible_balance = float(
                            invoice.get("collectible_balance_inr") or 0
                        )
                        if (
                            current
                            and not is_closed
                            and cash_as_of_end > 0
                            and collectible_balance > 0
                        ):
                            partial_receipts += amount

                if current and float(invoice.get("bad_debt_inr") or 0) > 0:
                    bad_debts.append({
                        "id": "bad-debt-" + str(invoice["id"]),
                        "date": invoice_date,
                        "invoice_number": invoice.get("invoice_number"),
                        "amount_paise": paise(invoice.get("bad_debt_inr")),
                    })

            approved = approvals[pid]
            project_expenses = expenses.get(pid, [])
            expense_total = sum(
                entry["amount_paise"] for entry in project_expenses
            )

            outstanding = (
                paise(source_project.get("outstanding_inr"))
                if current else None
            )

            row = {
                "id": str(pid),
                "project_code": source_project.get("project_code"),
                "project_name": source_project.get("project_name") or "",
                "client_name": source_project.get("client_name") or "",
                "department": source_project.get("department_label") or "",
                "manager": source_project.get("project_manager_name") or "",
                "finance_status": source_project.get("sales_status") or "",
                "operational_status": source_project.get("project_status") or "",
                "sales_approved": approved,
                "payments_received": receipts_in_period,
                "outstanding": outstanding,
                "expenses": expense_total,
            }
            rows.append(row)

            summary["sales_approved"] += approved
            summary["invoiced"] += invoice_amount_in_period
            summary["payments_received"] += receipts_in_period
            summary["expenses"] += expense_total

            if current:
                summary["partial_payments"] += partial_receipts
                summary["outstanding"] += outstanding or 0
                summary["bad_debts"] += sum(
                    item["amount_paise"] for item in bad_debts
                )

            sales_invoice = source_project.get("bd_sales_invoice") or {}
            sales_invoices = []
            if sales_invoice and sales_invoice.get("reference"):
                sales_invoices.append({
                    **sales_invoice,
                    "invoice_number": sales_invoice.get("reference"),
                    "amount_paise": paise(
                        sales_invoice.get("amount_inr")
                    ),
                })

            details[str(pid)] = {
                "project": row,
                "sales_invoices": sales_invoices,
                "finance_invoices": finance_invoices,
                "payments": payment_history,
                "expenses": project_expenses,
                "bad_debts": bad_debts,
            }

        notes = [
            "Approved sales use dated baseline approval records.",
            "Receipts count invoice cash payments; applied client "
            "advances are not counted twice as cash.",
            "Expenses currently cover project-linked vendor payments "
            "and employee reimbursements, not all company overheads.",
        ]

        if not current:
            notes.append(
                "Historical outstanding, partial-payment status and "
                "bad-debt balances are unavailable until the full "
                "as-of ledger is implemented."
            )

        return {
            "summary": summary,
            "projects": rows,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notes": notes,
            "_details": details,
        }


class ManagementReportingService:
    async def get_dashboard(self, start, end):
        result = await asyncio.to_thread(build_report, start, end)
        result.pop("_details", None)
        return result

    async def get_project_detail(self, project_id, end):
        result = await asyncio.to_thread(
            build_report, date(2000, 1, 1), end
        )
        return result["_details"].get(str(project_id))


reporting_service = ManagementReportingService()