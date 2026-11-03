"""Hard end-to-end workflow test for Management Project Tracking and Sales.

Covers the complete financial lifecycle that the Management register exposes:
BD approved sales value, raised Finance invoices (draft excluded), cash receipts
(period and as-of filters), partial payments, outstanding balances, expenses
(vendor payments + employee reimbursements), approved bad debts, project
details, access control, date validation and both export formats.

The numbers are deliberately independent per project so a regression in one
calculation cannot be hidden by a compensating error in another.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.api.dependencies import get_current_auth
from app.core.database import SessionLocal
from app.core.security import create_access_token
from app.models.entities import User
from app.modules.commercial.models import (
    ProjectCommercialEstimateRevision,
    ProjectExpense,
    ProjectVendorInvoice,
    ProjectVendorPayment,
)
from app.modules.finance.models import (
    FinanceClient,
    FinanceProject,
    FinanceProjectMasterProfile,
)
from app.modules.operations.lifecycle_models import (
    ProjectInvoice,
    ProjectInvoiceBadDebt,
    ProjectInvoicePayment,
)
from app.modules.operations.models import ProjectWorkflow
from app.routers.management_sales_reporting import (
    IST,
    build_report,
    reporting_service,
)
from app.routers.project_tracking_sales import build_project_tracking_router


TODAY = datetime.now(IST).date()
PERIOD_START = TODAY - timedelta(days=30)
PERIOD_END = TODAY
BASE = "/api/management/project-tracking-sales"


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
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


def _client(db, code: str, name: str, created_by: User) -> FinanceClient:
    row = FinanceClient(
        client_code=code,
        client_name=name,
        contact_person_name="Contact Person",
        contact_person_phone="9999999999",
        source_team="bd",
        source_person_name=created_by.full_name,
        is_active=True,
        created_by_id=created_by.id,
    )
    db.add(row)
    db.flush()
    return row


def _project(
    db,
    suffix: str,
    *,
    name: str,
    department: str,
    operational_status: str,
    bd: User,
    pm: User,
) -> tuple[FinanceProject, ProjectWorkflow]:
    client = _client(db, f"PTS-C-{suffix}", f"Client {suffix}", bd)
    project = FinanceProject(
        project_code=f"PTS-P-{suffix}",
        project_name=name,
        client_id=client.id,
        client_name=client.client_name,
        start_date=TODAY - timedelta(days=60),
        end_date=TODAY - timedelta(days=1),
        created_by_id=bd.id,
    )
    db.add(project)
    db.flush()

    db.add(
        FinanceProjectMasterProfile(
            project_id=project.id,
            project_status=operational_status,
            project_manager_id=pm.id,
            created_by_id=bd.id,
            updated_by_id=bd.id,
        )
    )
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=bd.id,
        status="CLOSED",
        performing_department_code=department,
        currency="INR",
        created_by_id=bd.id,
        updated_by_id=bd.id,
    )
    db.add(workflow)
    db.flush()
    return project, workflow


def _baseline(
    db,
    project: FinanceProject,
    *,
    value: str,
    approved_on: date,
    quotation: str,
    bd: User,
    approver: User,
) -> ProjectCommercialEstimateRevision:
    amount = Decimal(value)
    row = ProjectCommercialEstimateRevision(
        project_id=project.id,
        revision_no=1,
        is_baseline=True,
        status="APPROVED",
        is_locked=True,
        quotation_reference=quotation,
        scope_description=f"Approved scope for {project.project_code}",
        billing_type="FIXED",
        currency_code="INR",
        estimated_amount=amount,
        taxable_base_amount=amount,
        tax_percent=Decimal("0.00"),
        expected_tax=Decimal("0.00"),
        expected_gross=amount,
        fx_rate_to_inr=Decimal("1"),
        fx_rate_date=approved_on,
        fx_rate_source="BASE_CURRENCY",
        fx_rate_mode="BASE_CURRENCY",
        estimated_inr=amount,
        base_inr=amount,
        tax_inr=Decimal("0.00"),
        gross_inr=amount,
        estimate_date=approved_on,
        created_by_id=bd.id,
        approved_by_id=approver.id,
        approved_at=datetime.combine(approved_on, time(10, 0)),
    )
    db.add(row)
    db.flush()
    return row


def _invoice(
    db,
    project: FinanceProject,
    *,
    number: str,
    status: str,
    invoice_date: date,
    amount: str,
    creator: User,
) -> ProjectInvoice:
    value = Decimal(amount)
    row = ProjectInvoice(
        project_id=project.id,
        invoice_number=number,
        status=status,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=30),
        amount=value,
        tax_amount=Decimal("0.00"),
        currency="INR",
        fx_rate_to_inr=Decimal("1"),
        total_inr=value,
        created_by_id=creator.id,
    )
    db.add(row)
    db.flush()
    return row


def _payment(
    db,
    project: FinanceProject,
    invoice: ProjectInvoice,
    *,
    reference: str,
    on: date,
    amount: str,
    creator: User,
) -> ProjectInvoicePayment:
    row = ProjectInvoicePayment(
        project_id=project.id,
        invoice_id=invoice.id,
        payment_reference=reference,
        payment_date=on,
        amount=Decimal(amount),
        payment_mode="bank_transfer",
        recorded_by_id=creator.id,
    )
    db.add(row)
    db.flush()
    return row


def _permissions(db):
    vinod = _user(db, "vinod@nakshatech.com", "management", "Vinod")
    chethan = _user(db, "chethan@nakshatech.com", "management", "Chethan")
    outsider = _user(db, "operations.head@nakshatech.com", "management", "Other Management")
    finance = _user(db, "finance.pts@nakshatech.com", "finance", "Finance Lead")
    bd = _user(db, "bd.pts@nakshatech.com", "bd", "BD Lead")
    pm = _user(db, "pm.pts@nakshatech.com", "employee", "Project Manager")
    return vinod, chethan, outsider, finance, bd, pm


def _seed(db):
    """Seed three projects that exercise every branch of the report."""
    vinod, chethan, outsider, finance, bd, pm = _permissions(db)

    # --- Project A: fully closed, one invoice fully paid, one partly written off.
    full, _ = _project(
        db,
        "FULL",
        name="Closed Project",
        department="lidar",
        operational_status="active",
        bd=bd,
        pm=pm,
    )
    _baseline(
        db,
        full,
        value="100000",
        approved_on=TODAY - timedelta(days=20),
        quotation="QUO-FULL",
        bd=bd,
        approver=vinod,
    )
    full_paid = _invoice(
        db,
        full,
        number="INV-FULL-1",
        status="INVOICE_CLOSED",
        invoice_date=TODAY - timedelta(days=10),
        amount="60000",
        creator=finance,
    )
    _payment(db, full, full_paid, reference="FULL-CASH-1", on=TODAY - timedelta(days=9), amount="30000", creator=finance)
    _payment(db, full, full_paid, reference="FULL-CASH-2", on=TODAY - timedelta(days=8), amount="30000", creator=finance)

    written_off = _invoice(
        db,
        full,
        number="INV-FULL-2",
        status="INVOICE_CLOSED",
        invoice_date=TODAY - timedelta(days=9),
        amount="40000",
        creator=finance,
    )
    _payment(db, full, written_off, reference="FULL-CASH-3", on=TODAY - timedelta(days=7), amount="30000", creator=finance)
    # A future-dated receipt must never inflate period receipts or as-of cash.
    _payment(db, full, written_off, reference="FULL-FUTURE", on=TODAY + timedelta(days=1), amount="5000", creator=finance)
    db.add(
        ProjectInvoiceBadDebt(
            project_id=full.id,
            invoice_id=written_off.id,
            status="APPROVED",
            proposed_amount=Decimal("10000"),
            approved_amount=Decimal("10000"),
            recovered_amount=Decimal("0"),
            currency="INR",
            reason="Client confirmed the balance is unrecoverable.",
            collection_attempts="Calls, emails and a written reminder recorded.",
            proposed_by_id=finance.id,
            reviewed_by_id=vinod.id,
            reviewed_at=datetime.combine(TODAY - timedelta(days=6), time(11, 0)),
        )
    )

    vendor_invoice = ProjectVendorInvoice(
        project_id=full.id,
        vendor_name="Survey Vendor",
        invoice_number="VINV-FULL-1",
        invoice_date=TODAY - timedelta(days=15),
        category="survey",
        description="Field survey subcontract",
        taxable_amount=Decimal("13000"),
        gross_amount=Decimal("13000"),
        taxable_inr=Decimal("13000"),
        tax_inr=Decimal("0"),
        gross_inr=Decimal("13000"),
        created_by_id=finance.id,
    )
    db.add(vendor_invoice)
    db.flush()
    db.add_all(
        [
            ProjectVendorPayment(
                vendor_invoice_id=vendor_invoice.id,
                project_id=full.id,
                amount=Decimal("4000"),
                amount_inr=Decimal("4000"),
                payment_date=TODAY - timedelta(days=5),
                payment_reference="VP-IN-PERIOD",
                recorded_by_id=finance.id,
            ),
            ProjectVendorPayment(
                vendor_invoice_id=vendor_invoice.id,
                project_id=full.id,
                amount=Decimal("9000"),
                amount_inr=Decimal("9000"),
                payment_date=TODAY - timedelta(days=40),
                payment_reference="VP-OLD-PERIOD",
                recorded_by_id=finance.id,
            ),
        ]
    )
    db.add_all(
        [
            ProjectExpense(
                expense_code="EXP-FULL-REIMBURSED",
                project_id=full.id,
                employee_id=pm.id,
                expense_date=TODAY - timedelta(days=4),
                category="travel",
                purpose="Site visit",
                amount=Decimal("1200"),
                approved_amount=Decimal("1000"),
                status="REIMBURSED",
                reimbursed_at=datetime.combine(TODAY - timedelta(days=3), time(9, 30)),
                reimbursement_reference="REIMB-FULL-1",
            ),
            ProjectExpense(
                expense_code="EXP-FULL-PENDING",
                project_id=full.id,
                employee_id=pm.id,
                expense_date=TODAY - timedelta(days=2),
                category="travel",
                purpose="Not reimbursed yet",
                amount=Decimal("500"),
                status="APPROVED",
            ),
        ]
    )

    # --- Project B: partially paid open invoice + draft invoice + unbilled balance.
    partial, _ = _project(
        db,
        "PARTIAL",
        name="Partially Paid Project",
        department="ortho",
        operational_status="active",
        bd=bd,
        pm=pm,
    )
    _baseline(
        db,
        partial,
        value="50000",
        approved_on=TODAY - timedelta(days=15),
        quotation="QUO-PARTIAL",
        bd=bd,
        approver=chethan,
    )
    partial_invoice = _invoice(
        db,
        partial,
        number="INV-PARTIAL-1",
        status="PARTIALLY_PAID",
        invoice_date=TODAY - timedelta(days=6),
        amount="20000",
        creator=finance,
    )
    _payment(db, partial, partial_invoice, reference="PARTIAL-CASH-1", on=TODAY - timedelta(days=4), amount="5000", creator=finance)
    _invoice(
        db,
        partial,
        number="INV-PARTIAL-DRAFT",
        status="INVOICE_DRAFT",
        invoice_date=TODAY - timedelta(days=3),
        amount="5000",
        creator=finance,
    )

    # --- Project C: no activity in the current period, but an open receivable.
    stale, _ = _project(
        db,
        "STALE",
        name="Historical Project",
        department="civil",
        operational_status="inactive",
        bd=bd,
        pm=pm,
    )
    _baseline(
        db,
        stale,
        value="80000",
        approved_on=TODAY - timedelta(days=90),
        quotation="QUO-STALE",
        bd=bd,
        approver=vinod,
    )
    _invoice(
        db,
        stale,
        number="INV-STALE-1",
        status="PAYMENT_PENDING",
        invoice_date=TODAY - timedelta(days=85),
        amount="80000",
        creator=finance,
    )

    db.commit()
    return {
        "vinod": vinod.id,
        "chethan": chethan.id,
        "outsider": outsider.id,
        "finance": finance.id,
        "full": full.id,
        "partial": partial.id,
        "stale": stale.id,
        "emails": {
            "vinod": vinod.email,
            "chethan": chethan.email,
            "outsider": outsider.email,
            "finance": finance.email,
        },
    }


@pytest.fixture()
def world():
    with SessionLocal() as db:
        ids = _seed(db)
    return ids


@pytest.fixture()
def api():
    app = FastAPI()
    app.include_router(build_project_tracking_router(get_current_auth, reporting_service))
    return TestClient(app)


def _token(email: str, role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(email, role)}"}


def _report(start=PERIOD_START, end=PERIOD_END):
    return build_report(start, end)


def _row(report, project_id: int) -> dict:
    return next(row for row in report["projects"] if row["id"] == str(project_id))


# ---------------------------------------------------------------------------
# Core calculations
# ---------------------------------------------------------------------------


def test_current_period_register_and_summary_cover_the_full_lifecycle(world):
    report = _report()
    summary = report["summary"]

    # The report API stores money in paise; the frontend divides by 100 for display.
    assert summary["sales_approved"] == (100000 + 50000) * 100
    assert summary["invoiced"] == (60000 + 40000 + 20000) * 100  # draft excluded
    assert summary["payments_received"] == (30000 + 30000 + 30000 + 5000) * 100
    assert summary["expenses"] == (4000 + 1000) * 100  # old vendor payment + pending reimbursement excluded
    assert summary["bad_debts"] == 10000 * 100
    assert summary["outstanding"] == (0 + 25000 + 15000 + 5000 + 80000) * 100

    full = _row(report, world["full"])
    assert full["sales_approved"] == 100000 * 100
    assert full["payments_received"] == 90000 * 100
    assert full["outstanding"] == 0
    assert full["expenses"] == 5000 * 100
    assert full["finance_status"] == "Moved to Revenue"
    assert full["operational_status"] == "active"
    assert full["department"] == "LiDAR"
    assert full["manager"] == "Project Manager"

    partial = _row(report, world["partial"])
    assert partial["sales_approved"] == 50000 * 100
    assert partial["payments_received"] == 5000 * 100
    assert partial["outstanding"] == 45000 * 100
    assert partial["expenses"] == 0
    assert partial["finance_status"] == "Partially Paid"

    stale = _row(report, world["stale"])
    assert stale["sales_approved"] == 0  # approval happened before the selected period
    assert stale["payments_received"] == 0
    assert stale["outstanding"] == 80000 * 100
    assert stale["finance_status"] == "Payment Pending"
    assert stale["operational_status"] == "inactive"


def test_partial_payments_only_count_receipts_against_open_partial_invoices(world):
    """A closed invoice resolved by an approved write-off is not a partial payment.

    The written-off invoice has a gross balance but no collectible balance. Its
    receipts are period cash (already counted in payments_received) and must not
    inflate the "Partial Payments" KPI.
    """
    summary = _report()["summary"]

    assert summary["partial_payments"] == 5000 * 100


def test_summary_reconciles_with_register_rows(world):
    report = _report()
    summary = report["summary"]
    rows = report["projects"]

    assert summary["sales_approved"] == sum(row["sales_approved"] for row in rows)
    assert summary["payments_received"] == sum(row["payments_received"] for row in rows)
    assert summary["outstanding"] == sum(row["outstanding"] for row in rows)
    assert summary["expenses"] == sum(row["expenses"] for row in rows)
    # build_report() carries the drill-down payload; the HTTP layer strips it (asserted below).
    assert "_details" in report


def test_historical_period_marks_unavailable_balances_and_keeps_dated_totals(world):
    historical_start = TODAY - timedelta(days=120)
    historical_end = TODAY - timedelta(days=60)
    report = _report(historical_start, historical_end)
    summary = report["summary"]

    # Only the stale project's baseline approval and invoice fall inside this window.
    assert summary["sales_approved"] == 80000 * 100
    assert summary["invoiced"] == 80000 * 100
    assert summary["payments_received"] == 0
    assert summary["expenses"] == 0
    assert summary["partial_payments"] is None
    assert summary["outstanding"] is None
    assert summary["bad_debts"] is None
    assert any("Historical" in note for note in report["notes"])

    for row in report["projects"]:
        assert row["outstanding"] is None
        assert row["payments_received"] == 0


def test_period_boundaries_are_inclusive(world):
    # The partial invoice was raised on TODAY-6 and its receipt landed on TODAY-4.
    start = TODAY - timedelta(days=6)
    end = TODAY - timedelta(days=4)
    report = _report(start, end)

    assert report["summary"]["invoiced"] == 20000 * 100
    assert report["summary"]["payments_received"] == 5000 * 100

    partial = _row(report, world["partial"])
    assert partial["sales_approved"] == 0  # baseline approved on TODAY-15
    assert partial["payments_received"] == 5000 * 100
    assert partial["outstanding"] is None


def test_project_detail_exposes_every_financial_section(world):
    result = build_report(date(2000, 1, 1), PERIOD_END)["_details"]

    full = result[str(world["full"])]
    assert full["project"]["sales_approved"] == 100000 * 100
    assert full["project"]["payments_received"] == 90000 * 100

    assert [item["invoice_number"] for item in full["sales_invoices"]] == ["QUO-FULL"]
    assert full["sales_invoices"][0]["amount_paise"] == 10_000_000

    assert sorted(item["invoice_number"] for item in full["finance_invoices"]) == [
        "INV-FULL-1",
        "INV-FULL-2",
    ]
    assert sorted(item["amount_paise"] for item in full["finance_invoices"]) == [4_000_000, 6_000_000]

    # All receipts up to the as-of date are listed, but the future-dated one is not.
    assert sorted(item["payment_reference"] for item in full["payments"]) == [
        "FULL-CASH-1",
        "FULL-CASH-2",
        "FULL-CASH-3",
    ]
    assert sum(item["amount_paise"] for item in full["payments"]) == 9_000_000

    # Detail is an all-time drill-down, so both vendor payments are visible here.
    assert sum(item["amount_paise"] for item in full["expenses"]) == 1_400_000
    assert {item["type"] for item in full["expenses"]} == {
        "Vendor payment",
        "Employee reimbursement",
    }

    assert len(full["bad_debts"]) == 1
    assert full["bad_debts"][0]["amount_paise"] == 1_000_000

    partial = result[str(world["partial"])]
    assert [item["invoice_number"] for item in partial["finance_invoices"]] == [
        "INV-PARTIAL-1",
        "INV-PARTIAL-DRAFT",
    ]
    assert sum(item["amount_paise"] for item in partial["payments"]) == 500_000
    assert partial["bad_debts"] == []


# ---------------------------------------------------------------------------
# HTTP contract, access control and validation
# ---------------------------------------------------------------------------


def test_dashboard_http_contract_and_cache_headers(world, api):
    headers = _token(world["emails"]["vinod"], "management")
    response = api.get(
        f"{BASE}/dashboard",
        params={"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["sales_approved"] == 150000 * 100
    assert body["summary"]["bad_debts"] == 10000 * 100
    assert len(body["projects"]) == 3
    assert "_details" not in body
    assert "no-store" in response.headers["cache-control"]


def test_access_endpoint_and_management_identity_restriction(world, api):
    allowed = _token(world["emails"]["vinod"], "management")
    other_management = _token(world["emails"]["outsider"], "management")
    finance = _token(world["emails"]["finance"], "finance")

    assert api.get(f"{BASE}/access", headers=allowed).json() == {"allowed": True}
    assert api.get(f"{BASE}/access").status_code == 401
    assert api.get(f"{BASE}/access", headers=finance).status_code == 403
    assert api.get(f"{BASE}/access", headers=other_management).status_code == 403
    assert api.get(f"{BASE}/access", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_date_validation_and_missing_project_detail(world, api):
    headers = _token(world["emails"]["vinod"], "management")

    reversed_range = api.get(
        f"{BASE}/dashboard",
        params={"start": TODAY.isoformat(), "end": (TODAY - timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert reversed_range.status_code == 422

    future_end = api.get(
        f"{BASE}/dashboard",
        params={"start": (TODAY - timedelta(days=1)).isoformat(), "end": (TODAY + timedelta(days=1)).isoformat()},
        headers=headers,
    )
    assert future_end.status_code == 422

    missing = api.get(
        f"{BASE}/projects/999999",
        params={"end": PERIOD_END.isoformat()},
        headers=headers,
    )
    assert missing.status_code == 404

    no_end = api.get(f"{BASE}/projects/{world['full']}", headers=headers)
    assert no_end.status_code == 422


def test_project_detail_endpoint_matches_service_detail(world, api):
    headers = _token(world["emails"]["chethan"], "management")
    response = api.get(
        f"{BASE}/projects/{world['full']}",
        params={"end": PERIOD_END.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    detail = response.json()
    assert set(detail) == {
        "project",
        "sales_invoices",
        "finance_invoices",
        "payments",
        "expenses",
        "bad_debts",
    }
    assert detail["project"]["id"] == str(world["full"])
    assert detail["bad_debts"][0]["invoice_number"] == "INV-FULL-2"
    assert "no-store" in response.headers["cache-control"]


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


def test_excel_export_contains_register_rows_and_is_formula_safe(world, api):
    with SessionLocal() as db:
        project = db.get(FinanceProject, world["stale"])
        project.project_name = "=1+1"
        db.commit()

    headers = _token(world["emails"]["vinod"], "management")
    response = api.get(
        f"{BASE}/export/xlsx",
        params={"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "project-tracking.xlsx" in response.headers["content-disposition"]

    workbook = load_workbook(filename=BytesIO(response.content))
    sheet = workbook["Project Tracking"]
    assert [cell.value for cell in sheet[1]] == [
        "Project",
        "Client",
        "Department",
        "Manager",
        "Sales (INR)",
        "Received (INR)",
        "Outstanding (INR)",
    ]
    assert sheet.max_row == 4  # header + three projects
    assert float(sheet.cell(row=2, column=5).value) == 100000.0
    assert float(sheet.cell(row=2, column=6).value) == 90000.0
    assert float(sheet.cell(row=2, column=7).value) == 0.0
    assert sheet.cell(row=4, column=1).value == "'=1+1"


def test_pdf_export_returns_a_valid_pdf(world, api):
    headers = _token(world["emails"]["vinod"], "management")
    response = api.get(
        f"{BASE}/export/pdf",
        params={"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert "project-tracking.pdf" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")
    assert len(response.content) > 500


def test_export_rejects_unsupported_format(world, api):
    headers = _token(world["emails"]["vinod"], "management")
    response = api.get(
        f"{BASE}/export/csv",
        params={"start": PERIOD_START.isoformat(), "end": PERIOD_END.isoformat()},
        headers=headers,
    )

    assert response.status_code == 400
