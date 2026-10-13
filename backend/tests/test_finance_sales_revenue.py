from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str) -> User:
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


def _project(db, suffix: str):
    bd = _user(db, f"bd.salesrev.{suffix}@nakshatech.com", "bd")
    finance = _user(db, f"finance.salesrev.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"SR-{suffix}",
        client_name=f"Sales Revenue Client {suffix}",
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
        project_code=f"SR-P-{suffix}",
        project_name=f"Sales Revenue Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 10, 31),
        created_by_id=bd.id,
    )
    db.add(project)
    db.flush()
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=bd.id,
        performing_department_code="lidar",
        status="PAYMENT_PENDING",
        commercial_value=Decimal("100000.00"),
        currency="INR",
        created_by_id=bd.id,
        updated_by_id=bd.id,
    )
    db.add(workflow)
    db.flush()
    invoice = ProjectInvoice(
        project_id=project.id,
        invoice_number=f"INV-SR-{suffix}",
        status="PAYMENT_PENDING",
        invoice_date=date(2026, 9, 5),
        due_date=date(2026, 9, 30),
        amount=Decimal("100000.00"),
        tax_amount=Decimal("0.00"),
        currency="INR",
        created_by_id=finance.id,
    )
    db.add(invoice)
    db.flush()
    return bd, finance, project, workflow, invoice


def test_partial_payment_remains_sales_and_not_revenue():
    with SessionLocal() as db:
        _, finance, project, _, invoice = _project(db, "PARTIAL")
        payment = ProjectInvoicePayment(
            project_id=project.id,
            invoice_id=invoice.id,
            payment_reference="PARTIAL-REF",
            payment_date=date(2026, 9, 20),
            amount=Decimal("40000.00"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        )
        db.add(payment)
        invoice.status = "PARTIALLY_PAID"
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        assert row["sales_visible"] is True
        assert row["sales_status"] == "Partially Paid"
        assert row["received_against_open_sales_inr"] == 40000.0
        assert row["outstanding_inr"] == 60000.0
        assert not any(item["project_id"] == project.id for item in payload["revenue_events"])
        db.rollback()


def test_full_payment_not_closed_still_remains_sales():
    with SessionLocal() as db:
        _, finance, project, workflow, invoice = _project(db, "PAIDOPEN")
        payment = ProjectInvoicePayment(
            project_id=project.id,
            invoice_id=invoice.id,
            payment_reference="FULL-OPEN-REF",
            payment_date=date(2026, 9, 25),
            amount=Decimal("100000.00"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        )
        db.add(payment)
        invoice.status = "PAYMENT_RECEIVED"
        workflow.status = "PAYMENT_RECEIVED"
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        assert row["sales_visible"] is True
        assert row["sales_status"] == "Payment Received / Awaiting Closure"
        assert row["outstanding_inr"] == 0.0
        assert not any(item["project_id"] == project.id for item in payload["revenue_events"])
        db.rollback()


def test_only_closed_fully_paid_invoice_appears_in_revenue():
    with SessionLocal() as db:
        _, finance, project, workflow, invoice = _project(db, "CLOSED")
        payment = ProjectInvoicePayment(
            project_id=project.id,
            invoice_id=invoice.id,
            payment_reference="CLOSED-REF",
            payment_date=date(2026, 9, 28),
            amount=Decimal("100000.00"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        )
        db.add(payment)
        invoice.status = "INVOICE_CLOSED"
        invoice.closed_by_id = finance.id
        invoice.closed_at = payment.created_at
        workflow.status = "INVOICE_CLOSED"
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        revenue = next(item for item in payload["revenue_events"] if item["project_id"] == project.id)
        assert row["sales_visible"] is False
        assert row["closed_revenue_inr"] == 100000.0
        assert revenue["revenue_amount_inr"] == 100000.0
        assert revenue["finance_invoice_number"] == invoice.invoice_number
        assert revenue["department_code"] == "lidar"
        db.rollback()


def test_closed_status_without_full_payment_is_not_revenue():
    with SessionLocal() as db:
        _, finance, project, workflow, invoice = _project(db, "BAD-CLOSED")
        payment = ProjectInvoicePayment(
            project_id=project.id,
            invoice_id=invoice.id,
            payment_reference="BAD-CLOSED-REF",
            payment_date=date(2026, 9, 29),
            amount=Decimal("25000.00"),
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        )
        db.add(payment)
        invoice.status = "INVOICE_CLOSED"
        workflow.status = "INVOICE_CLOSED"
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        assert row["sales_visible"] is True
        assert row["received_against_open_sales_inr"] == 25000.0
        assert row["outstanding_inr"] == 75000.0
        assert not any(item["project_id"] == project.id for item in payload["revenue_events"])
        db.rollback()
