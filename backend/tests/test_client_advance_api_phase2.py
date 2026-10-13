from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.finance.advance import ClientAdvanceFollowUp, ClientAdvanceStatusHistory, ClientAdvanceTransaction
from app.modules.finance.advance_schemas import ClientAdvanceFollowUpCreate, ClientAdvanceTransactionCreate
from app.modules.finance.advance_service import (
    add_advance_followup,
    advance_projects,
    advance_summary,
    derive_advance_status,
    record_advance_transaction,
)
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.models import OrthoProjectMember, OrthoProjectProfile, ProjectWorkflow


def _user(db, email: str, role: str, name: str | None = None) -> User:
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


def _project(
    db,
    *,
    suffix: str,
    bd: User,
    pm: User | None = None,
    advance_required: bool = True,
    advance_amount: Decimal = Decimal("100000.00"),
    expected_date: date | None = None,
    final_date: date | None = None,
) -> FinanceProject:
    today = date.today()
    client = FinanceClient(
        client_code=f"ADV-C-{suffix}",
        client_name=f"Advance Client {suffix}",
        contact_person_name="Accounts Contact",
        contact_person_phone="9999999999",
        source_team="bd_team",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=bd.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"ADV-P-{suffix}",
        project_name=f"Advance Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        project_source_team="bd_team",
        project_source_person_name=bd.full_name,
        created_by_id=bd.id,
    )
    db.add(project)
    db.flush()
    db.add(ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=bd.id,
        status="finance_approved",
        performing_department_code="lidar",
        commercial_value=Decimal("500000.00"),
        currency="INR",
        created_by_id=bd.id,
        updated_by_id=bd.id,
    ))
    if pm is not None:
        db.add(FinanceProjectMasterProfile(
            project_id=project.id,
            project_status="active",
            project_manager_id=pm.id,
            created_by_id=bd.id,
            updated_by_id=bd.id,
        ))
    db.add(ProjectCommercialEstimateRevision(
        project_id=project.id,
        revision_no=1,
        is_baseline=True,
        status="APPROVED",
        is_locked=True,
        scope_description="Advance API test scope",
        billing_type="fixed_price",
        payment_terms="20% advance before mobilization" if advance_required else "30 days after invoice",
        currency_code="INR",
        estimated_amount=Decimal("500000.00"),
        taxable_base_amount=Decimal("500000.00"),
        tax_percent=Decimal("0"),
        expected_tax=Decimal("0"),
        expected_gross=Decimal("500000.00"),
        advance_required=advance_required,
        advance_payment_type="fixed_advance" if advance_required else "no_advance",
        advance_amount=advance_amount if advance_required else None,
        advance_currency_code="INR" if advance_required else None,
        expected_advance_date=expected_date or today + timedelta(days=5),
        final_advance_date=final_date or today + timedelta(days=10),
        fx_rate_to_inr=Decimal("1"),
        fx_rate_date=today,
        fx_rate_source="BASE_CURRENCY",
        fx_rate_mode="BASE_CURRENCY",
        estimated_inr=Decimal("500000.00"),
        base_inr=Decimal("500000.00"),
        tax_inr=Decimal("0"),
        gross_inr=Decimal("500000.00"),
        estimate_date=today,
        created_by_id=bd.id,
    ))
    db.flush()
    return project


def test_advance_summary_and_pipeline_use_isolated_inr_totals():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.advance.summary@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.advance.summary@nakshatech.com", "bd", "BD Owner")
        overdue = _project(
            db,
            suffix="SUMMARY-OVERDUE",
            bd=bd,
            expected_date=today - timedelta(days=3),
            final_date=today - timedelta(days=1),
        )
        _project(db, suffix="SUMMARY-NONE", bd=bd, advance_required=False)
        db.add(ClientAdvanceTransaction(
            project_id=overdue.id,
            client_id=overdue.client_id,
            sequence=1,
            amount=Decimal("40000.00"),
            currency="INR",
            amount_inr=Decimal("40000.00"),
            fx_rate=Decimal("1"),
            payment_date=today,
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        ))
        db.flush()

        summary = advance_summary(db, user=finance, effective_role="finance", as_of=today)
        assert summary["total_advance_expected"] == 100000.0
        assert summary["total_advance_received"] == 40000.0
        assert summary["total_advance_pending"] == 60000.0
        assert summary["total_overdue_advance"] == 60000.0
        assert summary["counts_by_status"]["overdue"] == 1
        assert summary["counts_by_status"]["not_required"] == 1

        rows = advance_projects(db, user=finance, effective_role="finance", as_of=today)
        row = next(item for item in rows if item["project_id"] == overdue.id)
        assert row["client"] == "Advance Client SUMMARY-OVERDUE"
        assert row["department"] == "LiDAR"
        assert row["bd_person"] == "BD Owner"
        assert row["project_value"] == 500000.0
        assert row["received_amount"] == 40000.0
        assert row["pending_amount"] == 60000.0
        assert row["status"] == "overdue"


def test_partial_and_multiple_advance_transactions_create_derived_history():
    with SessionLocal() as db:
        finance = _user(db, "finance.advance.multiple@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.advance.multiple@nakshatech.com", "bd", "BD")
        project = _project(db, suffix="MULTIPLE", bd=bd)

        first = record_advance_transaction(
            db,
            project_id=project.id,
            payload=ClientAdvanceTransactionCreate(
                amount=Decimal("40000"),
                currency="inr",
                payment_date=date.today(),
                payment_mode="bank transfer",
                reference_number="ADV-ONE",
                bank_reference="BANK-ONE",
                attachment="receipts/adv-one.pdf",
            ),
            actor=finance,
            effective_role="finance",
        )
        assert first["status"] == "partial_received"
        assert first["transaction"]["amount_inr"] == 40000.0

        second = record_advance_transaction(
            db,
            project_id=project.id,
            payload=ClientAdvanceTransactionCreate(
                amount=Decimal("60000"),
                currency="INR",
                payment_date=date.today(),
                payment_mode="rtgs",
                reference_number="ADV-TWO",
            ),
            actor=finance,
            effective_role="finance",
        )
        assert second["status"] == "received"
        assert db.scalar(select(ClientAdvanceTransaction).where(
            ClientAdvanceTransaction.project_id == project.id,
            ClientAdvanceTransaction.sequence == 2,
        )) is not None
        history = list(db.scalars(select(ClientAdvanceStatusHistory).where(
            ClientAdvanceStatusHistory.project_id == project.id
        ).order_by(ClientAdvanceStatusHistory.id)).all())
        assert [(row.old_status, row.new_status) for row in history] == [
            ("requested", "partial_received"),
            ("partial_received", "received"),
        ]


def test_followup_creation_uses_separate_client_advance_table():
    with SessionLocal() as db:
        finance = _user(db, "finance.advance.followup@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.advance.followup@nakshatech.com", "bd", "BD")
        project = _project(db, suffix="FOLLOWUP", bd=bd)
        result = add_advance_followup(
            db,
            project_id=project.id,
            payload=ClientAdvanceFollowUpCreate(
                contact_person="Client Accounts",
                communication_type="phone",
                remarks="Client confirmed transfer is in process.",
                next_followup_date=date.today() + timedelta(days=2),
            ),
            actor=finance,
            effective_role="finance",
        )
        assert result["contact_person"] == "Client Accounts"
        assert result["communication_type"] == "phone"
        assert db.scalar(select(ClientAdvanceFollowUp).where(
            ClientAdvanceFollowUp.project_id == project.id
        )) is not None


def test_status_priority_is_fully_derived():
    today = date.today()
    base = dict(
        advance_required=True,
        terms_exist=True,
        expected_inr=Decimal("100"),
        received_inr=Decimal("0"),
        adjusted_inr=Decimal("0"),
        expected_date=today + timedelta(days=1),
        final_date=today + timedelta(days=2),
        invoice_closed=False,
        as_of=today,
    )
    assert derive_advance_status(**{**base, "advance_required": False}) == "not_required"
    assert derive_advance_status(**{**base, "received_inr": Decimal("100"), "adjusted_inr": Decimal("100"), "invoice_closed": True}) == "closed"
    assert derive_advance_status(**{**base, "received_inr": Decimal("100"), "adjusted_inr": Decimal("10")}) == "adjusted"
    assert derive_advance_status(**{**base, "received_inr": Decimal("100")}) == "received"
    assert derive_advance_status(**{**base, "final_date": today - timedelta(days=1)}) == "overdue"
    assert derive_advance_status(**{**base, "received_inr": Decimal("40")}) == "partial_received"
    assert derive_advance_status(**{**base, "expected_date": today}) == "pending"
    assert derive_advance_status(**base) == "requested"


def test_advance_api_permissions_and_pm_redaction():
    with SessionLocal() as db:
        finance = _user(db, "finance.advance.api@nakshatech.com", "finance", "Finance")
        management = _user(db, "management.advance.api@nakshatech.com", "management", "Management")
        bd_one = _user(db, "bd.one.advance.api@nakshatech.com", "bd", "BD One")
        bd_two = _user(db, "bd.two.advance.api@nakshatech.com", "bd", "BD Two")
        pm = _user(db, "pm.advance.api@nakshatech.com", "lidar", "LiDAR PM")
        production = _user(db, "production.advance.api@nakshatech.com", "employee", "Production")
        own_project = _project(db, suffix="API-OWN", bd=bd_one, pm=pm)
        _project(db, suffix="API-OTHER", bd=bd_two)
        db.add(OrthoProjectProfile(
            project_id=own_project.id,
            project_manager_user_id=pm.id,
            created_by_id=pm.id,
        ))
        db.add(OrthoProjectMember(
            project_id=own_project.id,
            user_id=production.id,
            member_role="production",
            assigned_by_id=pm.id,
        ))
        db.commit()
        users = {row.role: row for row in (finance, management, pm, production)}
        users["bd_one"] = bd_one

    selected = users["finance"]

    def auth_override():
        return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    client = TestClient(app)
    try:
        response = client.post(
            f"/api/finance/advance-payments/{own_project.id}/transactions",
            json={
                "amount": "25000.00",
                "currency": "INR",
                "payment_date": date.today().isoformat(),
                "payment_mode": "neft",
                "reference_number": "API-ADV-1",
                "bank_reference": "API-BANK-1",
                "attachment": "receipts/api-adv-1.pdf",
            },
        )
        assert response.status_code == 201, response.text

        response = client.post(
            f"/api/finance/advance-payments/{own_project.id}/followups",
            json={
                "contact_person": "Client Accounts",
                "communication_type": "email",
                "remarks": "Requested remittance advice.",
                "next_followup_date": (date.today() + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text

        selected = users["management"]
        assert client.get("/api/finance/advance-payments/summary").status_code == 200
        assert client.post(
            f"/api/finance/advance-payments/{own_project.id}/followups",
            json={"contact_person": "X Y", "communication_type": "email", "remarks": "Read only"},
        ).status_code == 403

        selected = users["bd_one"]
        bd_rows = client.get("/api/finance/advance-payments/projects").json()["projects"]
        assert [row["project_id"] for row in bd_rows] == [own_project.id]

        selected = users["lidar"]
        pm_rows = client.get("/api/finance/advance-payments/projects").json()["projects"]
        assert [row["project_id"] for row in pm_rows] == [own_project.id]
        assert pm_rows[0]["financial_amounts_visible"] is False
        assert pm_rows[0]["advance_amount"] is None
        pm_detail = client.get(f"/api/finance/advance-payments/{own_project.id}").json()
        assert pm_detail["transactions"] == []
        assert pm_detail["followups"] == []
        assert pm_detail["payment_terms"] is None

        selected = users["employee"]
        assert client.get("/api/finance/advance-payments/summary").status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
