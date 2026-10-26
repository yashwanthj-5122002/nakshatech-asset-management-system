"""Cash-only realization after authorized Finance closure, including write-offs."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.entities import utc_now
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.lifecycle_models import ProjectInvoiceBadDebtApproval, ProjectInvoicePayment, ProjectTimelineEvent
from app.modules.operations.lifecycle_schemas import BadDebtDecision, BadDebtProposalCreate, BadDebtRecoveryCreate, InvoiceClose, InvoicePaymentCreate
from app.modules.operations.lifecycle_service import (
    _approved_bad_debt_remaining, _invoice_cash_balance, _invoice_payload, _payment_total,
    assert_finance_closable, close_invoice, decide_bad_debt, mark_invoice_overdue,
    propose_bad_debt, record_bad_debt_recovery, record_invoice_payment,
)
from app.modules.operations.schemas import WorkflowFinanceClosure
from app.modules.operations.workflow_service import finance_close_project
from test_bad_debt_lifecycle_v8_1 import VINOD_EMAIL, _approve_both, _user
from test_finance_sales_revenue import _project


def _case(db, *, total="24148.70", payments=("20000",), decision="approved", currency="INR"):
    _, finance, project, workflow, invoice = _project(db, "CASH-WRITEOFF")
    invoice.amount = Decimal(total)
    invoice.currency = currency
    if currency=="USD":
        invoice.fx_rate_to_inr=Decimal("83.5")
        invoice.total_inr=Decimal(total)*Decimal("83.5")
    invoice.due_date = date.today()-timedelta(days=5)
    workflow.commercial_value = Decimal(total)
    workflow.currency = currency
    db.flush()
    for i, value in enumerate(payments):
        record_invoice_payment(db, actor=finance, invoice_id=invoice.id, payload=InvoicePaymentCreate(
            payment_reference=f"ACTUAL-CASH-{i+1}", payment_date=date.today(), amount=Decimal(value),
            payment_mode="bank_transfer", fx_rate_to_inr=Decimal("84") if currency=="USD" else None,
            fx_rate_mode="MANUAL_OVERRIDE" if currency=="USD" else None,
            fx_override_reason="Agreed bank realization" if currency=="USD" else None,
        ))
    mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
    debt = propose_bad_debt(db, actor=finance, invoice_id=invoice.id, payload=BadDebtProposalCreate(
        reason="Collection exhausted after documented follow-up", collection_attempts="Calls and written reminders recorded",
    ))
    if decision=="approved":
        _approve_both(db, invoice.id)
    elif decision=="rejected":
        decide_bad_debt(db, actor=_user(db,VINOD_EMAIL,"management"), invoice_id=invoice.id,
                       payload=BadDebtDecision(decision="rejected",comments="Continue collection"))
    db.flush()
    return finance, project, workflow, invoice, debt


def _overview(db, project):
    result=sales_revenue_overview(db)
    row=next(p for p in result["projects"] if p["project_id"]==project.id)
    events=[e for e in result["revenue_events"] if e["project_id"]==project.id]
    assert result["kpi_summary"]["reconciled"] is True
    assert row["open_sales_reconciled"] is True
    return result,row,events


def _reconciles(db, invoice):
    total=invoice.amount+invoice.tax_amount
    assert total == _payment_total(db,invoice.id)+max(Decimal(0),_invoice_cash_balance(db,invoice)-_approved_bad_debt_remaining(db,invoice.id))+_approved_bad_debt_remaining(db,invoice.id)


def test_finance_closed_payment_and_approved_debt_realizes_only_actual_cash():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db)
        assert invoice.status=="PAYMENT_OVERDUE"
        assert _invoice_payload(db,invoice)["can_close_invoice"] is True
        _,before,events=_overview(db,project)
        assert before["closed_revenue_inr"]==0 and not events
        assert before["open_sales_inr"]==24148.70
        assert before["bad_debt_inr"]==4148.70
        assert before["cash_received_inr"]==20000
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose(comments="Finance closure after approved write-off"))
        db.flush()
        result,row,events=_overview(db,project)
        assert invoice.status==_invoice_payload(db,invoice)["status"]=="INVOICE_CLOSED"
        assert _invoice_payload(db,invoice)["can_close_invoice"] is False
        assert row["closed_revenue_inr"]==20000
        assert row["cash_received_inr"]==20000
        assert row["open_sales_inr"]==row["outstanding_inr"]==0
        assert row["sales_visible"] is False
        assert row["bad_debt_inr"]==result["kpi_summary"]["bad_debt_inr"]==4148.70
        assert result["kpi_summary"]["realized_revenue_inr"]==20000
        assert len(events)==1 and events[0]["revenue_amount_inr"]==20000
        assert events[0]["payment_references"]==["ACTUAL-CASH-1"]
        assert invoice.amount==Decimal("24148.70") and debt.approved_amount==Decimal("4148.70")
        _reconciles(db,invoice)


@pytest.mark.parametrize("decision",["pending","rejected"])
def test_pending_or_rejected_debt_neither_closes_nor_qualifies_as_revenue(decision):
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db,decision=decision)
        assert _invoice_payload(db,invoice)["can_close_invoice"] is False
        with pytest.raises(ValueError,match="Full payment"):
            close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        # A bad legacy status label must not bypass the unresolved balance guard.
        invoice.status="INVOICE_CLOSED"
        db.flush()
        result,row,events=_overview(db,project)
        assert row["closed_revenue_inr"]==0 and not events
        assert row["bad_debt_inr"]==0
        assert row["outstanding_inr"]==4148.70
        assert row["sales_visible"] is True
        _reconciles(db,invoice)


def test_fully_written_off_closed_invoice_has_zero_revenue():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db,total="50000",payments=())
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        db.flush()
        result,row,events=_overview(db,project)
        assert row["closed_revenue_inr"]==result["kpi_summary"]["realized_revenue_inr"]==0
        assert row["cash_received_inr"]==0
        assert all(e["revenue_amount_inr"]==0 for e in events)
        assert row["open_sales_inr"]==row["outstanding_inr"]==0
        assert row["bad_debt_inr"]==result["kpi_summary"]["bad_debt_inr"]==50000
        assert db.scalar(select(func.count(ProjectInvoicePayment.id)))==0
        _reconciles(db,invoice)


def test_post_closure_recoveries_use_real_payments_and_preserve_closure_and_approvals():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db)
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        workflow.status="CLOSED"
        workflow.finance_closed_at=utc_now()
        db.flush()
        closed_at,closed_by=invoice.closed_at,invoice.closed_by_id
        project_closed_at=workflow.finance_closed_at
        approvals=list(db.scalars(select(ProjectInvoiceBadDebtApproval.id)).all())
        for i,amount in enumerate(("1000","3148.70")):
            record_bad_debt_recovery(db,actor=finance,invoice_id=invoice.id,payload=BadDebtRecoveryCreate(
                amount=Decimal(amount),payment_date=date.today()+timedelta(days=i),payment_reference=f"REAL-RECOVERY-{i+1}",payment_mode="bank_transfer",remarks="Recovered from client",
            ))
            db.flush()
            result,row,events=_overview(db,project)
            expected=21000 if i==0 else 24148.70
            remaining=3148.70 if i==0 else 0
            assert row["closed_revenue_inr"]==events[0]["revenue_amount_inr"]==expected
            assert row["cash_received_inr"]==expected
            assert row["bad_debt_inr"]==result["kpi_summary"]["bad_debt_inr"]==remaining
            assert row["open_sales_inr"]==row["outstanding_inr"]==0
            assert events[0]["revenue_date"]==(date.today()+timedelta(days=i)).isoformat()
            assert invoice.status==_invoice_payload(db,invoice)["status"]=="INVOICE_CLOSED"
            assert (invoice.closed_at,invoice.closed_by_id)==(closed_at,closed_by)
            assert workflow.status=="CLOSED" and workflow.finance_closed_at==project_closed_at
            assert debt.approved_amount==Decimal("4148.70")
            assert list(db.scalars(select(ProjectInvoiceBadDebtApproval.id)).all())==approvals
            assert db.scalar(select(func.count(ProjectInvoicePayment.id)))==i+2
            _reconciles(db,invoice)
        assert debt.status=="RECOVERED"


def test_multiple_payment_rows_are_realized_exactly_once():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db,payments=("12000","8000"))
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        db.flush()
        result,row,events=_overview(db,project)
        assert row["closed_revenue_inr"]==events[0]["revenue_amount_inr"]==20000
        assert events[0]["payment_references"]==["ACTUAL-CASH-1","ACTUAL-CASH-2"]
        assert db.scalar(select(func.count(ProjectInvoicePayment.id)))==2
        _reconciles(db,invoice)


def test_closed_fx_invoice_uses_payment_realization_and_locked_bad_debt_rate():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db,total="1000",payments=("600",),currency="USD")
        invoice.fx_rate_to_inr=Decimal("83.5")
        invoice.total_inr=Decimal("83500")
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        db.flush()
        result,row,events=_overview(db,project)
        assert row["closed_revenue_inr"]==events[0]["revenue_amount_inr"]==50400  # 600 USD realized at 84
        assert row["bad_debt_inr"]==result["kpi_summary"]["bad_debt_inr"]==33400  # 400 USD locked at 83.5
        assert row["open_sales_inr"]==row["outstanding_inr"]==0
        assert row["invoices"][0]["payments"][0]["amount_inr"]==50400
        _reconciles(db,invoice)


def test_finance_project_closure_finalizes_resolved_invoice_after_existing_gates():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db)
        for status in ("CLIENT_ACCEPTED","READY_FOR_BILLING"):
            db.add(ProjectTimelineEvent(project_id=project.id,event_key=f"test:{status}",event_type=status.lower(),title=status,status=status,actor_user_id=finance.id))
        db.flush()
        assert_finance_closable(db,workflow=workflow)
        finance_close_project(db,actor=finance,project_id=project.id,payload=WorkflowFinanceClosure(remarks="Finance confirms resolution"))
        db.flush()
        assert workflow.status=="CLOSED" and workflow.finance_closed_at is not None
        assert invoice.status=="INVOICE_CLOSED" and invoice.closed_by_id==finance.id and invoice.closed_at is not None
        assert _overview(db,project)[1]["closed_revenue_inr"]==20000


def test_existing_finance_closed_project_can_close_omitted_invoice_without_reopening():
    with SessionLocal() as db:
        finance,project,workflow,invoice,debt=_case(db)
        workflow.status="CLOSED"
        workflow.finance_closed_at=utc_now()
        original=workflow.finance_closed_at
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose(comments="Complete omitted invoice closure"))
        db.flush()
        assert workflow.status=="CLOSED" and workflow.finance_closed_at==original
        assert invoice.status=="INVOICE_CLOSED"
        count=db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.event_type=="invoice_closed"))
        close_invoice(db,actor=finance,invoice_id=invoice.id,payload=InvoiceClose())
        db.flush()
        assert db.scalar(select(func.count(ProjectTimelineEvent.id)).where(ProjectTimelineEvent.event_type=="invoice_closed"))==count
        assert _overview(db,project)[1]["closed_revenue_inr"]==20000
