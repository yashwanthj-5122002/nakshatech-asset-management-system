"""Phase 4: Advance Payment notifications and alerts.

Covers due/overdue/partial/high-value notification creation, duplicate
prevention through dedupe keys, and backend role filtering (Finance full,
Management high-value only, BD own projects, PM counts without amounts,
Production/QC/QA denied).
"""

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
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.advance_notification_service import (
    evaluate_advance_alerts,
    high_value_threshold,
    refresh_advance_notifications,
)
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import ProjectWorkflow


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
    advance_amount: Decimal = Decimal("100000.00"),
    expected_date: date | None = None,
    final_date: date | None = None,
) -> FinanceProject:
    today = date.today()
    client = FinanceClient(
        client_code=f"ADV4-C-{suffix}",
        client_name=f"Phase4 Client {suffix}",
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
        project_code=f"ADV4-P-{suffix}",
        project_name=f"Phase4 Project {suffix}",
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
    db.add(ProjectCommercialEstimateRevision(
        project_id=project.id,
        revision_no=1,
        is_baseline=True,
        status="APPROVED",
        is_locked=True,
        scope_description="Phase 4 notification scope",
        billing_type="fixed_price",
        payment_terms="Advance before mobilization",
        currency_code="INR",
        estimated_amount=Decimal("500000.00"),
        taxable_base_amount=Decimal("500000.00"),
        tax_percent=Decimal("0"),
        expected_tax=Decimal("0"),
        expected_gross=Decimal("500000.00"),
        advance_required=True,
        advance_payment_type="fixed_advance",
        advance_amount=advance_amount,
        advance_currency_code="INR",
        expected_advance_date=expected_date if expected_date is not None else today + timedelta(days=5),
        final_advance_date=final_date if final_date is not None else today + timedelta(days=10),
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


def _titles(db, user: User) -> list[str]:
    rows = db.scalars(
        select(GlobalNotification.title).where(GlobalNotification.recipient_user_id == user.id)
    ).all()
    return sorted(rows)


def test_due_notification_created_for_finance():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.due@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.adv4.due@nakshatech.com", "bd", "BD Owner")
        project = _project(
            db,
            suffix="DUE",
            bd=bd,
            expected_date=today,
            final_date=today + timedelta(days=7),
        )
        db.commit()
        project_id, project_name = project.id, project.project_name

        result = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert result["matched"]["due"] >= 1
        assert result["created"] >= 1

        note = db.scalar(select(GlobalNotification).where(
            GlobalNotification.dedupe_key == f"advance_due_project_{project_id}_{today.isoformat()}"
        ))
        assert note is not None
        assert note.title == "Advance Payment Due"
        assert note.event_type == "finance.advance_payment.due"
        assert project_name in note.message
        assert "Phase4 Client DUE" in note.message
        assert today.strftime("%d-%m-%Y") in note.message
        assert note.recipient_role == "finance"
        db.commit()


def test_overdue_notification_created_with_days_overdue():
    today = date.today()
    final_date = today - timedelta(days=3)
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.overdue@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.adv4.overdue@nakshatech.com", "bd", "BD Owner")
        project = _project(
            db,
            suffix="OVERDUE",
            bd=bd,
            expected_date=today - timedelta(days=6),
            final_date=final_date,
        )
        db.commit()
        project_id = project.id

        result = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert result["matched"]["overdue"] >= 1

        note = db.scalar(select(GlobalNotification).where(
            GlobalNotification.dedupe_key == f"advance_overdue_project_{project_id}_{today.isoformat()}"
        ))
        assert note is not None
        assert note.title == "Advance Payment Overdue"
        assert "overdue by 3 day(s)" in note.message
        assert "1,00,000" in note.message  # Indian grouping for pending amount
        db.commit()


def test_partial_advance_pending_notification():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.partial@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.adv4.partial@nakshatech.com", "bd", "BD Owner")
        project = _project(
            db,
            suffix="PARTIAL",
            bd=bd,
            expected_date=today + timedelta(days=5),
            final_date=today + timedelta(days=10),
        )
        db.add(ClientAdvanceTransaction(
            project_id=project.id,
            client_id=project.client_id,
            sequence=1,
            amount=Decimal("40000.00"),
            currency="INR",
            amount_inr=Decimal("40000.00"),
            fx_rate=Decimal("1"),
            payment_date=today,
            payment_mode="bank_transfer",
            recorded_by_id=finance.id,
        ))
        db.commit()
        project_id = project.id

        result = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert result["matched"]["partial"] >= 1

        note = db.scalar(select(GlobalNotification).where(
            GlobalNotification.dedupe_key == f"advance_partial_project_{project_id}_{today.isoformat()}"
        ))
        assert note is not None
        assert note.title == "Partial Advance Pending"
        assert "40,000" in note.message  # received
        assert "60,000" in note.message  # pending
        assert note.recipient_role == "finance"
        db.commit()


def test_duplicate_refresh_is_idempotent_same_day():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.dedupe@nakshatech.com", "finance", "Finance")
        bd = _user(db, "bd.adv4.dedupe@nakshatech.com", "bd", "BD Owner")
        project = _project(
            db,
            suffix="DEDUPE",
            bd=bd,
            expected_date=today,
            final_date=today + timedelta(days=7),
        )
        db.commit()
        project_id = project.id

        first = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert first["created"] >= 1

        def _count() -> int:
            return db.scalar(
                select(GlobalNotification.id).where(
                    GlobalNotification.dedupe_key
                    == f"advance_due_project_{project_id}_{today.isoformat()}"
                )
            ) is not None

        assert _count() is True

        second = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert second["matched"]["due"] == first["matched"]["due"]
        assert second["created"] == 0, "Same-day refresh must not duplicate notifications"
        db.commit()


def test_high_value_notification_goes_to_management_only():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.hv@nakshatech.com", "finance", "Finance")
        management = _user(db, "management.adv4.hv@nakshatech.com", "management", "Management")
        bd = _user(db, "bd.adv4.hv@nakshatech.com", "bd", "BD Owner")
        # Pending advance of Rs.15,00,000 exceeds the default Rs.10,00,000 threshold.
        project = _project(
            db,
            suffix="HIGHVALUE",
            bd=bd,
            advance_amount=Decimal("1500000.00"),
            expected_date=today + timedelta(days=5),
            final_date=today + timedelta(days=10),
        )
        db.commit()
        project_id = project.id

        assert high_value_threshold() == Decimal("1000000")

        result = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert result["matched"]["high_value"] == 1

        note = db.scalar(select(GlobalNotification).where(
            GlobalNotification.dedupe_key
            == f"advance_high_value_project_{project_id}_{today.isoformat()}"
        ))
        assert note is not None
        assert note.title == "High Value Pending Advance"
        assert note.recipient_role == "management"
        assert "15,00,000" in note.message
        assert "10,00,000" in note.message  # threshold shown

        # Management receives it; Finance does not.
        assert "High Value Pending Advance" in _titles(db, management)
        assert "High Value Pending Advance" not in _titles(db, finance)
        db.commit()


def test_role_filtering_bd_pm_and_production():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.roles@nakshatech.com", "finance", "Finance")
        bd_own = _user(db, "bd.own.adv4@nakshatech.com", "bd", "BD Own")
        bd_other = _user(db, "bd.other.adv4@nakshatech.com", "bd", "BD Other")
        pm = _user(db, "pm.adv4@nakshatech.com", "lidar", "LiDAR PM")
        production = _user(db, "production.adv4@nakshatech.com", "employee", "Production")
        qc = _user(db, "qc.adv4@nakshatech.com", "employee", "QC")

        own_project = _project(db, suffix="OWN", bd=bd_own, expected_date=today)
        other_project = _project(db, suffix="OTHER", bd=bd_other, expected_date=today)
        db.add(FinanceProjectMasterProfile(
            project_id=own_project.id,
            project_status="active",
            project_manager_id=pm.id,
            created_by_id=bd_own.id,
            updated_by_id=bd_own.id,
        ))
        db.commit()
        own_id, other_id = own_project.id, other_project.id

        # BD: only own project alerts are evaluated (backend-scoped).
        bd_result = refresh_advance_notifications(db, user=bd_own, effective_role="bd")
        assert bd_result["evaluated_projects"] == 1
        assert bd_result["matched"]["due"] == 1
        assert db.scalar(select(GlobalNotification.id).where(
            GlobalNotification.dedupe_key == f"advance_due_project_{own_id}_{today.isoformat()}"
        )) is not None
        assert db.scalar(select(GlobalNotification.id).where(
            GlobalNotification.dedupe_key == f"advance_due_project_{other_id}_{today.isoformat()}"
        )) is None, "BD must not raise alerts for projects owned by another BD"

        # Finance: full visibility across every project.
        finance_result = refresh_advance_notifications(db, user=finance, effective_role="finance")
        assert finance_result["evaluated_projects"] == 2
        assert finance_result["financial_amounts_visible"] is True
        assert finance_result["matched"]["due"] == 2
        # own_id was already materialised during the BD refresh (recipient is the
        # Finance role either way), so only other_id's notification is new.
        assert finance_result["created"] == 1
        assert db.scalar(select(GlobalNotification.id).where(
            GlobalNotification.dedupe_key == f"advance_due_project_{other_id}_{today.isoformat()}"
        )) is not None

        # PM: assigned project only, counts returned but amounts never exposed.
        pm_result = refresh_advance_notifications(db, user=pm, effective_role="lidar")
        assert pm_result["evaluated_projects"] == 1
        assert pm_result["financial_amounts_visible"] is False
        assert "pending_amount" not in pm_result
        assert isinstance(pm_result["created"], int)

        # Production/QC/QA: no access at all.
        for denied in (production, qc):
            try:
                refresh_advance_notifications(db, user=denied, effective_role="employee")
            except PermissionError:
                pass
            else:
                raise AssertionError("Production/QC/QA must be denied advance notification refresh")
        db.commit()


def test_evaluate_alerts_rules_are_pure_and_status_aware():
    today = date.today()
    threshold = Decimal("1000000")
    base = {
        "project_id": 1,
        "project_name": "GIS4456",
        "client": "ABC",
        "status": "pending",
        "status_label": "Pending",
        "advance_amount": Decimal("500000"),
        "received_amount": Decimal("0"),
        "pending_amount": Decimal("500000"),
        "expected_date": today.isoformat(),
        "final_date": (today + timedelta(days=5)).isoformat(),
    }

    due = evaluate_advance_alerts([base], as_of=today, threshold=threshold)
    assert [alert["kind"] for alert in due] == ["due"]

    overdue_row = {
        **base,
        # Realistic derived status once today > final_advance_date.
        "status": "overdue",
        "status_label": "Overdue",
        "expected_date": (today - timedelta(days=4)).isoformat(),
        "final_date": (today - timedelta(days=2)).isoformat(),
    }
    overdue = evaluate_advance_alerts([overdue_row], as_of=today, threshold=threshold)
    assert set(alert["kind"] for alert in overdue) == {"overdue"}
    assert overdue[0]["days_overdue"] == 2

    partial_row = {
        **base,
        "status": "partial_received",
        "status_label": "Partial Received",
        "received_amount": Decimal("200000"),
        "pending_amount": Decimal("300000"),
        "expected_date": (today + timedelta(days=5)).isoformat(),
    }
    partial = evaluate_advance_alerts([partial_row], as_of=today, threshold=threshold)
    assert [alert["kind"] for alert in partial] == ["partial"]

    high_value_row = {
        **base,
        "advance_amount": Decimal("1200000"),
        "pending_amount": Decimal("1200000"),
        "expected_date": (today + timedelta(days=5)).isoformat(),
    }
    high_value = evaluate_advance_alerts([high_value_row], as_of=today, threshold=threshold)
    assert [alert["kind"] for alert in high_value] == ["high_value"]

    # Terminal statuses never raise money-pending alerts.
    for status in ("not_required", "received", "adjusted", "closed"):
        assert evaluate_advance_alerts(
            [{**base, "status": status, "received_amount": Decimal("100000"),
              "pending_amount": Decimal("400000")}],
            as_of=today,
            threshold=threshold,
        ) == []



def test_refresh_notifications_api_enforces_permissions():
    today = date.today()
    with SessionLocal() as db:
        finance = _user(db, "finance.adv4.api@nakshatech.com", "finance", "Finance")
        management = _user(db, "management.adv4.api@nakshatech.com", "management", "Management")
        production = _user(db, "production.adv4.api@nakshatech.com", "employee", "Production")
        bd = _user(db, "bd.adv4.api@nakshatech.com", "bd", "BD Owner")
        _project(db, suffix="API", bd=bd, expected_date=today, final_date=today + timedelta(days=7))
        db.commit()
        users = {"finance": finance, "management": management, "production": production}

    selected = users["finance"]

    def auth_override():
        return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    client = TestClient(app)
    try:
        response = client.post("/api/finance/advance-payments/refresh-notifications")
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["created"] >= 1
        assert payload["matched"]["due"] >= 1
        assert payload["high_value_threshold_inr"] == 1000000.0
        assert set(payload["matched"]) == {"due", "overdue", "partial", "high_value"}
        # Counts only: the endpoint body never carries project amounts.
        assert "pending_amount" not in payload

        # Second call the same day is idempotent.
        again = client.post("/api/finance/advance-payments/refresh-notifications")
        assert again.status_code == 200
        assert again.json()["created"] == 0

        # Management may refresh (high-value alerts route to Management recipients).
        selected = users["management"]
        management_response = client.post("/api/finance/advance-payments/refresh-notifications")
        assert management_response.status_code == 200

        # Production/QC/QA are denied backend side.
        selected = users["production"]
        denied = client.post("/api/finance/advance-payments/refresh-notifications")
        assert denied.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_auth, None)

