from __future__ import annotations

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceProject
from app.modules.finance.service import project_payload, set_project_status


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="x",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_v6_1_5_finance_can_activate_legacy_unlinked_project():
    with SessionLocal() as db:
        finance = _user(db, "activation.finance@nakshatech.com", "finance", "Activation Finance")
        project = FinanceProject(
            project_code="ACT-LEGACY-001",
            project_name="Legacy Activation Project",
            client_name="Historical Client Name",
            client_id=None,
            is_active=False,
            created_by_id=finance.id,
        )
        db.add(project)
        db.flush()

        before = project_payload(project)
        assert before["project_status"] == "inactive"
        assert before["expense_allowed"] is False

        set_project_status(db, project=project, actor=finance, project_status="active")
        db.commit()
        db.refresh(project)

        active = project_payload(project)
        assert active["project_status"] == "active"
        assert active["is_active"] is True
        assert active["expense_allowed"] is True
        assert project.master_profile is not None

        set_project_status(db, project=project, actor=finance, project_status="completed")
        db.commit()
        db.refresh(project)

        completed = project_payload(project)
        assert completed["project_status"] == "completed"
        assert completed["is_active"] is False
        assert completed["expense_allowed"] is False
        assert "completed" in (completed["expense_block_reason"] or "").lower()


def test_v6_1_6_runtime_patch_route_activates_project():
    """Exercise the exact Batch-4 runtime route used by Docker, not app.routes."""
    from fastapi.testclient import TestClient

    from app.api.dependencies import CurrentAuth, get_current_auth
    from app.batch4_main import app

    with SessionLocal() as db:
        finance = _user(db, "activation.route.finance@nakshatech.com", "finance", "Activation Route Finance")
        project = FinanceProject(
            project_code="ACT-ROUTE-001",
            project_name="Runtime Route Activation Project",
            client_name="Runtime Historical Client",
            client_id=None,
            is_active=False,
            created_by_id=finance.id,
        )
        db.add(project)
        db.commit()
        db.refresh(finance)
        db.refresh(project)
        finance_id = finance.id
        project_id = project.id

    with SessionLocal() as db:
        finance = db.get(User, finance_id)
        assert finance is not None
        auth = CurrentAuth(user=finance, claims={"role": "finance"}, session=None)

        def _finance_auth_override():
            return auth

        app.dependency_overrides[get_current_auth] = _finance_auth_override
        client = TestClient(app)
        try:
            response = client.patch(
                f"/api/finance/projects/{project_id}/status",
                json={"project_status": "active"},
            )
        finally:
            client.close()
            app.dependency_overrides.pop(get_current_auth, None)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["project_code"] == "ACT-ROUTE-001"
    assert payload["project_status"] == "active"
    assert payload["is_active"] is True
    assert payload["expense_allowed"] is True

    with SessionLocal() as db:
        saved = db.get(FinanceProject, project_id)
        assert saved is not None
        assert saved.is_active is True
        assert saved.master_profile is not None
        assert saved.master_profile.project_status == "active"
