"""Password change / forgot-password regressions with Employee Master identity intact."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("TOTP_ENCRYPTION_KEY", "password-regression-totp-secret-32-chars")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.modules.employee_portal.employee_master import (  # noqa: E402
    ACTIVE_EMPLOYMENT,
    NOT_REGISTERED,
)
from app.modules.employee_portal.models import EmployeeMaster  # noqa: E402

pytestmark = pytest.mark.usefixtures("isolated_application_database")

EMAIL = "pwd.regression@nakshatech.com"
OLD_PASSWORD = "OldPassword@2026"
NEW_PASSWORD = "NewPassword@2026"


def _setup_user_with_master() -> None:
    with SessionLocal() as db:
        from app.core.security import hash_password

        user = User(
            email=EMAIL,
            full_name="Pwd Regression",
            password_hash=hash_password(OLD_PASSWORD),
            role="employee",
            branch="Head Office",
            employee_id="4001",
            department="Laser Scanning",
            designation="Survey Engineer",
            phone_number="9000000002",
            email_verified=True,
            account_status="active",
            is_active=True,
        )
        db.add(user)
        db.flush()
        from app.modules.employee_portal.models import AuthenticatorCredential

        db.add(
            AuthenticatorCredential(
                user_id=user.id,
                encrypted_secret="dGVzdC1lbmNyeXB0ZWQtc2VjcmV0",
                is_confirmed=True,
            )
        )
        db.add(
            EmployeeMaster(
                source_sl_no="SL-1",
                access_card_no="NT4001",
                access_card_no_normalized="nt4001",
                employee_number="4001",
                employee_number_normalized="4001",
                employee_name="Pwd Regression",
                phone="9000000002",
                phone_normalized="9000000002",
                department_raw="Laser Scanning",
                department_code="laser_scanning",
                designation_raw="Survey Engineer",
                email=EMAIL,
                email_normalized=EMAIL,
                employment_status=ACTIVE_EMPLOYMENT,
                crm_account_status="active",
                linked_user_id=user.id,
                source_batch_id="pwd-regression",
            )
        )
        db.commit()


def _login(password: str) -> dict:
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"role": "employee", "email": EMAIL, "password": password})
        assert response.status_code == 200, response.text
        return response.json()


def test_change_password_old_fails_new_succeeds_and_master_intact() -> None:
    _setup_user_with_master()
    session = _login(OLD_PASSWORD)
    token = session["access_token"]
    with TestClient(app) as client:
        changed = client.post(
            "/api/auth/change-password",
            json={"current_password": OLD_PASSWORD, "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert changed.status_code == 200, changed.text
    # Old password fails.
    with TestClient(app) as client:
        old_login = client.post("/api/auth/login", json={"role": "employee", "email": EMAIL, "password": OLD_PASSWORD})
        assert old_login.status_code == 401
    # New password succeeds.
    session = _login(NEW_PASSWORD)
    assert session["user"]["email"] == EMAIL
    # Employee Master link, role, department and TOTP remain intact.
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        assert user is not None
        assert user.role == "employee"
        assert user.department == "Laser Scanning"
        master = db.scalar(select(EmployeeMaster).where(EmployeeMaster.email_normalized == EMAIL))
        assert master is not None
        assert master.linked_user_id == user.id
        assert master.crm_account_status == "active"
        from app.modules.employee_portal.models import AuthenticatorCredential

        credential = db.scalar(select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id))
        assert credential is not None
        assert credential.is_confirmed is True


def test_forgot_password_old_fails_new_succeeds_and_identity_intact() -> None:
    _setup_user_with_master()
    with TestClient(app) as client:
        request = client.post("/api/auth/forgot-password/request-otp", json={"email": EMAIL})
        assert request.status_code == 200, request.text
        otp = request.json()["development_otp"]
        assert otp
        verify = client.post("/api/auth/forgot-password/verify-otp", json={"email": EMAIL, "otp": otp})
        assert verify.status_code == 200, verify.text
        reset = client.post(
            "/api/auth/forgot-password/reset",
            json={"reset_token": verify.json()["reset_token"], "new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert reset.status_code == 200, reset.text
    with TestClient(app) as client:
        old_login = client.post("/api/auth/login", json={"role": "employee", "email": EMAIL, "password": OLD_PASSWORD})
        assert old_login.status_code == 401
    session = _login(NEW_PASSWORD)
    assert session["user"]["email"] == EMAIL
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        assert user is not None
        assert user.role == "employee"
        assert user.employee_id == "4001"
        master = db.scalar(select(EmployeeMaster).where(EmployeeMaster.email_normalized == EMAIL))
        assert master is not None
        assert master.linked_user_id == user.id
        assert master.employee_number == "4001"
        assert master.access_card_no == "NT4001"


def test_master_linked_user_cannot_edit_identity_via_profile() -> None:
    _setup_user_with_master()
    session = _login(OLD_PASSWORD)
    token = session["access_token"]
    with TestClient(app) as client:
        response = client.patch(
            "/api/auth/profile",
            json={"full_name": "Tampered Name", "phone_number": "1111111111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403, response.text
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMAIL))
        assert user is not None
        assert user.full_name == "Pwd Regression"
        assert user.phone_number == "9000000002"
