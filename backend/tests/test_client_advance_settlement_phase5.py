"""Client Advance Received -> Project Collection -> Apply to Invoice -> Payment -> Revenue.

Finance V8 Phase 5 end-to-end money workflow on one project:

    Project value            Rs. 20,00,000
    Expected client advance  Rs.  5,00,000   (25 % of the taxable base)
    Invoice                  Rs. 20,00,000   (face value never changes)

    A. receive Rs. 2,00,000  -> Partial Received / Partial Payment / Rs. 18,00,000 left
    B. receive Rs. 3,00,000  -> Received       / Rs. 15,00,000 left
    C. raise the invoice     -> face value still Rs. 20,00,000
    D. apply Rs. 5,00,000    -> Adjusted / PARTIALLY_PAID / Rs. 15,00,000 outstanding
    E. receive Rs. 15,00,000 cash -> fully settled, outstanding Rs. 0, no double counting
    F. before Finance close  -> Revenue is still Rs. 0
    G. Finance closes it     -> Revenue Rs. 20,00,000 (never 15L or 25L) and Advance = Closed

Also covered: three receipts applied across invoices, and operational project
completion staying independent from financial completion.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.advance_schemas import ClientAdvanceTransactionCreate
from app.modules.finance.advance_service import record_advance_transaction
from app.modules.finance.advance_settlement_service import (
    advance_applied_by_invoice,
    apply_advance_to_invoice,
    available_unapplied_advance,
    project_collection_summary,
)
from app.modules.finance.models import FinanceClient, FinanceProjectMasterProfile
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.lifecycle_schemas import InvoiceClose, InvoicePaymentCreate
from app.modules.operations.lifecycle_service import assert_finance_closable, close_invoice, record_invoice_payment
from app.modules.operations.models import ProjectWorkflow
from app.modules.operations.schemas import WorkflowProjectCreate
from app.modules.operations.workflow_service import create_bd_project

PROJECT_VALUE = Decimal("2000000")        # 20,00,000
ADVANCE_EXPECTED = Decimal("500000")     # 5,00,000
INVOICE_VALUE = Decimal("2000000")       # 20,00,000


def _user(db, email: str, role: str) -> User:
    row = User(
        email=email, full_name=email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _commercial(**overrides) -> ProjectCommercialInput:
    """20,00,000 contract, no tax, 25 % advance -> expected 5,00,000 (project value == 20,00,000)."""
    values = dict(
        scope_description="UAT money workflow", billing_type="fixed_price",
        payment_terms="25% advance, 75% after delivery", currency_code="INR",
        estimated_amount=PROJECT_VALUE, taxable_base_amount=PROJECT_VALUE, tax_percent=Decimal("0"),
        advance_required=True, advance_payment_type="percentage_advance",
        advance_percent=Decimal("25"),
        expected_advance_date=date(2026, 11, 15), final_advance_date=date(2026, 12, 15),
    )
    values.update(overrides)
    return ProjectCommercialInput(**values)


def _setup(db, suffix: str):
    bd = _user(db, f"bd.p5.{suffix}@nakshatech.com", "bd")
    finance = _user(db, f"finance.p5.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"P5-{suffix}", client_name=f"Phase5 Client {suffix}",
        contact_person_name="Contact", contact_person_phone="9999999999",
        source_team="bd_team", source_person_name=bd.full_name, is_active=True, created_by_id=bd.id,
    )
    db.add(client)
    db.flush()
    project, _ = create_bd_project(
        db, actor=bd,
        payload=WorkflowProjectCreate(
            client_id=client.id, project_code=f"P5-{suffix}", project_name=f"Phase5 Project {suffix}",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey",
            commercial=_commercial(),
        ),
    )
    db.flush()
    return project, bd, finance


def _receive(db, *, project_id: int, amount: Decimal, finance: User, reference: str) -> None:
    record_advance_transaction(
        db,
        project_id=project_id,
        payload=ClientAdvanceTransactionCreate(
            amount=amount, currency="INR", payment_date=date(2026, 10, 20),
            payment_mode="bank_transfer", reference_number=reference, bank_reference=f"BANK-{reference}",
        ),
        actor=finance,
        effective_role="finance",
    )
    db.flush()


def _invoice(db, *, project, finance, number: str, amount: Decimal = INVOICE_VALUE) -> ProjectInvoice:
    invoice = ProjectInvoice(
        project_id=project.id, invoice_number=number, status="INVOICE_RAISED",
        invoice_date=date(2026, 11, 1), due_date=date(2026, 12, 1),
        amount=amount, tax_amount=Decimal("0"), currency="INR", created_by_id=finance.id,
        raised_by_id=finance.id,
    )
    db.add(invoice)
    db.flush()
    return invoice


def _collection(db, *, project_id: int, bd: User) -> dict:
    return project_collection_summary(db, project_id=project_id, user=bd, effective_role="bd")


def _revenue_for(db, project_id: int) -> Decimal:
    overview = sales_revenue_overview(db)
    return sum(
        (Decimal(str(event["revenue_amount_inr"])) for event in overview["revenue_events"]
         if event["project_id"] == project_id),
        Decimal("0"),
    )


def _ids(db, suffix: str):
    bd = db.scalar(select(User).where(User.email == f"bd.p5.{suffix}@nakshatech.com"))
    finance = db.scalar(select(User).where(User.email == f"finance.p5.{suffix}@nakshatech.com"))
    return bd, finance


def test_full_money_workflow_advance_to_invoice_to_revenue():
    """A -> G: receive, apply to invoice, settle, close, recognize full revenue."""
    with SessionLocal() as db:
        project, bd, finance = _setup(db, "FLOW")
        project_id = project.id

        # ------------------------------------------- A. first advance receipt Rs. 2,00,000
        _receive(db, project_id=project_id, amount=Decimal("200000"), finance=finance, reference="ADV-1")
        state = _collection(db, project_id=project_id, bd=bd)
        assert state["advance_expected_inr"] == ADVANCE_EXPECTED
        assert state["advance_received_inr"] == Decimal("200000")
        assert state["advance_pending_inr"] == Decimal("300000")
        assert state["advance_status"] == "partial_received"
        assert state["total_collected_inr"] == Decimal("200000")
        assert state["remaining_project_balance_inr"] == Decimal("1800000")
        assert state["collection_status"] == "Partial Payment"
        assert state["invoice_status"] == "Invoice Not Raised"
        assert _revenue_for(db, project_id) == Decimal("0")

        # ------------------------------------------- B. second receipt Rs. 3,00,000 -> Received
        _receive(db, project_id=project_id, amount=Decimal("300000"), finance=finance, reference="ADV-2")
        state = _collection(db, project_id=project_id, bd=bd)
        assert state["advance_received_inr"] == ADVANCE_EXPECTED
        assert state["advance_pending_inr"] == Decimal("0")
        assert state["advance_status"] == "received"
        assert state["total_collected_inr"] == ADVANCE_EXPECTED
        assert state["remaining_project_balance_inr"] == Decimal("1500000")
        assert _revenue_for(db, project_id) == Decimal("0")

        # ------------------------------------------- C. raise the invoice (face value fixed)
        invoice = _invoice(db, project=project, finance=finance, number="INV-P5-FLOW")
        db.commit()
        assert Decimal(invoice.amount) == INVOICE_VALUE

    with SessionLocal() as db:
            bd, finance = _ids(db, "FLOW")
            invoice = db.scalar(select(ProjectInvoice).where(ProjectInvoice.invoice_number == "INV-P5-FLOW"))

            # ------------------------------------------- D. apply the whole advance to the invoice
            applied = apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice.id, amount_inr=ADVANCE_EXPECTED,
                actor=finance, effective_role="finance",
            )
            db.commit()

            assert applied["applied_inr"] == ADVANCE_EXPECTED
            assert applied["invoice_status"] == "PARTIALLY_PAID"
            assert applied["invoice_total"] == INVOICE_VALUE       # face value unchanged
            assert applied["invoice_settled_total"] == ADVANCE_EXPECTED
            assert applied["invoice_balance"] == Decimal("1500000")
            assert applied["advance_status"] == "adjusted"
            # the advance is NEVER duplicated into invoice payments
            assert db.scalar(select(func.count(ProjectInvoicePayment.id)).where(
                ProjectInvoicePayment.invoice_id == invoice.id
            )) == 0
            assert available_unapplied_advance(db, project_id=project_id) == Decimal("0")

            db.refresh(invoice)
            assert Decimal(invoice.amount) == INVOICE_VALUE       # still 20,00,000
            state = _collection(db, project_id=project_id, bd=bd)
            assert state["advance_applied_inr"] == ADVANCE_EXPECTED
            assert state["advance_unapplied_inr"] == Decimal("0")
            assert state["invoice_cash_payments_inr"] == Decimal("0")
            assert state["total_collected_inr"] == ADVANCE_EXPECTED   # counted once
            assert state["remaining_project_balance_inr"] == Decimal("1500000")
            assert state["advance_status"] == "adjusted"
            assert state["invoices"][0]["balance"] == Decimal("1500000")
            assert state["invoices"][0]["status"] == "PARTIALLY_PAID"
            assert _revenue_for(db, project_id) == Decimal("0")

            # ------------------------------------------- E. normal cash payment Rs. 15,00,000
            record_invoice_payment(
                db, actor=finance, invoice_id=invoice.id,
                payload=InvoicePaymentCreate(
                    payment_reference="CASH-1", payment_date=date(2026, 11, 20), amount=Decimal("1500000"),
                ),
            )
            db.commit()

            db.refresh(invoice)
            assert Decimal(invoice.amount) == INVOICE_VALUE       # face value still untouched
            # Existing ERP rule: an invoice closes when its SETTLED amount reaches the face
            # value. Settled = 15,00,000 cash + 5,00,000 advance applied = 20,00,000.
            assert invoice.status == "INVOICE_CLOSED"
            cash_rows = db.scalars(select(ProjectInvoicePayment).where(
                ProjectInvoicePayment.invoice_id == invoice.id
            )).all()
            assert len(cash_rows) == 1                            # exactly one payment row
            assert sum((Decimal(row.amount) for row in cash_rows), Decimal("0")) == Decimal("1500000")
            assert advance_applied_by_invoice(db, [invoice.id])[invoice.id] == ADVANCE_EXPECTED

            state = _collection(db, project_id=project_id, bd=bd)
            assert state["advance_applied_inr"] == ADVANCE_EXPECTED
            assert state["invoice_cash_payments_inr"] == Decimal("1500000")
            assert state["total_collected_inr"] == INVOICE_VALUE  # 5L advance + 15L cash = 20L, once
            assert state["remaining_project_balance_inr"] == Decimal("0")
            assert state["collection_status"] == "Fully Collected"
            assert state["invoices"][0]["balance"] == Decimal("0")

            # ------------------------------------- F/G. revenue and the final advance status
            # Revenue rule unchanged: recognized only for a CLOSED and fully settled invoice,
            # and it is the FULL settled amount - never 15L (cash only) and never 25L.
            assert _revenue_for(db, project_id) == INVOICE_VALUE
            final = _collection(db, project_id=project_id, bd=bd)
            assert final["advance_status"] == "closed"
            assert final["total_collected_inr"] == INVOICE_VALUE
            assert final["remaining_project_balance_inr"] == Decimal("0")
            assert final["invoice_status"] == "Closed"

            # The explicit close action stays available and is idempotent.
            close_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceClose(comments="Fully settled"))
            db.commit()
            db.refresh(invoice)
            assert invoice.status == "INVOICE_CLOSED"
            assert _revenue_for(db, project_id) == INVOICE_VALUE

            # Money is complete, but PROJECT Finance closure is still a separate manual gate.
            workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))
            with pytest.raises(ValueError):
                assert_finance_closable(db, workflow=workflow)


def test_multiple_advance_receipts_apply_exactly_once():
    """Rs. 2L + 1L + 2L = 5L: history preserved, each adjustment traceable, no double count."""
    with SessionLocal() as db:
        project, bd, finance = _setup(db, "MULTI")
        project_id = project.id
        _receive(db, project_id=project_id, amount=Decimal("200000"), finance=finance, reference="M1")
        _receive(db, project_id=project_id, amount=Decimal("100000"), finance=finance, reference="M2")
        _receive(db, project_id=project_id, amount=Decimal("200000"), finance=finance, reference="M3")

        state = _collection(db, project_id=project_id, bd=bd)
        assert state["advance_received_inr"] == ADVANCE_EXPECTED      # exactly 5L, once
        assert state["advance_status"] == "received"
        assert state["total_collected_inr"] == ADVANCE_EXPECTED
        assert available_unapplied_advance(db, project_id=project_id) == ADVANCE_EXPECTED

        invoice = _invoice(db, project=project, finance=finance, number="INV-P5-MULTI")
        db.flush()
        applied = apply_advance_to_invoice(
            db, project_id=project_id, invoice_id=invoice.id, amount_inr=ADVANCE_EXPECTED,
            actor=finance, effective_role="finance",
        )
        db.commit()

        assert len(applied["allocations"]) == 3                         # every receipt traced
        assert sum((Decimal(str(item["amount_inr"])) for item in applied["allocations"]), Decimal("0")) == ADVANCE_EXPECTED
        rows = db.scalars(select(ClientAdvanceTransaction).where(
            ClientAdvanceTransaction.project_id == project_id
        ).order_by(ClientAdvanceTransaction.sequence)).all()
        assert len(rows) == 3                                          # history preserved
        assert all(row.adjusted_invoice_id == invoice.id for row in rows)
        assert all(row.adjusted_at is not None for row in rows)
        assert sum((Decimal(row.adjusted_amount_inr) for row in rows), Decimal("0")) == ADVANCE_EXPECTED
        assert db.scalar(select(func.count(ProjectInvoicePayment.id))) == 0   # no fake payment row
        assert available_unapplied_advance(db, project_id=project_id) == Decimal("0")
        assert applied["invoice_settled_total"] == ADVANCE_EXPECTED
        assert applied["invoice_balance"] == Decimal("1500000")

        # The same money can never be applied twice.
        with pytest.raises(ValueError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice.id, amount_inr=ADVANCE_EXPECTED,
                actor=finance, effective_role="finance",
            )
        db.rollback()

        # Settlement never becomes 25L (20L face value + 5L advance counted twice).
        db.refresh(invoice)
        assert Decimal(invoice.amount) == INVOICE_VALUE
        assert advance_applied_by_invoice(db, [invoice.id])[invoice.id] == ADVANCE_EXPECTED
        state = _collection(db, project_id=project_id, bd=bd)
        assert state["total_collected_inr"] == ADVANCE_EXPECTED
        assert state["invoices"][0]["settled_total"] == ADVANCE_EXPECTED
        assert state["invoices"][0]["balance"] == Decimal("1500000")
        assert _revenue_for(db, project_id) == Decimal("0")
def test_operational_completion_stays_separate_from_financial_completion():
    """An operationally completed project may still carry an open receivable."""
    with SessionLocal() as db:
        project, bd, finance = _setup(db, "OPS")
        project_id = project.id
        _receive(db, project_id=project_id, amount=Decimal("500000"), finance=finance, reference="OPS-1")
        invoice = _invoice(db, project=project, finance=finance, number="INV-P5-OPS")
        db.flush()

        # Operations finish the delivery; money is still outstanding.
        workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))
        workflow.status = "OPERATIONAL_COMPLETE"
        db.flush()
        db.commit()

    with SessionLocal() as db:
        bd, finance = _ids(db, "OPS")
        invoice = db.scalar(select(ProjectInvoice).where(ProjectInvoice.invoice_number == "INV-P5-OPS"))
        workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))

        # Operational completion = YES, but the invoice is NOT closed and money is outstanding.
        assert workflow.status == "OPERATIONAL_COMPLETE"
        db.refresh(invoice)
        assert invoice.status == "INVOICE_RAISED"
        state = _collection(db, project_id=project_id, bd=bd)
        assert state["remaining_project_balance_inr"] == Decimal("1500000")
        assert state["collection_status"] == "Partial Payment"
        assert _revenue_for(db, project_id) == Decimal("0")
        # Project Finance closure is still blocked.
        with pytest.raises(ValueError):
            assert_finance_closable(db, workflow=workflow)

        # Settle the invoice with the advance and the remaining cash.
        apply_advance_to_invoice(
            db, project_id=project_id, invoice_id=invoice.id, amount_inr=ADVANCE_EXPECTED,
            actor=finance, effective_role="finance",
        )
        db.commit()
        record_invoice_payment(
            db, actor=finance, invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="OPS-CASH", payment_date=date(2026, 12, 5), amount=Decimal("1500000"),
            ),
        )
        db.commit()

        db.refresh(invoice)
        assert invoice.status == "INVOICE_CLOSED"
        assert _revenue_for(db, project_id) == INVOICE_VALUE       # full invoice value
        final = _collection(db, project_id=project_id, bd=bd)
        assert final["remaining_project_balance_inr"] == Decimal("0")
        assert final["advance_status"] == "closed"

def test_apply_advance_guards_and_role_permissions():
    """Validation limits, Finance-only writes, BD read-only and PM monetary redaction."""
    with SessionLocal() as db:
        project, bd, finance = _setup(db, "GUARD")
        project_id = project.id
        _receive(db, project_id=project_id, amount=Decimal("200000"), finance=finance, reference="G1")
        invoice = _invoice(db, project=project, finance=finance, number="INV-P5-GUARD", amount=Decimal("300000"))
        db.commit()
        invoice_id = invoice.id

        def _reload() -> ProjectInvoice:
            return db.scalar(select(ProjectInvoice).where(ProjectInvoice.invoice_number == "INV-P5-GUARD"))

        # amount <= 0
        with pytest.raises(ValueError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("0"),
                actor=finance, effective_role="finance",
            )
        db.rollback()
        # amount > unapplied advance available (only 2,00,000 received)
        with pytest.raises(ValueError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("250000"),
                actor=finance, effective_role="finance",
            )
        db.rollback()
        # amount > invoice outstanding (only 1,00,000 free after the 2,00,000 advance)
        apply_advance_to_invoice(
            db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("100000"),
            actor=finance, effective_role="finance",
        )
        db.commit()
        with pytest.raises(ValueError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("50000"),
                actor=finance, effective_role="finance",
            )
        db.rollback()
        # a closed invoice can never take more advance
        closed = _reload()
        closed.status = "INVOICE_CLOSED"
        db.commit()
        with pytest.raises(ValueError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("10000"),
                actor=finance, effective_role="finance",
            )
        db.rollback()
        closed = _reload()
        closed.status = "PARTIALLY_PAID"
        db.commit()

        # BD cannot record a receipt nor apply an advance.
        with pytest.raises(PermissionError):
            record_advance_transaction(
                db, project_id=project_id,
                payload=ClientAdvanceTransactionCreate(
                    amount=Decimal("1000"), currency="INR", payment_date=date(2026, 10, 25),
                    payment_mode="upi",
                ),
                actor=bd, effective_role="bd",
            )
        db.rollback()
        with pytest.raises(PermissionError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("100000"),
                actor=bd, effective_role="bd",
            )
        db.rollback()
        # Management is read-only as well.
        with pytest.raises(PermissionError):
            apply_advance_to_invoice(
                db, project_id=project_id, invoice_id=invoice_id, amount_inr=Decimal("100000"),
                actor=finance, effective_role="management",
            )
        db.rollback()

    # Read-side permissions are checked in a clean session (rollbacks detach objects).
    with SessionLocal() as db:
        bd, _ = _ids(db, "GUARD")
        # BD keeps a read-only collection view of its own project.
        state = _collection(db, project_id=project_id, bd=bd)
        assert state["total_collected_inr"] == Decimal("200000")

        # A technical PM role stays redacted: status/counts only, no monetary values.
        pm = _user(db, "pm.p5.GUARD@nakshatech.com", "lidar")
        profile = db.get(FinanceProjectMasterProfile, project_id)
        if profile is None:
            db.add(FinanceProjectMasterProfile(
                project_id=project_id, project_manager_id=pm.id, created_by_id=bd.id,
            ))
        else:
            profile.project_manager_id = pm.id
        db.commit()
        pm_state = project_collection_summary(
            db, project_id=project_id, user=pm, effective_role="lidar",
        )
        assert pm_state["financial_amounts_visible"] is False
        assert pm_state["total_collected_inr"] is None
        assert pm_state["advance_received_inr"] is None
        assert pm_state["project_value_inr"] is None
        assert pm_state["collection_status"] == "Partial Payment"   # status stays visible
        assert pm_state["advance_status"] == "adjusted"       # 1L of the 2L is applied to the invoice
        assert all(row["balance"] is None for row in pm_state["invoices"])

        # Production/QC/QA have no Client Advance finance access at all.
        for role in ("production", "qc", "qa"):
            denied = _user(db, f"ops.{role}.p5@nakshatech.com", role)
            db.commit()
            with pytest.raises(PermissionError):
                project_collection_summary(
                    db, project_id=project_id, user=denied, effective_role=role,
                )


