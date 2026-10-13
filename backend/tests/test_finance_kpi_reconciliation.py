from __future__ import annotations

import time
from datetime import date
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import OPEN_SALES_CATEGORIES, sales_revenue_overview
from app.modules.operations.lifecycle_models import ProjectInvoice, ProjectInvoicePayment
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str = "bd") -> User:
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


def _seed_project(
    db,
    *,
    suffix: str,
    department: str = "lidar",
    commercial_value: Decimal = Decimal("100000.00"),
    currency: str = "INR",
    invoices: list[dict] | None = None,
):
    bd = _user(db, f"bd.kpi.{suffix}@nakshatech.com", "bd")
    finance = _user(db, f"finance.kpi.{suffix}@nakshatech.com", "finance")
    client = FinanceClient(
        client_code=f"KPI-{suffix}",
        client_name=f"KPI Client {suffix}",
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
        project_code=f"KPI-P-{suffix}",
        project_name=f"KPI Project {suffix}",
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
        performing_department_code=department,
        status="PAYMENT_PENDING",
        commercial_value=commercial_value,
        currency=currency,
        created_by_id=bd.id,
        updated_by_id=bd.id,
    )
    db.add(workflow)
    db.flush()

    invoice_rows = []
    for index, spec in enumerate(invoices or [], start=1):
        invoice = ProjectInvoice(
            project_id=project.id,
            invoice_number=f"INV-{suffix}-{index}",
            status=spec.get("status", "PAYMENT_PENDING"),
            invoice_date=date(2026, 9, 5),
            due_date=date(2026, 9, 30),
            amount=spec["amount"],
            tax_amount=spec.get("tax_amount", Decimal("0.00")),
            currency=spec.get("currency", "INR"),
            fx_rate_to_inr=spec.get("fx_rate_to_inr"),
            total_inr=spec.get("total_inr"),
            created_by_id=finance.id,
        )
        db.add(invoice)
        db.flush()
        invoice_rows.append((invoice, finance, spec.get("payments", [])))

    return {
        "bd": bd,
        "finance": finance,
        "client": client,
        "project": project,
        "workflow": workflow,
        "invoices": invoice_rows,
    }


def _add_payment(db, *, project, invoice, finance, amount: Decimal, reference: str, fx_rate=None, inr_equivalent=None):
    payment = ProjectInvoicePayment(
        project_id=project.id,
        invoice_id=invoice.id,
        payment_reference=reference,
        payment_date=date(2026, 9, 20),
        amount=amount,
        payment_mode="bank_transfer",
        fx_rate_to_inr=fx_rate,
        inr_equivalent=inr_equivalent,
        recorded_by_id=finance.id,
    )
    db.add(payment)
    db.flush()
    return payment


def _assert_reconciled(payload: dict) -> None:
    summary = payload["kpi_summary"]
    categories_sum = sum(summary["categories"][key] for key in OPEN_SALES_CATEGORIES)
    assert summary["reconciled"] is True
    assert abs(summary["open_sales_inr"] - categories_sum) <= 0.01
    assert abs(summary["open_sales_inr"] - summary["categories_sum_inr"]) <= 0.01
    for row in payload["projects"]:
        project_categories = row["open_sales_categories"]
        project_sum = sum(project_categories[key] for key in OPEN_SALES_CATEGORIES)
        assert row["open_sales_reconciled"] is True
        assert abs(row["open_sales_inr"] - project_sum) <= 0.01


def test_multiple_invoices_on_one_project_reconcile():
    with SessionLocal() as db:
        seed = _seed_project(
            db,
            suffix="MULTIINV",
            commercial_value=Decimal("100000.00"),
            invoices=[
                {"amount": Decimal("40000.00"), "status": "PAYMENT_PENDING"},
                {"amount": Decimal("60000.00"), "status": "PARTIALLY_PAID"},
            ],
        )
        second_invoice, finance, _ = seed["invoices"][1]
        _add_payment(
            db,
            project=seed["project"],
            invoice=second_invoice,
            finance=finance,
            amount=Decimal("20000.00"),
            reference="MULTIINV-PARTIAL",
        )
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        categories = row["open_sales_categories"]
        assert categories["payment_pending_inr"] == 40000.0
        assert categories["partial_payment_inr"] == 60000.0
        assert categories["invoice_not_raised_inr"] == 0.0
        assert row["open_sales_inr"] == 100000.0
        _assert_reconciled(payload)
        assert payload["kpi_summary"]["categories"]["payment_pending_inr"] >= 40000.0
        db.rollback()


def test_multiple_payments_on_one_invoice_reconcile():
    with SessionLocal() as db:
        seed = _seed_project(
            db,
            suffix="MULTIPAY",
            commercial_value=Decimal("50000.00"),
            invoices=[{"amount": Decimal("50000.00"), "status": "PARTIALLY_PAID"}],
        )
        invoice, finance, _ = seed["invoices"][0]
        _add_payment(db, project=seed["project"], invoice=invoice, finance=finance, amount=Decimal("15000.00"), reference="MP-1")
        _add_payment(db, project=seed["project"], invoice=invoice, finance=finance, amount=Decimal("10000.00"), reference="MP-2")
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        assert row["received_against_open_sales_inr"] == 25000.0
        assert row["outstanding_inr"] == 25000.0
        assert row["open_sales_categories"]["partial_payment_inr"] == 50000.0
        _assert_reconciled(payload)
        db.rollback()


def test_partial_payment_category_and_balance():
    with SessionLocal() as db:
        seed = _seed_project(
            db,
            suffix="PARTIALCAT",
            commercial_value=Decimal("80000.00"),
            invoices=[{"amount": Decimal("80000.00"), "status": "PARTIALLY_PAID"}],
        )
        invoice, finance, _ = seed["invoices"][0]
        _add_payment(db, project=seed["project"], invoice=invoice, finance=finance, amount=Decimal("30000.00"), reference="PARTIAL-CAT")
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        assert row["open_sales_categories"]["partial_payment_inr"] == 80000.0
        assert row["partial_payment_balance_inr"] == 50000.0
        assert row["open_partial_invoice_count"] == 1
        _assert_reconciled(payload)
        assert payload["kpi_summary"]["collection"]["partial_payment_balance_inr"] >= 50000.0
        db.rollback()


def test_full_payment_and_closed_moves_to_revenue_not_open_sales():
    with SessionLocal() as db:
        seed = _seed_project(
            db,
            suffix="CLOSED",
            commercial_value=Decimal("120000.00"),
            invoices=[{"amount": Decimal("120000.00"), "status": "INVOICE_CLOSED"}],
        )
        invoice, finance, _ = seed["invoices"][0]
        _add_payment(db, project=seed["project"], invoice=invoice, finance=finance, amount=Decimal("120000.00"), reference="CLOSED-FULL")
        invoice.closed_by_id = finance.id
        invoice.closed_at = date(2026, 9, 28)
        db.flush()

        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        assert row["open_sales_inr"] == 0.0
        assert row["closed_revenue_inr"] == 120000.0
        assert all(row["open_sales_categories"][key] == 0.0 for key in OPEN_SALES_CATEGORIES)
        _assert_reconciled(payload)
        assert payload["kpi_summary"]["realized_revenue_inr"] >= 120000.0
        db.rollback()


def test_multi_currency_invoice_uses_fx_for_inr_categories():
    with SessionLocal() as db:
        seed = _seed_project(
            db,
            suffix="FX",
            commercial_value=Decimal("1000.00"),
            currency="USD",
            invoices=[
                {
                    "amount": Decimal("1000.00"),
                    "currency": "USD",
                    "fx_rate_to_inr": Decimal("83.50"),
                    "total_inr": Decimal("83500.00"),
                    "status": "PAYMENT_PENDING",
                }
            ],
        )
        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        assert row["open_sales_categories"]["payment_pending_inr"] == 83500.0
        assert row["open_sales_inr"] >= 83500.0
        assert row["currency"] == "USD"
        _assert_reconciled(payload)
        db.rollback()


def test_multi_department_scope_filters_kpi_summary():
    with SessionLocal() as db:
        lidar = _seed_project(db, suffix="DEPT-LIDAR", department="lidar", commercial_value=Decimal("100000.00"), invoices=[])
        ortho = _seed_project(db, suffix="DEPT-ORTHO", department="ortho", commercial_value=Decimal("200000.00"), invoices=[])
        civil = _seed_project(db, suffix="DEPT-CIVIL", department="civil", commercial_value=Decimal("50000.00"), invoices=[])
        db.flush()

        full = sales_revenue_overview(db)
        assert full["kpi_summary"]["open_sales_inr"] >= 350000.0
        _assert_reconciled(full)

        scoped = sales_revenue_overview(db, department_scope="lidar")
        scoped_ids = {row["project_id"] for row in scoped["projects"]}
        assert scoped_ids == {lidar["project"].id}
        assert scoped["kpi_summary"]["open_sales_inr"] == 100000.0
        _assert_reconciled(scoped)

        ortho_payload = sales_revenue_overview(db, department_scope="ortho")
        assert ortho_payload["kpi_summary"]["open_sales_inr"] == 200000.0
        assert ortho["project"].id in {row["project_id"] for row in ortho_payload["projects"]}

        civil_payload = sales_revenue_overview(db, department_scope="civil")
        assert civil_payload["kpi_summary"]["open_sales_inr"] == 50000.0
        db.rollback()


def test_project_without_invoices_is_invoice_not_raised():
    with SessionLocal() as db:
        seed = _seed_project(db, suffix="NOINV", commercial_value=Decimal("75000.00"), invoices=[])
        payload = sales_revenue_overview(db)
        row = next(item for item in payload["projects"] if item["project_id"] == seed["project"].id)
        assert row["invoice_not_raised"] is True
        assert row["open_sales_categories"]["invoice_not_raised_inr"] == 75000.0
        assert row["open_sales_inr"] == 75000.0
        _assert_reconciled(payload)
        assert payload["kpi_summary"]["counts"]["invoice_not_raised_projects"] >= 1
        db.rollback()


def test_large_dataset_performance_and_reconciliation():
    with SessionLocal() as db:
        for index in range(120):
            seed = _seed_project(
                db,
                suffix=f"PERF-{index:03d}",
                department=("lidar", "ortho", "civil", "mobile_mapping", "laser_scanning")[index % 5],
                commercial_value=Decimal("10000.00"),
                invoices=[
                    {"amount": Decimal("6000.00"), "status": "PAYMENT_PENDING"},
                    {"amount": Decimal("4000.00"), "status": "PARTIALLY_PAID"},
                ],
            )
            partial_invoice, finance, _ = seed["invoices"][1]
            _add_payment(
                db,
                project=seed["project"],
                invoice=partial_invoice,
                finance=finance,
                amount=Decimal("1000.00"),
                reference=f"PERF-PARTIAL-{index:03d}",
            )
        db.flush()

        started = time.perf_counter()
        payload = sales_revenue_overview(db)
        elapsed = time.perf_counter() - started
        assert elapsed < 5.0
        assert len(payload["projects"]) >= 120
        _assert_reconciled(payload)
        summary = payload["kpi_summary"]
        assert summary["open_sales_inr"] > 0
        assert summary["reconciled"] is True
        assert summary["counts"]["payment_pending_invoices"] >= 120
        assert summary["counts"]["partial_invoices"] >= 120
        db.rollback()
