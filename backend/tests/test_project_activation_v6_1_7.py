from __future__ import annotations

from types import SimpleNamespace

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance import service as finance_service
from app.modules.finance.models import FinanceProject
from app.modules.finance.service import project_expense_allowed, project_payload, set_project_status


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _pretend_production_engine(monkeypatch) -> None:
    fake_url = SimpleNamespace(get_backend_name=lambda: "postgresql")
    monkeypatch.setattr(finance_service, "engine", SimpleNamespace(url=fake_url))


def test_completed_and_on_hold_reason_survives_session_refresh():
    with SessionLocal() as db:
        finance = _user(db, "status.refresh.finance@nakshatech.com", "finance", "Status Refresh Finance")
        project = FinanceProject(
            project_code="STATUS-REFRESH-001",
            project_name="Lifecycle Refresh QA",
            client_name="Historical Client",
            is_active=False,
            created_by_id=finance.id,
        )
        db.add(project)
        db.flush()

        set_project_status(db, project=project, actor=finance, project_status="completed")
        db.commit()
        db.refresh(project)
        completed = project_payload(project)
        assert completed["project_status"] == "completed"
        assert completed["expense_allowed"] is False
        assert "completed" in (completed["expense_block_reason"] or "").lower()

        set_project_status(db, project=project, actor=finance, project_status="on_hold")
        db.commit()
        db.refresh(project)
        allowed, reason = project_expense_allowed(project)
        assert allowed is False
        assert "on hold" in (reason or "").lower()


def test_finance_activation_of_legacy_project_survives_production_startup_cleanup(monkeypatch):
    with SessionLocal() as db:
        finance = _user(db, "startup.finance@nakshatech.com", "finance", "Startup Finance")
        project = FinanceProject(
            project_code="PRJ-2026-005",
            project_name="International LiDAR Processing",
            client_name="Demo Overseas Client",
            is_active=False,
            created_by_id=finance.id,
        )
        db.add(project)
        db.flush()

        set_project_status(db, project=project, actor=finance, project_status="active")
        db.commit()
        db.refresh(project)
        assert project.is_active is True
        assert project_payload(project)["project_status"] == "active"
        assert project_payload(project)["expense_allowed"] is True

        _pretend_production_engine(monkeypatch)
        finance_service.ensure_finance_seed_data(db)
        db.expire_all()

        saved = db.get(FinanceProject, project.id)
        assert saved is not None
        data = project_payload(saved)
        assert data["project_status"] == "active"
        assert data["is_active"] is True
        assert data["expense_allowed"] is True


def test_unmanaged_legacy_demo_project_still_defaults_to_inactive_in_production(monkeypatch):
    with SessionLocal() as db:
        finance = _user(db, "cleanup.finance@nakshatech.com", "finance", "Cleanup Finance")
        project = FinanceProject(
            project_code="PRJ-2026-004",
            project_name="Legacy Demo Project",
            client_name="Legacy Demo Client",
            is_active=True,
            created_by_id=finance.id,
        )
        db.add(project)
        db.commit()

        _pretend_production_engine(monkeypatch)
        finance_service.ensure_finance_seed_data(db)
        db.expire_all()

        saved = db.get(FinanceProject, project.id)
        assert saved is not None
        assert saved.is_active is False
        assert project_payload(saved)["project_status"] == "inactive"
