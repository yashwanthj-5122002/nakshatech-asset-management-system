"""Employee Master self-registration: eligibility, duplicate protection, identity tamper-proofing."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("TOTP_ENCRYPTION_KEY", "employee-master-totp-secret-at-least-32-characters")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.modules.employee_portal.employee_master import (  # noqa: E402
    ACTIVE_EMPLOYMENT,
    NOT_REGISTERED,
    NEEDS_REVIEW,
)
from app.modules.employee_portal.models import Branch, EmployeeMaster  # noqa: E402
from app.modules.employee_portal.service import decrypt_totp_secret, totp_code  # noqa: E402

pytestmark = pytest.mark.usefixtures("isolated_application_database")

EMPLOYEE_EMAIL = "new.hire@nakshatech.com"
EMPLOYEE_PASSWORD = "NewHire@2026"


def _ensure_branch() -> None:
    with SessionLocal() as db:
        if db.get(Branch, 1) is None:
            db.add(Branch(id=1, code="HO", name="Head Office", is_active=True))
            db.commit()


def _make_master(**overrides) -> None:
    _ensure_branch()
    with SessionLocal() as db:
        master = EmployeeMaster(
            source_sl_no="1",
            access_card_no="NT9001",
            access_card_no_normalized="nt9001",
            employee_number="9001",
            employee_number_normalized="9001",
            employee_name="New Hire",
            phone="9000000001",
            phone_normalized="9000000001",
            department_raw="Laser Scanning",
            department_code="laser_scanning",
            designation_raw="Survey Engineer",
            email=EMPLOYEE_EMAIL,
            email_normalized=EMPLOYEE_EMAIL,
            employment_status=ACTIVE_EMPLOYMENT,
            crm_account_status=NOT_REGISTERED,
            source_batch_id="test-batch",
        )
        for key, value in overrides.items():
            setattr(master, key, value)
        db.add(master)
        db.commit()


def _authenticator_code(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        from app.modules.employee_portal.models import AuthenticatorCredential

        credential = db.scalar(
            select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id)
        )
        assert credential is not None
        return totp_code(decrypt_totp_secret(credential.encrypted_secret))


def _register(client: TestClient) -> dict:
    request = client.post("/api/auth/register/request-otp", json={"email": EMPLOYEE_EMAIL})
    assert request.status_code == 200, request.text
    otp = request.json()["development_otp"]
    assert otp
    verify = client.post("/api/auth/register/verify-otp", json={"email": EMPLOYEE_EMAIL, "otp": otp})
    assert verify.status_code == 200, verify.text
    payload = verify.json()
    assert payload["employee"]["employee_name"] == "New Hire"
    complete = client.post(
        "/api/auth/register/complete",
        json={
            "registration_token": payload["registration_token"],
            "branch_id": 1,
            "password": EMPLOYEE_PASSWORD,
            "confirm_password": EMPLOYEE_PASSWORD,
        },
    )
    assert complete.status_code == 200, complete.text
    confirm = client.post(
        "/api/auth/mfa/confirm",
        json={
            "mfa_setup_token": complete.json()["mfa_setup_token"],
            "code": _authenticator_code(EMPLOYEE_EMAIL),
        },
    )
    assert confirm.status_code == 200, confirm.text
    return confirm.json()


def test_eligible_employee_registers_with_master_identity() -> None:
    _make_master()
    with TestClient(app) as client:
        _register(client)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMPLOYEE_EMAIL))
        assert user is not None
        assert user.role == "employee"
        assert user.full_name == "New Hire"
        assert user.employee_id == "9001"
        assert user.department == "Laser Scanning"
        assert user.designation == "Survey Engineer"
        assert user.phone_number == "9000000001"
        master = db.scalar(select(EmployeeMaster).where(EmployeeMaster.email_normalized == EMPLOYEE_EMAIL))
        assert master is not None
        assert master.crm_account_status == "active"
        assert master.linked_user_id == user.id


def test_duplicate_account_is_rejected() -> None:
    _make_master()
    with TestClient(app) as client:
        _register(client)
        again = client.post("/api/auth/register/request-otp", json={"email": EMPLOYEE_EMAIL})
        assert again.status_code == 409


def test_ineligible_needs_review_employee_is_blocked() -> None:
    _make_master(crm_account_status=NEEDS_REVIEW, review_reason="External email is not eligible for automatic self-registration")
    with TestClient(app) as client:
        response = client.post("/api/auth/register/request-otp", json={"email": EMPLOYEE_EMAIL})
        assert response.status_code == 403
        assert "not eligible" in response.json()["detail"]


def test_unknown_email_is_blocked() -> None:
    with TestClient(app) as client:
        response = client.post("/api/auth/register/request-otp", json={"email": "nobody@nakshatech.com"})
        assert response.status_code == 403


def test_frontend_cannot_override_master_identity() -> None:
    """RegistrationCompleteRequest no longer carries identity fields; extra JSON keys are ignored."""
    _make_master()
    with TestClient(app) as client:
        request = client.post("/api/auth/register/request-otp", json={"email": EMPLOYEE_EMAIL})
        otp = request.json()["development_otp"]
        verify = client.post("/api/auth/register/verify-otp", json={"email": EMPLOYEE_EMAIL, "otp": otp})
        payload = verify.json()
        complete = client.post(
            "/api/auth/register/complete",
            json={
                "registration_token": payload["registration_token"],
                "branch_id": 1,
                "password": EMPLOYEE_PASSWORD,
                "confirm_password": EMPLOYEE_PASSWORD,
                "full_name": "Hacker Name",
                "employee_id": "0000",
                "department": "Finance",
                "designation": "CEO",
                "phone_number": "1111111111",
            },
        )
        assert complete.status_code == 200, complete.text
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == EMPLOYEE_EMAIL))
        assert user is not None
        assert user.full_name == "New Hire"
        assert user.employee_id == "9001"
        assert user.department == "Laser Scanning"
        assert user.designation == "Survey Engineer"
        assert user.phone_number == "9000000001"


def test_registration_otp_is_single_use() -> None:
    _make_master()
    with TestClient(app) as client:
        request = client.post("/api/auth/register/request-otp", json={"email": EMPLOYEE_EMAIL})
        otp = request.json()["development_otp"]
        first = client.post("/api/auth/register/verify-otp", json={"email": EMPLOYEE_EMAIL, "otp": otp})
        assert first.status_code == 200
        second = client.post("/api/auth/register/verify-otp", json={"email": EMPLOYEE_EMAIL, "otp": otp})
        assert second.status_code == 400
