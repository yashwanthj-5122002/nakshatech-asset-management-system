"""Focused tests: Bad Debt DUAL management approval (Vinod Sir AND Chethan).

Pins the new business rule added on top of the existing bad-debt lifecycle:
  * ONE approval never finalizes a write-off (no financial effect, KPI stays 0,
    collectible Outstanding stays collectible);
  * BOTH approvals apply the write-off exactly once;
  * either approver rejecting rejects the case and nothing moves to Bad Debt;
  * repeated/concurrent approval clicks are idempotent (no duplicate rows/notifications);
  * a payment arriving while the proposal is pending blocks final approval — the proposal
    can never exceed the new collectible balance and Outstanding never goes negative;
  * authorization requires the ACTUAL management identities (Finance/random management
    accounts cannot decide);
  * a rejected proposal can be re-proposed as a fresh approval cycle.

Isolated TEST DATA only. Not the release regression.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.lifecycle_models import ProjectInvoiceBadDebtApproval
from app.modules.operations.lifecycle_schemas import (
    BadDebtDecision,
    BadDebtProposalCreate,
    InvoicePaymentCreate,
)
from app.modules.operations.lifecycle_service import (
    _bad_debt_approval_payload,
    _invoice_cash_balance,
    decide_bad_debt,
    mark_invoice_overdue,
    propose_bad_debt,
    record_invoice_payment,
)
from test_bad_debt_lifecycle_v8_1 import (  # noqa: E402
    CHETHAN_EMAIL,
    VINOD_EMAIL,
    _overdue_invoice,
    _user,
)


def _propose(db, finance, invoice, amount=None):
    return propose_bad_debt(
        db, actor=finance, invoice_id=invoice.id,
        payload=BadDebtProposalCreate(
            proposed_amount=Decimal(str(amount)) if amount is not None else None,
            reason="Client stopped responding after the due date",
            collection_attempts="Three reminders and two calls",
        ))


def _decide(db, email, invoice_id, decision="approved", comments="Reviewed"):
    return decide_bad_debt(
        db, actor=_user(db, email, "management"), invoice_id=invoice_id,
        payload=BadDebtDecision(decision=decision, comments=comments))


def _kpi(db, project):
    overview = sales_revenue_overview(db, department_scope=None)
    row = next(r for r in overview["projects"] if r["project_id"] == project.id)
    return row


def _approval_rows(db, invoice_id):
    return db.scalar(select(func.count(ProjectInvoiceBadDebtApproval.id)).where(
        ProjectInvoiceBadDebtApproval.invoice_id == invoice_id)) or 0


# ======================= one approval never finalizes ====================================

def test_one_approval_only_has_no_financial_effect():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL1")
        record_invoice_payment(
            db, actor=finance, invoice_id=invoice.id,
            payload=InvoicePaymentCreate(payment_reference="DUAL1-4000",
                                         payment_date=date.today() - timedelta(days=10),
                                         amount=Decimal("4000"), payment_mode="bank_transfer"))
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        proposal = _propose(db, finance, invoice)
        db.flush()
        assert proposal.status == "PROPOSED"

        after_first = _decide(db, VINOD_EMAIL, invoice.id)
        db.flush()
        assert after_first.status == "PROPOSED"          # still pending
        assert after_first.approved_amount is None       # NO financial effect
        assert _approval_rows(db, invoice.id) == 1
        payload = _bad_debt_approval_payload(db, after_first)
        assert payload["approved_count"] == 1 and payload["required_count"] == 2

        row = _kpi(db, project)
        assert row["bad_debt_inr"] == 0.0                # KPI counts approved only
        assert row["outstanding_inr"] == 6000.0          # still collectible
        assert _invoice_cash_balance(db, invoice) == Decimal("6000")


def test_both_approvals_apply_the_write_off_exactly_once():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL2")
        record_invoice_payment(
            db, actor=finance, invoice_id=invoice.id,
            payload=InvoicePaymentCreate(payment_reference="DUAL2-4000",
                                         payment_date=date.today() - timedelta(days=10),
                                         amount=Decimal("4000"), payment_mode="bank_transfer"))
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice)
        db.flush()

        _decide(db, CHETHAN_EMAIL, invoice.id)           # reverse order also works
        final = _decide(db, VINOD_EMAIL, invoice.id)
        db.flush()
        assert final.status == "APPROVED"
        assert final.approved_amount == Decimal("6000")
        assert _approval_rows(db, invoice.id) == 2

        row = _kpi(db, project)
        assert row["bad_debt_inr"] == 6000.0             # approved unrecovered only
        assert row["outstanding_inr"] == 0.0             # approved write-off removed
        assert row["closed_revenue_inr"] == 0.0          # NEVER revenue
        assert row["sales_value_inr"] == 10000.0         # Sales never rewritten


# ======================= idempotency / concurrency ======================================

def test_repeated_approval_click_is_idempotent():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL3")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice)
        db.flush()
        _decide(db, VINOD_EMAIL, invoice.id)
        db.flush()
        rows_before = _approval_rows(db, invoice.id)
        notes_before = db.scalar(select(func.count(GlobalNotification.id))) or 0

        # Same approver clicks again (double submit) — no duplicate effect at all.
        again = _decide(db, VINOD_EMAIL, invoice.id)
        db.flush()
        assert again.status == "PROPOSED"
        assert _approval_rows(db, invoice.id) == rows_before
        assert (db.scalar(select(func.count(GlobalNotification.id))) or 0) == notes_before

        # And the second approver finalizes exactly once even if called twice.
        _decide(db, CHETHAN_EMAIL, invoice.id)
        db.flush()
        final = _decide(db, CHETHAN_EMAIL, invoice.id)
        db.flush()
        assert final.status == "APPROVED"
        assert _approval_rows(db, invoice.id) == 2


# ======================= rejection ======================================================

def test_either_approver_rejection_keeps_the_balance_collectible():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL4")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice)
        db.flush()
        _decide(db, VINOD_EMAIL, invoice.id)                     # one approval
        rejected = _decide(db, CHETHAN_EMAIL, invoice.id, decision="rejected",
                           comments="Continue collection for another cycle")
        db.flush()
        assert rejected.status == "REJECTED"
        assert rejected.approved_amount is None
        row = _kpi(db, project)
        assert row["bad_debt_inr"] == 0.0
        assert row["outstanding_inr"] == 10000.0                 # still collectible
        assert _invoice_cash_balance(db, invoice) == Decimal("10000")


def test_rejection_requires_a_reason():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL5")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice)
        db.flush()
        # The schema enforces min length; a whitespace-only reason must still be refused.
        with pytest.raises(ValueError, match="reason is required"):
            _decide(db, VINOD_EMAIL, invoice.id, decision="rejected", comments="   ")


# ======================= payment during approval =========================================

def test_payment_during_approval_blocks_final_approval_without_negative_outstanding():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL6")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice, amount=Decimal("10000"))
        db.flush()
        _decide(db, VINOD_EMAIL, invoice.id)                     # first approval
        db.flush()

        # The client pays while the proposal is pending — the real payment still works.
        record_invoice_payment(
            db, actor=finance, invoice_id=invoice.id,
            payload=InvoicePaymentCreate(payment_reference="DUAL6-PAY",
                                         payment_date=date.today(),
                                         amount=Decimal("4000"), payment_mode="bank_transfer"))
        db.flush()
        assert _invoice_cash_balance(db, invoice) == Decimal("6000")

        # The proposal (10,000) now exceeds the collectible balance -> approval is BLOCKED.
        with pytest.raises(ValueError, match="collectible balance changed"):
            _decide(db, CHETHAN_EMAIL, invoice.id)
        db.flush()
        assert _invoice_cash_balance(db, invoice) == Decimal("6000")   # never negative
        row = _kpi(db, project)
        assert row["bad_debt_inr"] == 0.0
        assert row["outstanding_inr"] == 6000.0


# ======================= authorization ==================================================

def test_only_the_two_authorized_management_identities_can_decide():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL7")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice)
        db.flush()

        # Finance can never self-approve.
        with pytest.raises(PermissionError):
            decide_bad_debt(db, actor=finance, invoice_id=invoice.id,
                            payload=BadDebtDecision(decision="approved", comments="self"))
        # A management user who is NOT Vinod Sir / Chethan can never decide.
        random_mgmt = _user(db, "some.other.management@nakshatech.com", "management")
        with pytest.raises(PermissionError):
            decide_bad_debt(db, actor=random_mgmt, invoice_id=invoice.id,
                            payload=BadDebtDecision(decision="approved", comments="not authorized"))
        assert _approval_rows(db, invoice.id) == 0
        # The authorized identities still work.
        _decide(db, VINOD_EMAIL, invoice.id)
        db.flush()
        assert _approval_rows(db, invoice.id) == 1


# ======================= re-proposal after rejection ====================================

def test_rejected_proposal_can_be_reproposed_as_a_fresh_cycle():
    with SessionLocal() as db:
        finance, _mgmt, project, invoice = _overdue_invoice(db, "DUAL8")
        mark_invoice_overdue(db, actor=finance, invoice_id=invoice.id)
        _propose(db, finance, invoice, amount=Decimal("4000"))
        db.flush()
        _decide(db, VINOD_EMAIL, invoice.id, decision="rejected", comments="Try more collection")
        db.flush()

        again = _propose(db, finance, invoice, amount=Decimal("6000"))
        db.flush()
        assert again.status == "PROPOSED"
        # A new cycle -> the previous rejection no longer counts against the new proposal.
        assert _bad_debt_approval_payload(db, again)["approved_count"] == 0
        _decide(db, VINOD_EMAIL, invoice.id)
        final = _decide(db, CHETHAN_EMAIL, invoice.id)
        db.flush()
        assert final.status == "APPROVED"
        assert final.approved_amount == Decimal("6000")
        # Append-only: the earlier cycle's decision rows are preserved (2 cycles x 1 = 2 rows + 1 new cycle rows)
        assert _approval_rows(db, invoice.id) >= 3
