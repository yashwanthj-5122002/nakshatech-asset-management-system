"""SEC-03: the role in force comes from the database row, never from the token.

A bearer token lives for hours. If its ``role`` claim were trusted, revoking or
downgrading an account in the database would not take effect until expiry, and
a stale (or forged-with-a-leaked-key) elevated claim would clear every
``require_roles`` gate. The claim is only meaningful as a downgrade to
``employee`` for Employee Support sign-ins.

Imports are deferred to inside the tests on purpose: importing the application
at module scope would freeze the settings singleton during collection, before
other test modules have applied their own ``SEED_*`` environment.
"""

from __future__ import annotations

from datetime import datetime


def _user(email: str, role: str):
    from app.models.entities import User

    return User(
        email=email,
        full_name="Role Fixture",
        password_hash="pytest-only-password-hash",
        role=role,
        branch="Head Office",
        is_active=True,
        token_version=0,
    )


def _auth(user, claims: dict) -> "object":
    from app.api.dependencies import CurrentAuth

    return CurrentAuth(user=user, claims=claims, session=None)


def test_elevated_role_claim_is_ignored():
    auth = _auth(_user("elevated@nakshatech.com", "employee"), {"role": "admin"})
    assert auth.effective_role == "employee"


def test_reduced_database_role_wins_over_stale_elevated_claim():
    auth = _auth(_user("downgraded@nakshatech.com", "employee"), {"role": "management"})
    assert auth.effective_role == "employee"


def test_employee_support_downgrade_is_honoured():
    # Employee Support signs in as a management user but deliberately mints a
    # token carrying role=employee; that downgrade must survive.
    auth = _auth(_user("support@nakshatech.com", "management"), {"role": "employee"})
    assert auth.effective_role == "employee"


def test_database_role_is_used_when_the_claim_is_absent():
    auth = _auth(_user("plain@nakshatech.com", "it"), {})
    assert auth.effective_role == "it"


def test_elevated_claim_cannot_pass_a_management_only_route():
    """End to end: an employee account carrying a management claim is refused."""
    from fastapi.testclient import TestClient

    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.main import app

    with SessionLocal() as db:
        user = _user("claim-elevation@nakshatech.com", "employee")
        db.add(user)
        db.commit()
        token = create_access_token(user.email, "management", token_version=int(user.token_version or 0))

    client = TestClient(app)
    month = datetime.now().strftime("%Y-%m")
    response = client.get(
        f"/api/it-activity/summary?month={month}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403, response.text

    # The same account still identifies itself correctly.
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200, me.text
    assert me.json()["role"] == "employee"
