from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.commercial.models import (
    ProjectCommercialEstimateRevision,
    ProjectFxOverride,
    ProjectVendorInvoice,
)
from app.modules.commercial.schemas import (
    CommercialEstimateDecision,
    CommercialEstimateInput,
    ProjectExpenseDecision,
    ProjectExpenseDeclarationInput,
    ProjectExpenseInput,
    ProjectExpenseReimbursement,
    VendorInvoiceInput,
)
from app.modules.commercial.service import (
    assert_commercial_closure_ready,
    create_estimate_revision,
    create_project_expense,
    create_vendor_invoice,
    decide_estimate_revision,
    decide_project_expense,
    project_cost_summary,
    reimburse_project_expense,
    submit_baseline_estimate,
    submit_project_expense,
    upsert_baseline_estimate,
    declare_project_expenses,
)
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectAssignment
from app.modules.operations.lifecycle_schemas import InvoiceDraftCreate, InvoicePaymentCreate, InvoiceRaise
from app.modules.operations.lifecycle_service import (
    READY_FOR_BILLING,
    create_invoice_draft,
    raise_invoice,
    record_invoice_payment,
)
from app.modules.operations.models import ProjectWorkflow
from app.modules.operations.schemas import WorkflowFinanceReview
from app.modules.operations.workflow_service import finance_review_project


def make_user(db, email: str, role: str, name: str | None = None) -> User:
    row = User(
        email=email,
        full_name=name or email.split("@", 1)[0],
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


def make_project(db, *, owner: User, status: str = "draft", code: str = "COMM-P01") -> tuple[FinanceProject, ProjectWorkflow]:
    client = FinanceClient(
        client_code=f"C-{code}",
        client_name="Commercial Test Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        source_team="bd_team",
        source_person_name=owner.full_name,
        is_active=True,
        created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=code,
        project_name="Commercial Layer Test",
        client_id=client.id,
        client_name=client.client_name,
        is_active=False,
        created_by_id=owner.id,
    )
    db.add(project)
    db.flush()
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=owner.id,
        status=status,
        scope_text="Photogrammetry delivery",
        priority="medium",
        currency="INR",
        created_by_id=owner.id,
        updated_by_id=owner.id,
    )
    db.add(workflow)
    db.flush()
    return project, workflow


def estimate_payload(amount: str, *, reason: str | None = None) -> CommercialEstimateInput:
    return CommercialEstimateInput(
        scope_description="Survey, processing and delivery",
        billing_type="fixed_price",
        payment_terms="30 days",
        po_wo_reference="PO-COMM-01",
        currency_code="INR",
        estimated_amount=Decimal(amount),
        taxable_base_amount=Decimal(amount),
        tax_percent=Decimal("18"),
        estimated_direct_cost_inr=Decimal("50000"),
        estimate_date=date(2026, 9, 21),
        reason=reason,
    )


def test_finance_project_approval_freezes_baseline_and_later_revision_updates_summary():
    with SessionLocal() as db:
        bd = make_user(db, "bd.commercial@nakshatech.com", "bd", "BD Commercial")
        finance = make_user(db, "finance.commercial@nakshatech.com", "finance", "Finance Commercial")
        project, workflow = make_project(db, owner=bd, status="pending_finance_approval", code="COMM-BASE-01")

        baseline = upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=estimate_payload("100000"))
        submit_baseline_estimate(db, actor=bd, project_id=project.id)
        finance_review_project(
            db,
            actor=finance,
            project_id=project.id,
            payload=WorkflowFinanceReview(decision="approve", feedback="Commercials verified"),
        )
        db.flush()

        assert baseline.status == "APPROVED"
        assert baseline.is_locked is True
        assert baseline.approved_by_id == finance.id
        assert workflow.status == "finance_approved"
        assert project.is_active is True
        assert Decimal(workflow.commercial_value) == Decimal("100000.00")

        with pytest.raises(ValueError, match="baseline is locked"):
            upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=estimate_payload("110000"))

        revision = create_estimate_revision(
            db,
            actor=bd,
            project_id=project.id,
            payload=estimate_payload("120000", reason="Client approved additional scope"),
        )
        decide_estimate_revision(
            db,
            actor=finance,
            revision_id=revision.id,
            payload=CommercialEstimateDecision(decision="approve", comments="Variation order verified"),
        )
        db.flush()

        assert revision.revision_no == 2
        assert revision.status == "APPROVED"
        assert revision.is_locked is True
        assert Decimal(workflow.commercial_value) == Decimal("120000.00")
        assert workflow.po_wo_number == "PO-COMM-01"


def test_client_invoice_and_payment_keep_separate_historical_fx_snapshots_and_gain_loss():
    with SessionLocal() as db:
        finance = make_user(db, "finance.fx@nakshatech.com", "finance", "Finance FX")
        project, workflow = make_project(db, owner=finance, status=READY_FOR_BILLING, code="COMM-FX-01")
        project.is_active = True

        invoice = create_invoice_draft(
            db,
            actor=finance,
            project_id=project.id,
            payload=InvoiceDraftCreate(
                invoice_number="INV-FX-001",
                invoice_date=date(2026, 9, 1),
                due_date=date(2026, 9, 30),
                amount=Decimal("1000"),
                tax_amount=Decimal("180"),
                tax_percent=Decimal("18"),
                currency="USD",
                payment_terms="30 days",
                po_wo_reference="PO-USD-01",
                fx_rate_to_inr=Decimal("80"),
                fx_rate_mode="CONTRACT_RATE",
                fx_override_reason="PO contract rate",
            ),
        )
        assert Decimal(invoice.total_inr) == Decimal("94400.00")
        assert Decimal(invoice.fx_rate_to_inr) == Decimal("80.00000000")
        assert invoice.fx_locked is False

        raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
        assert invoice.fx_locked is True

        payment = record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="BANK-REAL-001",
                payment_date=date(2026, 9, 20),
                amount=Decimal("1180"),
                payment_mode="bank_transfer",
                fx_rate_to_inr=Decimal("82"),
                fx_rate_mode="BANK_REALIZATION_RATE",
                fx_override_reason="Bank realization advice",
            ),
        )
        db.flush()

        assert Decimal(payment.inr_equivalent) == Decimal("96760.00")
        assert Decimal(payment.invoice_inr_equivalent) == Decimal("94400.00")
        assert Decimal(payment.fx_gain_loss_inr) == Decimal("2360.00")
        assert Decimal(payment.fx_rate_to_inr) == Decimal("82.00000000")
        overrides = list(db.scalars(select(ProjectFxOverride).where(ProjectFxOverride.project_id == project.id)).all())
        assert len(overrides) == 2
        assert {row.new_mode for row in overrides} == {"CONTRACT_RATE", "BANK_REALIZATION_RATE"}


def test_employee_paid_vendor_bill_counts_cost_once_and_closure_waits_for_reimbursement_only():
    with SessionLocal() as db:
        bd = make_user(db, "bd.cost@nakshatech.com", "bd", "BD Cost")
        finance = make_user(db, "finance.cost@nakshatech.com", "finance", "Finance Cost")
        employee = make_user(db, "employee.cost@nakshatech.com", "employee", "Employee Cost")
        project, _ = make_project(db, owner=bd, status="in_progress", code="COMM-COST-01")
        project.is_active = True
        db.add(FinanceProjectAssignment(project_id=project.id, user_id=employee.id, assigned_by_id=bd.id, is_active=True))
        db.flush()

        expense = create_project_expense(
            db,
            actor=employee,
            project_id=project.id,
            payload=ProjectExpenseInput(
                expense_date=date(2026, 9, 10),
                category="field_material",
                purpose="Survey control material purchased for project",
                amount=Decimal("1200"),
                payment_source="EMPLOYEE_PAID",
            ),
        )
        submit_project_expense(db, actor=employee, expense_id=expense.id)
        decide_project_expense(
            db,
            actor=finance,
            expense_id=expense.id,
            payload=ProjectExpenseDecision(decision="approve", approved_amount=Decimal("1200"), comments="Receipt verified"),
        )
        vendor = create_vendor_invoice(
            db,
            actor=finance,
            project_id=project.id,
            payload=VendorInvoiceInput(
                vendor_name="Field Supplier",
                invoice_number="FS-1001",
                invoice_date=date(2026, 9, 10),
                category="field_material",
                description="Survey control material",
                currency_code="INR",
                taxable_amount=Decimal("1200"),
                payment_source="EMPLOYEE_PAID",
                linked_employee_expense_id=expense.id,
            ),
        )
        db.flush()

        assert vendor.payment_status == "PAID"
        assert db.get(ProjectVendorInvoice, vendor.id).linked_employee_expense_id == expense.id
        summary = project_cost_summary(db, project_id=project.id)
        assert summary["employee_cost_inr"] == 0.0
        assert summary["vendor_cost_inr"] == 1200.0
        assert summary["total_direct_cost_inr"] == 1200.0

        with pytest.raises(ValueError, match="not financially settled"):
            assert_commercial_closure_ready(db, project_id=project.id)

        reimburse_project_expense(
            db,
            actor=finance,
            expense_id=expense.id,
            payload=ProjectExpenseReimbursement(reimbursement_reference="UTR-EMP-001"),
        )
        # Missing "No More Project Expenses" declaration is informational only.
        # Once the employee-paid expense is reimbursed, Finance Closure may proceed.
        assert_commercial_closure_ready(db, project_id=project.id)

        declare_project_expenses(
            db,
            actor=employee,
            project_id=project.id,
            payload=ProjectExpenseDeclarationInput(phase_key="ORIGINAL", declaration_status="NO_MORE_EXPENSES"),
        )
        assert_commercial_closure_ready(db, project_id=project.id)


def test_legacy_project_without_commercial_records_is_not_blocked_by_commercial_guard():
    with SessionLocal() as db:
        owner = make_user(db, "legacy.owner@nakshatech.com", "bd", "Legacy Owner")
        project, _ = make_project(db, owner=owner, status="finance_closure_pending", code="COMM-LEGACY-01")
        assert db.scalar(select(ProjectCommercialEstimateRevision.id).where(ProjectCommercialEstimateRevision.project_id == project.id)) is None
        assert_commercial_closure_ready(db, project_id=project.id)


def test_company_paid_approved_expense_is_settled_for_closure_after_employee_declaration():
    with SessionLocal() as db:
        bd = make_user(db, "bd.companypaid@nakshatech.com", "bd", "BD Company Paid")
        finance = make_user(db, "finance.companypaid@nakshatech.com", "finance", "Finance Company Paid")
        employee = make_user(db, "employee.companypaid@nakshatech.com", "employee", "Employee Company Paid")
        project, _ = make_project(db, owner=bd, status="in_progress", code="COMM-COMPANY-01")
        project.is_active = True
        db.add(FinanceProjectAssignment(project_id=project.id, user_id=employee.id, assigned_by_id=bd.id, is_active=True))
        db.flush()

        expense = create_project_expense(
            db,
            actor=employee,
            project_id=project.id,
            payload=ProjectExpenseInput(
                expense_date=date(2026, 9, 11),
                category="printing",
                purpose="Company card printing charge",
                amount=Decimal("500"),
                payment_source="COMPANY_PAID",
            ),
        )
        submit_project_expense(db, actor=employee, expense_id=expense.id)
        decide_project_expense(
            db,
            actor=finance,
            expense_id=expense.id,
            payload=ProjectExpenseDecision(decision="approve", approved_amount=Decimal("500"), comments="Company-paid proof verified"),
        )
        declare_project_expenses(
            db,
            actor=employee,
            project_id=project.id,
            payload=ProjectExpenseDeclarationInput(phase_key="ORIGINAL", declaration_status="NO_MORE_EXPENSES"),
        )
        assert_commercial_closure_ready(db, project_id=project.id)


def test_draft_client_invoice_is_not_counted_as_billed_revenue_until_raised():
    with SessionLocal() as db:
        finance = make_user(db, "finance.draftbilling@nakshatech.com", "finance", "Finance Draft Billing")
        project, _ = make_project(db, owner=finance, status=READY_FOR_BILLING, code="COMM-DRAFT-INV-01")
        project.is_active = True

        invoice = create_invoice_draft(
            db,
            actor=finance,
            project_id=project.id,
            payload=InvoiceDraftCreate(
                invoice_number="INV-DRAFT-001",
                invoice_date=date(2026, 9, 21),
                due_date=date(2026, 10, 21),
                amount=Decimal("10000"),
                tax_amount=Decimal("1800"),
                tax_percent=Decimal("18"),
                currency="INR",
            ),
        )
        assert project_cost_summary(db, project_id=project.id)["billed_net_revenue_inr"] == 0.0

        raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
        db.flush()  # SessionLocal deliberately disables autoflush; the HTTP router commits before a later summary request.
        assert project_cost_summary(db, project_id=project.id)["billed_net_revenue_inr"] == 10000.0
