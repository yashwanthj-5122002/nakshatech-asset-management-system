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
