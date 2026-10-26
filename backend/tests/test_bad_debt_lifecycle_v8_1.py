from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import Base, SessionLocal
from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.lifecycle_models import (
    ProjectInvoice,
    ProjectInvoiceBadDebt,
    ProjectInvoicePayment,
)
from app.modules.operations.lifecycle_schemas import (
    BadDebtDecision,
    BadDebtProposalCreate,
    BadDebtRecoveryCreate,
    FeedbackRequestCreate,
    FeedbackResponseCreate,
    InvoiceDraftCreate,
    InvoicePaymentCreate,
    InvoiceRaise,
)
from app.modules.operations.lifecycle_service import (
    CLIENT_ACCEPTANCE_PENDING_BD,
    FEEDBACK_NOT_SENT,
    READY_FOR_BILLING,
    _approved_bad_debt_remaining,
    _invoice_payload,
    _payment_total,
    confirm_client_acceptance,
    create_feedback_request,
    create_invoice_draft,
    decide_bad_debt,
    list_bad_debts,
    mark_invoice_overdue,
    propose_bad_debt,
    raise_invoice,
    record_bad_debt_recovery,
    record_invoice_payment,
    submit_feedback_response,
)
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str) -> User:
    # Idempotent: the two authorized Bad Debt approvers are shared by every test.
    existing = db.scalar(select(User).where(User.email == email))
    if existing is not None:
        return existing
    row = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="test-only",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


# The two authorized management approvers (identity comes from
# app.core.management_access → vinod@ / chethan@; never a hard-coded id).
VINOD_EMAIL = "vinod@nakshatech.com"
CHETHAN_EMAIL = "chethan@nakshatech.com"


def _approve_both(db, invoice_id: int, comments: str = "Approved after collection review"):
    """DUAL approval: the write-off only becomes effective after BOTH approvers agree."""
    first = decide_bad_debt(
        db, actor=_user(db, VINOD_EMAIL, "management"), invoice_id=invoice_id,
        payload=BadDebtDecision(decision="approved", comments=comments))
    db.flush()
    assert first.status == "PROPOSED", "one approval must not finalize the write-off"
    second = decide_bad_debt(
        db, actor=_user(db, CHETHAN_EMAIL, "management"), invoice_id=invoice_id,
        payload=BadDebtDecision(decision="approved", comments=comments))
    db.flush()
    return second


def _overdue_invoice(db, suffix: str, due_days: int = 5):
    bd = _user(db, f"bd.baddebt.{suffix}@nakshatech.com", "bd")
    finance = _user(db, f"finance.baddebt.{suffix}@nakshatech.com", "finance")
    management = _user(db, VINOD_EMAIL, "management")
    client = FinanceClient(
        client_code=f"BD-{suffix}",
        client_name=f"Bad Debt Client {suffix}",
        contact_person_name="Contact",
        contact_person_phone="9999999999",
        source_team="bd",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=bd.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"BD-P-{suffix}",
        project_name=f"Bad Debt Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date.today() - timedelta(days=60),
        end_date=date.today() - timedelta(days=10),
        created_by_id=bd.id,
    )
    db.add(project)
    db.flush()
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=bd.id,
        performing_department_code="lidar",
        status=READY_FOR_BILLING,
        commercial_value=Decimal("10000"),
        currency="INR",
        created_by_id=bd.id,
        updated_by_id=bd.id,
    )
    db.add(workflow)
    db.flush()
    invoice = create_invoice_draft(
        db,
        actor=finance,
        project_id=project.id,
        payload=InvoiceDraftCreate(
            invoice_number=f"INV-BD-{suffix}",
            invoice_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=due_days),
            amount=Decimal("10000"),
            tax_amount=Decimal("0"),
            currency="INR",
            payment_terms="30 days",
        ),
    )
    raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
    db.flush()
    return finance, management, project, invoice


def test_bad_debt_is_separate_from_payment_and_revenue_and_removes_collectible_outstanding():
    with SessionLocal() as db:
        finance, management, project, invoice = _overdue_invoice(db, "PARTIAL")
        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="BD-PARTIAL-4000",
                payment_date=date.today() - timedelta(days=10),
                amount=Decimal("4000"),
                payment_mode="bank_transfer",
            ),
        )
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        proposal = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Client has not settled the remaining balance",
                collection_attempts="Three emails and two calls recorded",
                last_followup_date=date.today() - timedelta(days=1),
            ),
        )
        assert proposal.status == "PROPOSED"
        assert proposal.proposed_amount == Decimal("6000")

        approved = _approve_both(db, invoice.id, "Approved after collection review")
        db.flush()
        assert approved.status == "APPROVED"
        assert approved.approved_amount == Decimal("6000")
        assert db.get(ProjectInvoiceBadDebt, approved.id) is not None

        # No fake payment is created for the write-off and the invoice stays overdue.
        assert invoice.status == "PAYMENT_OVERDUE"

        overview = sales_revenue_overview(db)
        row = next(item for item in overview["projects"] if item["project_id"] == project.id)
        assert row["bad_debt_inr"] == 6000.0
        assert row["outstanding_inr"] == 0.0
        assert row["closed_revenue_inr"] == 0.0
        assert not any(item["project_id"] == project.id for item in overview["revenue_events"])
        assert overview["kpi_summary"]["bad_debt_inr"] >= 6000.0
        db.rollback()


def test_bad_debt_requires_overdue_invoice_and_management_decision():
    with SessionLocal() as db:
        finance, management, _, invoice = _overdue_invoice(db, "GUARD")
        with pytest.raises(ValueError, match="Mark the invoice Payment Overdue"):
            propose_bad_debt(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtProposalCreate(
                    reason="Collection exhausted",
                    collection_attempts="Repeated follow-up",
                ),
            )
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        proposal = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Collection exhausted",
                collection_attempts="Repeated follow-up",
            ),
        )
        rejected = decide_bad_debt(
            db,
            actor=management,
            invoice_id=invoice.id,
            payload=BadDebtDecision(decision="rejected", comments="Continue collection for another cycle"),
        )
        assert proposal.id == rejected.id
        assert rejected.status == "REJECTED"
        assert rejected.approved_amount is None
        db.rollback()


def test_positive_feedback_waits_for_bd_confirmation_before_finance_billing_handoff():
    with SessionLocal() as db:
        bd = _user(db, "bd.feedback.confirm@nakshatech.com", "bd")
        client = FinanceClient(
            client_code="FDBD-1",
            client_name="Feedback Client",
            client_email="client.feedback@example.com",
            contact_person_name="Client Contact",
            contact_person_phone="9999999999",
            source_team="bd",
            source_person_name=bd.full_name,
            is_active=True,
            created_by_id=bd.id,
        )
        db.add(client)
        db.flush()
        project = FinanceProject(
            project_code="FDBD-P-1",
            project_name="Feedback Confirmation Project",
            client_id=client.id,
            client_name=client.client_name,
            start_date=date.today() - timedelta(days=30),
            end_date=date.today(),
            created_by_id=bd.id,
        )
        db.add(project)
        db.flush()
        workflow = ProjectWorkflow(
            project_id=project.id,
            bd_owner_user_id=bd.id,
            performing_department_code="lidar",
            status=FEEDBACK_NOT_SENT,
            commercial_value=Decimal("25000"),
            currency="INR",
            created_by_id=bd.id,
            updated_by_id=bd.id,
        )
        db.add(workflow)
        db.flush()
        _, token, _ = create_feedback_request(
            db,
            actor=bd,
            project_id=project.id,
            payload=FeedbackRequestCreate(message="Please confirm delivery", expiry_days=14),
        )
        response = submit_feedback_response(
            db,
            token=token,
            payload=FeedbackResponseCreate(
                response_type="accepted",
                comments="Delivery accepted",
                client_name="Client Contact",
                client_email="client.feedback@example.com",
            ),
        )
        db.flush()
        assert workflow.status == CLIENT_ACCEPTANCE_PENDING_BD
        assert response.classification_status == "pending_bd"

        confirm_client_acceptance(db, actor=bd, response_id=response.id)
        db.flush()
        assert workflow.status == READY_FOR_BILLING
        assert response.classification_status == "confirmed"
        assert response.classified_as == "accepted"
        db.rollback()


# ===========================================================================
# V8.1 manual UAT: BADDEBT4586 / invoice 465GHJK6
#
# The badge Finance reads inside the invoice card must follow the overdue rule
# (due date passed + open balance + not settled) for EVERY stored status. A
# persisted PAYMENT_OVERDUE must never fall back to the payment-derived
# PAYMENT PENDING, which is what stopped the Bad Debt action from rendering.
# ===========================================================================


def test_invoice_detail_status_follows_the_overdue_rule_not_the_stored_status():
    with SessionLocal() as db:
        finance, _, _, invoice = _overdue_invoice(db, "DETAIL", due_days=-3)

        # Due date still in the future -> not overdue, whatever the workflow says.
        payload = _invoice_payload(db, invoice)
        assert payload["stored_status"] == "PAYMENT_PENDING"
        assert payload["status"] == "PAYMENT_PENDING"
        assert payload["days_overdue"] == 0

        # Due date passes while the stored status is still PAYMENT PENDING.
        invoice.due_date = date.today() - timedelta(days=2)
        db.flush()
        payload = _invoice_payload(db, invoice)
        assert payload["stored_status"] == "PAYMENT_PENDING"
        assert payload["status"] == "PAYMENT_OVERDUE"
        assert payload["days_overdue"] == 2
        assert payload["balance"] == 10000.0
        assert payload["collectible_balance"] == 10000.0

        # The UAT regression: once PAYMENT OVERDUE is persisted it must stay
        # PAYMENT OVERDUE instead of reverting to the payment-derived state.
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        db.flush()
        payload = _invoice_payload(db, invoice)
        assert payload["stored_status"] == "PAYMENT_OVERDUE"
        assert payload["status"] == "PAYMENT_OVERDUE"
        assert payload["days_overdue"] == 2
        db.rollback()


def test_partial_payment_invoice_is_overdue_and_still_accepts_payments():
    with SessionLocal() as db:
        finance, _, _, invoice = _overdue_invoice(db, "PARTPAY")
        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="BD-PP-4000",
                payment_date=date.today() - timedelta(days=10),
                amount=Decimal("4000"),
                payment_mode="bank_transfer",
            ),
        )
        db.flush()
        payload = _invoice_payload(db, invoice)
        assert payload["stored_status"] == "PARTIALLY_PAID"
        assert payload["status"] == "PAYMENT_OVERDUE"
        assert payload["balance"] == 6000.0
        assert payload["days_overdue"] == 5

        # Escalation is optional: the normal Record Payment path keeps working
        # on an overdue invoice and no synthetic settlement is ever created.
        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="BD-PP-6000",
                payment_date=date.today(),
                amount=Decimal("6000"),
                payment_mode="upi",
            ),
        )
        db.flush()
        assert _payment_total(db, invoice.id) == Decimal("10000")
        assert invoice.status == "INVOICE_CLOSED"
        assert _invoice_payload(db, invoice)["status"] == "INVOICE_CLOSED"
        db.rollback()


def test_duplicate_bad_debt_proposal_is_blocked_until_management_decides():
    with SessionLocal() as db:
        finance, management, _, invoice = _overdue_invoice(db, "DUP")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        first = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Collection exhausted after the due date",
                collection_attempts="Calls, emails and a written reminder",
            ),
        )
        db.flush()

        with pytest.raises(ValueError, match="already pending Management review"):
            propose_bad_debt(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtProposalCreate(
                    reason="Second attempt while the first is pending",
                    collection_attempts="Calls, emails and a written reminder",
                ),
            )

        decide_bad_debt(
            db,
            actor=management,
            invoice_id=invoice.id,
            payload=BadDebtDecision(decision="rejected", comments="Keep collecting one more cycle"),
        )
        db.flush()
        again = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Second attempt after Management rejection",
                collection_attempts="Escalated to the accounts team",
            ),
        )
        db.flush()
        assert again.id == first.id
        assert again.status == "PROPOSED"
        assert again.recovered_amount == Decimal("0")
        db.rollback()


def test_partial_bad_debt_write_off_never_exceeds_the_collectible_balance():
    with SessionLocal() as db:
        finance, management, project, invoice = _overdue_invoice(db, "PARTIALWO")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)

        with pytest.raises(ValueError, match="cannot exceed the outstanding collectible balance"):
            propose_bad_debt(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtProposalCreate(
                    reason="Write off more than the client owes",
                    collection_attempts="Not applicable",
                    proposed_amount=Decimal("99999"),
                ),
            )
        with pytest.raises(ValueError, match="greater than 0"):
            propose_bad_debt(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtProposalCreate(
                    reason="Zero write off",
                    collection_attempts="Not applicable",
                    proposed_amount=Decimal("0"),
                ),
            )

        proposal = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Write off only the disputed portion",
                collection_attempts="Three calls and two escalation emails",
                proposed_amount=Decimal("3000"),
            ),
        )
        assert proposal.proposed_amount == Decimal("3000")

        approved = _approve_both(db, invoice.id, "Approved the disputed portion only")
        db.flush()
        assert approved.status == "APPROVED"
        assert approved.approved_amount == Decimal("3000")
        # A partial write-off leaves a normal collectible balance, so the
        # project must NOT jump to Finance Closure Pending yet.
        assert db.get(ProjectWorkflow, project.id).status == "PAYMENT_OVERDUE"

        overview = sales_revenue_overview(db)
        row = next(item for item in overview["projects"] if item["project_id"] == project.id)
        assert row["bad_debt_inr"] == 3000.0
        assert row["outstanding_inr"] == 7000.0
        assert row["closed_revenue_inr"] == 0.0
        assert _approved_bad_debt_remaining(db, invoice.id) == Decimal("3000")
        assert not any(item["project_id"] == project.id for item in overview["revenue_events"])
        db.rollback()


def test_approved_partial_bad_debt_keeps_collectible_payment_and_recovery_separate():
    with SessionLocal() as db:
        finance, management, project, invoice = _overdue_invoice(db, "SPLITCOLLECT")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        proposal = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Only part of the overdue balance is being written off",
                collection_attempts="Collection team confirmed the remaining portion is still collectible",
                proposed_amount=Decimal("3000"),
            ),
        )
        _approve_both(db, invoice.id, "Approve partial write-off only")
        db.flush()
        assert proposal.approved_amount == Decimal("3000")

        # Only INR 7,000 is still ordinarily collectible. Trying to push any of
        # the written-off INR 3,000 through Record Payment must be rejected.
        with pytest.raises(ValueError, match="collectible balance"):
            record_invoice_payment(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=InvoicePaymentCreate(
                    payment_reference="TOO-MUCH-COLLECTIBLE",
                    payment_date=date.today(),
                    amount=Decimal("7001"),
                    payment_mode="bank_transfer",
                ),
            )

        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="COLLECTIBLE-7000",
                payment_date=date.today(),
                amount=Decimal("7000"),
                payment_mode="bank_transfer",
            ),
        )
        db.flush()
        assert _payment_total(db, invoice.id) == Decimal("7000")
        assert _approved_bad_debt_remaining(db, invoice.id) == Decimal("3000")

        overview = sales_revenue_overview(db)
        project_row = next(item for item in overview["projects"] if item["project_id"] == project.id)
        assert project_row["outstanding_inr"] == 0.0
        assert project_row["bad_debt_inr"] == 3000.0
        assert project_row["closed_revenue_inr"] == 0.0

        # The written-off portion can only come back through the explicit
        # recovery path, which records real cash and updates recovery history.
        record_bad_debt_recovery(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtRecoveryCreate(
                amount=Decimal("3000"),
                payment_date=date.today(),
                payment_reference="RECOVER-WRITEOFF-3000",
                payment_mode="bank_transfer",
            ),
        )
        db.flush()
        bad_debt = db.get(ProjectInvoiceBadDebt, proposal.id)
        assert bad_debt is not None
        assert bad_debt.status == "RECOVERED"
        assert bad_debt.recovered_amount == Decimal("3000")
        assert _payment_total(db, invoice.id) == Decimal("10000")
        db.rollback()


def test_recovery_books_real_cash_partial_then_full_and_preserves_history():
    with SessionLocal() as db:
        finance, management, project, invoice = _overdue_invoice(db, "RECOVER")
        sales_before = sales_revenue_overview(db)
        sales_before_value = next(
            item["sales_value_inr"] for item in sales_before["projects"] if item["project_id"] == project.id
        )

        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="BD-RCV-4000",
                payment_date=date.today() - timedelta(days=10),
                amount=Decimal("4000"),
                payment_mode="bank_transfer",
            ),
        )
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        proposal = propose_bad_debt(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtProposalCreate(
                reason="Client stopped responding after the due date",
                collection_attempts="Five calls, four emails, one written notice",
                last_followup_date=date.today() - timedelta(days=3),
            ),
        )
        assert proposal.proposed_amount == Decimal("6000")
        approved = _approve_both(db, invoice.id, "Approved write-off after review")
        db.flush()
        assert approved.status == "APPROVED"
        assert approved.approved_amount == Decimal("6000")

        overview = sales_revenue_overview(db)
        row = next(item for item in overview["projects"] if item["project_id"] == project.id)
        assert row["sales_value_inr"] == sales_before_value  # Sales history untouched
        assert row["bad_debt_inr"] == 6000.0
        assert row["outstanding_inr"] == 0.0
        assert row["closed_revenue_inr"] == 0.0  # write-off is NOT Revenue

        # A full approved write-off has no ordinary collectible balance left.
        # Finance must use the Recovery path for later cash so the Bad Debt
        # history is updated instead of silently booking an unrelated payment.
        with pytest.raises(ValueError, match="use Bad Debt Recovery"):
            record_invoice_payment(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=InvoicePaymentCreate(
                    payment_reference="WRONG-NORMAL-PAYMENT",
                    payment_date=date.today(),
                    amount=Decimal("1"),
                    payment_mode="bank_transfer",
                ),
            )

        # --- partial recovery: real cash, one new payment row, no duplicate settlement
        record_bad_debt_recovery(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtRecoveryCreate(
                amount=Decimal("2000"),
                payment_date=date.today(),
                payment_reference="UTR-RECOV-1",
                payment_mode="bank_transfer",
                remarks="Client part payment against the write-off",
            ),
        )
        db.flush()
        row = db.get(ProjectInvoiceBadDebt, approved.id)
        assert row is not None  # original Bad Debt record preserved
        assert row.status == "APPROVED"  # not yet fully recovered
        assert row.proposed_amount == Decimal("6000")  # original proposal history intact
        assert row.reason == "Client stopped responding after the due date"
        assert row.recovered_amount == Decimal("2000")
        assert _approved_bad_debt_remaining(db, invoice.id) == Decimal("4000")

        payments = list(
            db.scalars(
                select(ProjectInvoicePayment).where(ProjectInvoicePayment.invoice_id == invoice.id)
            ).all()
        )
        assert len(payments) == 2  # one original payment + one recovery, never synthetic
        assert sum((p.amount for p in payments), Decimal("0")) == Decimal("6000")
        assert invoice.status == "PARTIALLY_PAID"

        overview = sales_revenue_overview(db)
        row = next(item for item in overview["projects"] if item["project_id"] == project.id)
        assert row["sales_value_inr"] == sales_before_value
        assert row["bad_debt_inr"] == 4000.0  # write-off shrank by the real cash
        assert row["outstanding_inr"] == 0.0
        assert row["closed_revenue_inr"] == 0.0
        assert not any(item["project_id"] == project.id for item in overview["revenue_events"])
        # Partial recovery does not revoke Management's write-off. The remaining
        # cash balance is still fully covered by the remaining approved Bad Debt,
        # so Finance Closure Pending eligibility must be restored.
        assert db.get(ProjectWorkflow, project.id).status == "FINANCE_CLOSURE_PENDING"

        register = {item["invoice_id"]: item for item in list_bad_debts(db)}
        entry = register[invoice.id]
        assert entry["status"] == "APPROVED"
        assert entry["proposed_amount"] == 6000.0
        assert entry["recovered_amount"] == 2000.0
        assert entry["unrecovered_amount"] == 4000.0
        assert entry["proposed_by_name"] is not None
        assert entry["reviewed_by_name"] is not None

        # --- more cash than is left unrecovered must be refused
        with pytest.raises(ValueError, match="cannot exceed the unrecovered Bad Debt balance"):
            record_bad_debt_recovery(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtRecoveryCreate(
                    amount=Decimal("5000"),
                    payment_date=date.today(),
                    payment_reference="UTR-RECOV-TOO-MUCH",
                    payment_mode="upi",
                ),
            )

        # --- full recovery
        record_bad_debt_recovery(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=BadDebtRecoveryCreate(
                amount=Decimal("4000"),
                payment_date=date.today(),
                payment_reference="UTR-RECOV-2",
                payment_mode="upi",
            ),
        )
        db.flush()
        row = db.get(ProjectInvoiceBadDebt, approved.id)
        assert row.status == "RECOVERED"
        assert row.recovered_amount == Decimal("6000")
        assert row.approved_amount == Decimal("6000")  # history never rewritten
        # Dual approval: the FINAL reviewer recorded on the case is the second approver.
        assert row.reviewed_by_id == _user(db, CHETHAN_EMAIL, "management").id
        assert _approved_bad_debt_remaining(db, invoice.id) == Decimal("0")

        payments = list(
            db.scalars(
                select(ProjectInvoicePayment).where(ProjectInvoicePayment.invoice_id == invoice.id)
            ).all()
        )
        assert len(payments) == 3
        assert sum((p.amount for p in payments), Decimal("0")) == Decimal("10000")
        assert _payment_total(db, invoice.id) == Decimal("10000")
        assert invoice.status == "INVOICE_CLOSED"

        with pytest.raises(ValueError, match="already fully recovered"):
            record_bad_debt_recovery(
                db,
                actor=finance,
                invoice_id=invoice.id,
                payload=BadDebtRecoveryCreate(
                    amount=Decimal("1"),
                    payment_date=date.today(),
                    payment_reference="UTR-RECOV-AGAIN",
                    payment_mode="upi",
                ),
            )

        register = {item["invoice_id"]: item for item in list_bad_debts(db)}
        entry = register[invoice.id]
        assert entry["status"] == "RECOVERED"
        assert entry["recovered_amount"] == 6000.0
        assert entry["unrecovered_amount"] == 0.0
        assert entry["net_bad_debt"] == 0.0
        db.rollback()


# ===========================================================================
# Role gating on the HTTP layer: only Finance may propose / recover, only
# Management may decide, and every operational role is refused with 403.
# ===========================================================================

_HTTP_OPERATIONAL_ROLES = ("bd", "ortho", "lidar", "employee", "production", "qc", "qa")


def _build_bad_debt_app():
    from fastapi import FastAPI
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.database import get_db
    from app.modules.operations.lifecycle_router import router as lifecycle_router

    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        ids = {}
        for role in ("finance", "management", *_HTTP_OPERATIONAL_ROLES):
            user = User(
                email=f"bdduty.{role}@nakshatech.com",
                full_name=role.title(),
                password_hash="test-only",
                role=role,
                is_active=True,
            )
            db.add(user)
            db.flush()
            ids[role] = user.id
        # The two authorized Bad Debt approvers (dual approval requirement).
        for key, email in (("vinod", VINOD_EMAIL), ("chethan", CHETHAN_EMAIL)):
            approver = User(
                email=email,
                full_name=key.title(),
                password_hash="test-only",
                role="management",
                is_active=True,
            )
            db.add(approver)
            db.flush()
            ids[key] = approver.id
        db.commit()

    app = FastAPI()
    app.include_router(lifecycle_router, prefix="/api")

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    return app, TestingSession, ids


class _RoleClient:
    """A TestClient bound to one role.

    ``app.dependency_overrides`` is shared by every client built on the same
    app, so the auth override has to be re-applied immediately before each
    request instead of once when the client is constructed.
    """

    def __init__(self, app, TestingSession, role: str, ids: dict[str, int]) -> None:
        from app.api.dependencies import get_current_auth

        self._app = app
        self._TestingSession = TestingSession
        self._role = role
        self._ids = ids
        self._get_current_auth = get_current_auth

    def _request(self, method: str, url: str, **kwargs):
        from fastapi.testclient import TestClient

        from app.api.dependencies import CurrentAuth

        def override_auth() -> CurrentAuth:
            with self._TestingSession() as db:
                user = db.get(User, self._ids[self._role])
                db.expunge(user)
            return CurrentAuth(user=user, claims={"role": user.role}, session=None)

        self._app.dependency_overrides[self._get_current_auth] = override_auth
        return TestClient(self._app).request(method, url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._request("POST", url, **kwargs)

    def get(self, url: str, **kwargs):
        return self._request("GET", url, **kwargs)


def _client_for_role(app, TestingSession, role: str, ids: dict[str, int]) -> _RoleClient:
    return _RoleClient(app, TestingSession, role, ids)


def _seed_http_overdue_invoice(TestingSession, ids: dict[str, int], suffix: str) -> tuple[int, int]:
    with TestingSession() as db:
        finance_id = ids["finance"]
        bd_id = ids["bd"]
        client = FinanceClient(
            client_code=f"BDHTTP-{suffix}",
            client_name=f"Bad Debt HTTP Client {suffix}",
            contact_person_name="Contact",
            contact_person_phone="9999999999",
            source_team="bd",
            source_person_name="BD",
            is_active=True,
            created_by_id=bd_id,
        )
        db.add(client)
        db.flush()
        project = FinanceProject(
            project_code=f"BDHTTP-P-{suffix}",
            project_name=f"Bad Debt HTTP Project {suffix}",
            client_id=client.id,
            client_name=client.client_name,
            start_date=date.today() - timedelta(days=60),
            end_date=date.today() - timedelta(days=10),
            created_by_id=bd_id,
        )
        db.add(project)
        db.flush()
        db.add(
            ProjectWorkflow(
                project_id=project.id,
                bd_owner_user_id=bd_id,
                performing_department_code="lidar",
                status="PAYMENT_PENDING",
                commercial_value=Decimal("10000"),
                currency="INR",
                created_by_id=bd_id,
                updated_by_id=bd_id,
            )
        )
        invoice = ProjectInvoice(
            project_id=project.id,
            invoice_number=f"INV-BDHTTP-{suffix}",
            status="PAYMENT_PENDING",
            invoice_date=date.today() - timedelta(days=40),
            due_date=date.today() - timedelta(days=5),
            amount=Decimal("10000"),
            tax_amount=Decimal("0"),
            currency="INR",
            created_by_id=finance_id,
            raised_by_id=finance_id,
            raised_at=utc_now(),
        )
        db.add(invoice)
        db.flush()
        project_id, invoice_id = project.id, invoice.id
        db.commit()
    return project_id, invoice_id


def test_bad_debt_endpoints_are_denied_to_operational_roles_and_cross_roles():
    app, TestingSession, ids = _build_bad_debt_app()

    for role in _HTTP_OPERATIONAL_ROLES:
        client = _client_for_role(app, TestingSession, role, ids)
        assert client.post(
            "/api/lifecycle/invoices/999999/bad-debt",
            json={"reason": "Not allowed", "collection_attempts": "Not allowed"},
        ).status_code == 403, f"{role} must not be able to propose Bad Debt"
        assert client.post(
            "/api/lifecycle/invoices/999999/bad-debt/decision",
            json={"decision": "approved", "comments": "Not allowed"},
        ).status_code == 403, f"{role} must not be able to decide Bad Debt"
        assert client.post(
            "/api/lifecycle/invoices/999999/bad-debt/recovery",
            json={
                "amount": "1",
                "payment_date": date.today().isoformat(),
                "payment_reference": "NOPE",
            },
        ).status_code == 403, f"{role} must not be able to record a recovery"
        assert client.post(
            "/api/lifecycle/invoices/999999/overdue"
        ).status_code == 403, f"{role} must not escalate invoices"
        assert client.get("/api/lifecycle/bad-debts").status_code == 403, (
            f"{role} must not be able to read the Bad Debt register"
        )

    # Cross-role checks: Management proposes nothing, Finance decides nothing.
    management = _client_for_role(app, TestingSession, "management", ids)
    assert management.post(
        "/api/lifecycle/invoices/999999/bad-debt",
        json={"reason": "Not allowed", "collection_attempts": "Not allowed"},
    ).status_code == 403
    assert management.get("/api/lifecycle/bad-debts").status_code == 200

    finance = _client_for_role(app, TestingSession, "finance", ids)
    assert finance.post(
        "/api/lifecycle/invoices/999999/bad-debt/decision",
        json={"decision": "approved", "comments": "Finance cannot decide"},
    ).status_code == 403
    assert finance.get("/api/lifecycle/bad-debts").status_code == 200


def test_bad_debt_endpoints_happy_path_for_finance_and_management():
    app, TestingSession, ids = _build_bad_debt_app()
    project_id, invoice_id = _seed_http_overdue_invoice(TestingSession, ids, "FLOW")

    finance = _client_for_role(app, TestingSession, "finance", ids)

    # Finance escalates the invoice to Payment Overdue first.
    resp = finance.post(f"/api/lifecycle/invoices/{invoice_id}/overdue")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PAYMENT_OVERDUE"

    # Finance proposes.
    resp = finance.post(
        f"/api/lifecycle/invoices/{invoice_id}/bad-debt",
        json={
            "reason": "Client has not settled the invoice",
            "collection_attempts": "Calls and emails recorded",
            "last_followup_date": (date.today() - timedelta(days=1)).isoformat(),
            "proposed_amount": "6000",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PROPOSED"
    bad_debt_id = resp.json()["id"]

    # A second proposal while one is pending is refused.
    resp = finance.post(
        f"/api/lifecycle/invoices/{invoice_id}/bad-debt",
        json={"reason": "Duplicate proposal", "collection_attempts": "Duplicate proposal"},
    )
    assert resp.status_code == 422
    assert "already pending" in resp.json()["detail"]

    # Management decides.
    # DUAL APPROVAL: Vinod Sir approves first — the write-off is still pending.
    vinod = _client_for_role(app, TestingSession, "vinod", ids)
    resp = vinod.post(
        f"/api/lifecycle/invoices/{invoice_id}/bad-debt/decision",
        json={"decision": "approved", "comments": "Approved after collection review"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "PROPOSED"
    assert resp.json()["approvals"]["approved_count"] == 1

    # Chethan approves — now the write-off becomes effective (exactly once).
    chethan = _client_for_role(app, TestingSession, "chethan", ids)
    resp = chethan.post(
        f"/api/lifecycle/invoices/{invoice_id}/bad-debt/decision",
        json={"decision": "approved", "comments": "Approved after collection review"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "APPROVED"
    assert resp.json()["approvals"]["approved_count"] == 2

    # Finance records a real recovery.
    resp = finance.post(
        f"/api/lifecycle/invoices/{invoice_id}/bad-debt/recovery",
        json={
            "amount": "6000",
            "payment_date": date.today().isoformat(),
            "payment_reference": "UTR-FLOW-1",
            "payment_mode": "bank_transfer",
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "RECOVERED"
    assert resp.json()["recovered_amount"] == 6000.0

    resp = finance.get("/api/lifecycle/bad-debts")
    assert resp.status_code == 200
    entry = next(item for item in resp.json() if item["id"] == bad_debt_id)
    assert entry["status"] == "RECOVERED"
    assert entry["invoice_id"] == invoice_id
    assert entry["project_id"] == project_id
    assert entry["unrecovered_amount"] == 0.0
