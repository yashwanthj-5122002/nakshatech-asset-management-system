"""Production initialization must preserve existing account credentials."""
from app.core.config import settings
from app.core.database import SessionLocal
from app.main import initialize_application
from app.models.entities import User


def test_production_startup_preserves_account_passwords_and_skips_seeders(monkeypatch):
    import app.main as main

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(type(settings), "validate_production_settings", lambda self: None)

    def unexpected_seed(*args, **kwargs):
        raise AssertionError("Production startup called a development seeder")

    for name in (
        "seed_database", "ensure_management_accounts", "ensure_operations_test_accounts",
        "ensure_v81_test_employee_accounts", "ensure_multi_department_pm_accounts",
        "ensure_multi_department_test_employee_accounts", "ensure_bd_employee_accounts",
        "ensure_finance_seed_data", "ensure_bundled_it_activity_reference_data",
    ):
        monkeypatch.setattr(main, name, unexpected_seed)

    with SessionLocal() as db:
        user = User(email="vinod@nakshatech.com", full_name="Existing Management",
                    password_hash="existing-private-hash", role="management", is_active=True)
        db.add(user)
        db.commit()
        user_id = user.id

    initialize_application()

    with SessionLocal() as db:
        assert db.get(User, user_id).password_hash == "existing-private-hash"
