from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import verify_password
from app.models.entities import User
from app.services.seed import ensure_operations_test_accounts


TEST_PASSWORD = "UnitTestOnly_2026!"


def _configure(monkeypatch):
    values = {
        "seed_operations_test_users_enabled": True,
        "seed_bd_manager_email": "bd@nakshatech.com",
        "seed_bd_manager_password": TEST_PASSWORD,
        "seed_ortho_pm_email": "ortho@nakshatech.com",
        "seed_ortho_pm_password": TEST_PASSWORD,
        "seed_employee_test_email": "employee1@nakshatech.com",
        "seed_employee_test_password": TEST_PASSWORD,
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def test_v707_creates_only_manager_manager_employee_test_logins(monkeypatch):
    _configure(monkeypatch)
    expected = {
        "bd@nakshatech.com": ("bd", "Manager", "TEST-BD-MGR"),
        "ortho@nakshatech.com": ("ortho", "Project Manager", "TEST-ORTHO-PM"),
        "employee1@nakshatech.com": ("employee", "Employee", "TEST-EMPLOYEE-001"),
    }

    with SessionLocal() as db:
        ensure_operations_test_accounts(db)
        for email, (role, designation, employee_id) in expected.items():
            user = db.scalar(select(User).where(func.lower(User.email) == email))
            assert user is not None
            assert user.role == role
            assert user.designation == designation
            assert user.employee_id == employee_id
            assert user.account_status == "active"
            assert user.is_active is True
            assert user.email_verified is True
            assert user.must_change_password is False
            assert user.mfa_required is False
            assert user.password_hash != TEST_PASSWORD
            assert verify_password(TEST_PASSWORD, user.password_hash)

        assert db.scalar(select(User).where(func.lower(User.email) == "ortho2@nakshatech.com")) is None
        assert db.scalar(select(User).where(func.lower(User.email) == "ortho3@nakshatech.com")) is None
        assert db.scalar(select(User).where(func.lower(User.email) == "ortho4@nakshatech.com")) is None
        assert db.scalar(select(User).where(func.lower(User.email) == "ortho5@nakshatech.com")) is None


def test_v707_test_logins_are_idempotent(monkeypatch):
    _configure(monkeypatch)
    with SessionLocal() as db:
        ensure_operations_test_accounts(db)
        first = {
            email: user_id
            for email, user_id in db.execute(
                select(User.email, User.id).where(User.employee_id.in_(["TEST-BD-MGR", "TEST-ORTHO-PM", "TEST-EMPLOYEE-001"]))
            ).all()
        }
        ensure_operations_test_accounts(db)
        second = {
            email: user_id
            for email, user_id in db.execute(
                select(User.email, User.id).where(User.employee_id.in_(["TEST-BD-MGR", "TEST-ORTHO-PM", "TEST-EMPLOYEE-001"]))
            ).all()
        }
        assert first == second
        assert len(second) == 3


def test_v707_operations_test_seed_is_rejected_in_production(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "seed_operations_test_users_enabled", True)
    # Reproduce the local/UAT condition from the failure log: JWT_SECRET can
    # also be development-strength. The test-account production guard must
    # still be the deterministic first failure.
    monkeypatch.setattr(settings, "jwt_secret", "short-local-dev-secret")
    try:
        settings.validate_production_settings()
    except RuntimeError as exc:
        assert "SEED_OPERATIONS_TEST_USERS_ENABLED" in str(exc)
    else:
        raise AssertionError("Production must reject enabled BD/Ortho/employee test seeding")
