from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import sales_revenue_overview
from app.modules.operations.lifecycle_models import ProjectInvoice
from app.modules.operations.lifecycle_schemas import (
    InvoiceDraftCreate,
    InvoicePaymentCreate,
    InvoiceRaise,
)
from app.modules.operations.lifecycle_service import (
    READY_FOR_BILLING,
    compute_invoice_payment_status,
    create_invoice_draft,
    raise_invoice,
    record_invoice_payment,
)
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


def _project(db, suffix: str, *, amount: str = "10000") -> tuple[User, FinanceProject, ProjectWorkflow, ProjectInvoice]:
    bd = _user(db, f"bd.invstatus.{suffix}@nakshatech.com", "bd")
    finance = _user(db, f"finance.invstatus.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"IS-{suffix}",
        client_name=f"Invoice Status Client {suffix}",
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
        project_code=f"IS-P-{suffix}",
        project_name=f"Invoice Status Project {suffix}",
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
        status=READY_FOR_BILLING,
        commercial_value=Decimal(amount),
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
            invoice_number=f"INV-IS-{suffix}",
            invoice_date=date(2026, 9, 5),
            due_date=date(2026, 10, 5),
            amount=Decimal(amount),
            tax_amount=Decimal("0"),
            currency="INR",
            payment_terms="30 days",
        ),
    )
    raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
    db.flush()
    return finance, project, workflow, invoice


def test_compute_invoice_payment_status_rules():
    assert compute_invoice_payment_status(invoice_total=Decimal("10000"), paid_total=Decimal("10000")) == "INVOICE_CLOSED"
    assert compute_invoice_payment_status(invoice_total=Decimal("10000"), paid_total=Decimal("4000")) == "PARTIALLY_PAID"
    assert compute_invoice_payment_status(invoice_total=Decimal("10000"), paid_total=Decimal("0")) == "PAYMENT_PENDING"
    assert compute_invoice_payment_status(invoice_total=Decimal("10000"), paid_total=Decimal("12000")) == "INVOICE_CLOSED"


def test_full_payment_closes_invoice_and_counts_as_revenue():
    with SessionLocal() as db:
        finance, project, _, invoice = _project(db, "FULL", amount="10000")
        assert invoice.status == "PAYMENT_PENDING"

        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="FULL-10000",
                payment_date=date(2026, 9, 20),
                amount=Decimal("10000"),
                payment_mode="bank_transfer",
            ),
        )
        db.flush()
        assert invoice.status == "INVOICE_CLOSED"

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        revenue = next(item for item in payload["revenue_events"] if item["project_id"] == project.id)
        assert row["closed_revenue_inr"] == 10000.0
        assert revenue["revenue_amount_inr"] == 10000.0
        db.rollback()


def test_partial_payment_sets_partially_paid_with_outstanding():
    with SessionLocal() as db:
        finance, project, _, invoice = _project(db, "PART", amount="10000")

        record_invoice_payment(
            db,
            actor=finance,
            invoice_id=invoice.id,
            payload=InvoicePaymentCreate(
                payment_reference="PART-4000",
                payment_date=date(2026, 9, 20),
                amount=Decimal("4000"),
                payment_mode="bank_transfer",
            ),
        )
        db.flush()
        assert invoice.status == "PARTIALLY_PAID"

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        assert row["outstanding_inr"] == 6000.0
        assert not any(item["project_id"] == project.id for item in payload["revenue_events"])
        db.rollback()


def test_no_payment_keeps_payment_pending():
    with SessionLocal() as db:
        _, project, _, invoice = _project(db, "NONE", amount="10000")
        assert invoice.status == "PAYMENT_PENDING"

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == project.id)
        assert row["outstanding_inr"] == 10000.0
        assert not any(item["project_id"] == project.id for item in payload["revenue_events"])
        db.rollback()
