from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_privileged_auth_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "privileged-auth-test-secret-at-least-32-characters"
os.environ["TOTP_ENCRYPTION_KEY"] = "privileged-auth-totp-secret-at-least-32-characters"
os.environ["EMAIL_DELIVERY_MODE"] = "console"
os.environ["SEED_DEFAULT_USERS"] = "true"
os.environ["SEED_ADMIN_EMAIL"] = "admin@nakshatech.com"
os.environ["SEED_ADMIN_PASSWORD"] = "AdminRegression@2026"
os.environ["SEED_SOFTWARE_TEAM_EMAIL"] = "software.team@nakshatech.com"
os.environ["SEED_SOFTWARE_TEAM_PASSWORD"] = "SoftwareTemporary@2026"
os.environ["SEED_MANAGEMENT_EMAIL"] = "vinod@nakshatech.com"
os.environ["SEED_MANAGEMENT_PASSWORD"] = "VinodTemporary@2026"
os.environ["SEED_MANAGEMENT_SECONDARY_EMAIL"] = "chethan@nakshatech.com"
os.environ["SEED_MANAGEMENT_SECONDARY_PASSWORD"] = "ChethanTemporary@2026"
os.environ["SEED_IT_EMAIL"] = "it-support@nakshatech.com"
os.environ["SEED_IT_PASSWORD"] = "ITTemporary@2026"
os.environ["SEED_DRONE_EMAIL"] = "drone@nakshatech.com"
os.environ["SEED_DRONE_PASSWORD"] = "DroneRegression@2026"

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.modules.employee_portal.models import AuthenticatorCredential, Branch, SupportTicket  # noqa: E402
from app.modules.employee_portal.service import decrypt_totp_secret, totp_code  # noqa: E402
from app.services.seed import ensure_management_accounts  # noqa: E402


def _authenticator_code(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        credential = db.scalar(
            select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id)
        )
        assert credential is not None
        return totp_code(decrypt_totp_secret(credential.encrypted_secret))


def _activate_privileged_account(
    client: TestClient,
    *,
    role: str,
    email: str,
    temporary_password: str,
    permanent_password: str,
    completion_path: str = "/api/auth/privileged/complete-setup",
) -> dict:
    first_login = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": temporary_password},
    )
    assert first_login.status_code == 200, first_login.text
    first_payload = first_login.json()
    assert first_payload["mfa_setup_required"] is True
    assert first_payload["password_change_required"] is False
    assert first_payload["access_token"] is None
    assert first_payload["user"]["role"] == role

    confirm_mfa = client.post(
        "/api/auth/mfa/confirm",
        json={
            "mfa_setup_token": first_payload["mfa_setup_token"],
            "code": _authenticator_code(email),
        },
    )
    assert confirm_mfa.status_code == 200, confirm_mfa.text
    mfa_payload = confirm_mfa.json()
    assert mfa_payload["password_change_required"] is True
    assert mfa_payload["password_change_token"]
    assert mfa_payload["access_token"] is None

    complete = client.post(
        completion_path,
        json={
            "password_change_token": mfa_payload["password_change_token"],
            "new_password": permanent_password,
            "confirm_password": permanent_password,
        },
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["access_token"]
    assert complete.json()["user"]["email"] == email
    assert complete.json()["user"]["role"] == role

    old_temporary = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": temporary_password},
    )
    assert old_temporary.status_code == 401

    future_login = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": permanent_password},
    )
    assert future_login.status_code == 200, future_login.text
    assert future_login.json()["mfa_setup_required"] is False
    assert future_login.json()["password_change_required"] is False
    assert future_login.json()["access_token"]
    return future_login.json()


def test_privileged_authentication_admin_correction_and_management_ticket_oversight() -> None:
    with TestClient(app) as client:
        management_accounts = client.get("/api/auth/privileged/accounts?role=management")
        assert management_accounts.status_code == 200, management_accounts.text
        assert [item["email"] for item in management_accounts.json()["accounts"]] == [
            "vinod@nakshatech.com",
            "chethan@nakshatech.com",
        ]

        software_accounts = client.get("/api/auth/privileged/accounts?role=software_team")
        assert software_accounts.status_code == 200, software_accounts.text
        assert software_accounts.json()["accounts"] == [{
            "display_name": "Software Team",
            "full_name": "Software Team",
            "email": "software.team@nakshatech.com",
        }]

        it_accounts = client.get("/api/auth/privileged/accounts?role=it")
        assert it_accounts.status_code == 200, it_accounts.text
        assert it_accounts.json()["accounts"] == [{
            "display_name": "IT Support",
            "full_name": "IT Department",
            "email": "it-support@nakshatech.com",
        }]

        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.email == "admin@nakshatech.com"))
            software_user = db.scalar(select(User).where(User.email == "software.team@nakshatech.com"))
            it_user = db.scalar(select(User).where(User.email == "it-support@nakshatech.com"))
            assert admin is not None and software_user is not None and it_user is not None
            admin.role = "software_team"
            # Reproduce the legacy active department accounts shown in the login
            # screenshots. Without a confirmed Authenticator they must be moved
            # into the new temporary-password activation flow.
            for legacy_official, legacy_password in (
                (software_user, "OldSoftwarePassword@2026"),
                (it_user, "OldITPassword@2026"),
            ):
                legacy_official.password_hash = hash_password(legacy_password)
                legacy_official.account_status = "active"
                legacy_official.is_active = True
                legacy_official.must_change_password = False
                legacy_official.mfa_required = False
            db.add_all([
                User(
                    email="legacy-management@nakshatech.com",
                    full_name="Legacy Management",
                    password_hash=hash_password("LegacyManagement@2026"),
                    role="management",
                    branch="Head Office",
                    email_verified=True,
                    account_status="active",
                    is_active=True,
                ),
                User(
                    email="legacy-software@nakshatech.com",
                    full_name="Legacy Software",
                    password_hash=hash_password("LegacySoftware@2026"),
                    role="software_team",
                    branch="Head Office",
                    email_verified=True,
                    account_status="active",
                    is_active=True,
                ),
                User(
                    email="legacy-it@nakshatech.com",
                    full_name="Legacy IT",
                    password_hash=hash_password("LegacyIT@2026"),
                    role="it",
                    branch="Head Office",
                    email_verified=True,
                    account_status="active",
                    is_active=True,
                ),
            ])
            db.commit()
            ensure_management_accounts(db)

            corrected_admin = db.scalar(select(User).where(User.email == "admin@nakshatech.com"))
            corrected_software = db.scalar(select(User).where(User.email == "software.team@nakshatech.com"))
            corrected_it = db.scalar(select(User).where(User.email == "it-support@nakshatech.com"))
            assert corrected_admin is not None
            assert corrected_admin.role == "admin"
            for corrected in (corrected_software, corrected_it):
                assert corrected is not None
                assert corrected.account_status == "pending_mfa"
                assert corrected.is_active is False
                assert corrected.must_change_password is True
                assert corrected.mfa_required is True
            for email in (
                "legacy-management@nakshatech.com",
                "legacy-software@nakshatech.com",
                "legacy-it@nakshatech.com",
            ):
                legacy = db.scalar(select(User).where(User.email == email))
                assert legacy is not None
                assert legacy.is_active is False
                assert legacy.account_status == "disabled_privileged_access"

        admin_login = client.post(
            "/api/auth/login",
            json={
                "role": "admin",
                "email": "admin@nakshatech.com",
                "password": os.environ["SEED_ADMIN_PASSWORD"],
            },
        )
        assert admin_login.status_code == 200, admin_login.text
        assert admin_login.json()["user"]["role"] == "admin"

        unauthorized_software = client.post(
            "/api/auth/login",
            json={
                "role": "software_team",
                "email": "employee@nakshatech.com",
                "password": "EmployeePassword@2026",
            },
        )
        assert unauthorized_software.status_code == 403

        vinod = _activate_privileged_account(
            client,
            role="management",
            email="vinod@nakshatech.com",
            temporary_password=os.environ["SEED_MANAGEMENT_PASSWORD"],
            permanent_password="VinodPermanent@2026",
            completion_path="/api/auth/management/complete-setup",
        )
        chethan = _activate_privileged_account(
            client,
            role="management",
            email="chethan@nakshatech.com",
            temporary_password=os.environ["SEED_MANAGEMENT_SECONDARY_PASSWORD"],
            permanent_password="ChethanPermanent@2026",
        )
        software = _activate_privileged_account(
            client,
            role="software_team",
            email="software.team@nakshatech.com",
            temporary_password=os.environ["SEED_SOFTWARE_TEAM_PASSWORD"],
            permanent_password="SoftwarePermanent@2026",
        )
        it_support = _activate_privileged_account(
            client,
            role="it",
            email="it-support@nakshatech.com",
            temporary_password=os.environ["SEED_IT_PASSWORD"],
            permanent_password="ITPermanent@2026",
        )

        with SessionLocal() as db:
            branch = db.scalar(select(Branch).order_by(Branch.id))
            assert branch is not None
            employee = User(
                email="ticket.employee@nakshatech.com",
                full_name="Ticket Employee",
                password_hash=hash_password("EmployeePassword@2026"),
                role="employee",
                branch=branch.name,
                email_verified=True,
                account_status="active",
                is_active=True,
            )
            db.add(employee)
            db.flush()
            ticket = SupportTicket(
                ticket_code="IT-OVERSIGHT-001",
                requester_id=employee.id,
                branch_id=branch.id,
                department="it",
                title="Laptop network issue",
                description="The employee cannot connect to the office network.",
                priority="high",
                status="new",
            )
            db.add(ticket)
            db.commit()
            ticket_id = ticket.id

        vinod_headers = {"Authorization": f"Bearer {vinod['access_token']}"}
        chethan_headers = {"Authorization": f"Bearer {chethan['access_token']}"}
        software_headers = {"Authorization": f"Bearer {software['access_token']}"}
        it_headers = {"Authorization": f"Bearer {it_support['access_token']}"}
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

        page_view = client.post(
            "/api/audit/page-view",
            headers=it_headers,
            json={"path": "/it", "title": "IT Dashboard"},
        )
        assert page_view.status_code == 204, page_view.text

        for headers in (vinod_headers, chethan_headers, software_headers):
            user_activity = client.get("/api/software/users", headers=headers)
            assert user_activity.status_code == 200, user_activity.text
            user_emails = {item["email"] for item in user_activity.json()}
            assert {
                "vinod@nakshatech.com",
                "chethan@nakshatech.com",
                "software.team@nakshatech.com",
                "it-support@nakshatech.com",
            }.issubset(user_emails)

            audit_activity = client.get("/api/software/audit?limit=500", headers=headers)
            assert audit_activity.status_code == 200, audit_activity.text
            events = audit_activity.json()
            assert any(
                event["actor_email"] == "it-support@nakshatech.com"
                and event["event_type"] == "LOGIN_SUCCESS"
                for event in events
            )
            assert any(
                event["actor_email"] == "it-support@nakshatech.com"
                and event["event_type"] == "MODULE_VISITED"
                and event["module"] == "/it"
                for event in events
            )

        admin_audit = client.get("/api/software/audit", headers=admin_headers)
        assert admin_audit.status_code == 403

        with SessionLocal() as db:
            it_user_id = db.scalar(select(User.id).where(User.email == "it-support@nakshatech.com"))
            assert it_user_id is not None
        management_reset_attempt = client.post(
            f"/api/software/users/{it_user_id}/reset-authenticator",
            headers=vinod_headers,
        )
        assert management_reset_attempt.status_code == 403

        for headers in (vinod_headers, chethan_headers, software_headers):
            ticket_list = client.get("/api/tickets", headers=headers)
            assert ticket_list.status_code == 200, ticket_list.text
            visible = next(item for item in ticket_list.json() if item["id"] == ticket_id)
            assert visible["department"] == "it"
            assert visible["can_handle"] is False

            detail = client.get(f"/api/tickets/{ticket_id}", headers=headers)
            assert detail.status_code == 200, detail.text
            assert detail.json()["can_handle"] is False

        management_reply = client.post(
            f"/api/tickets/{ticket_id}/messages",
            headers=vinod_headers,
            json={"message": "Management must remain read-only."},
        )
        assert management_reply.status_code == 403

        management_update = client.patch(
            f"/api/tickets/{ticket_id}",
            headers=chethan_headers,
            json={"status": "resolved", "resolution": "Unauthorized Management update"},
        )
        assert management_update.status_code == 403

        it_resolve = client.patch(
            f"/api/tickets/{ticket_id}",
            headers=it_headers,
            json={"status": "resolved", "resolution": "Network adapter configuration corrected."},
        )
        assert it_resolve.status_code == 200, it_resolve.text
        assert it_resolve.json()["status"] == "resolved"
        assert it_resolve.json()["can_handle"] is True

        for headers in (vinod_headers, chethan_headers, software_headers):
            resolved = client.get(f"/api/tickets/{ticket_id}", headers=headers)
            assert resolved.status_code == 200, resolved.text
            assert resolved.json()["status"] == "resolved"
            assert resolved.json()["resolution"] == "Network adapter configuration corrected."
            assert resolved.json()["can_handle"] is False

        wrong_role = client.post(
            "/api/auth/login",
            json={
                "role": "employee",
                "email": "vinod@nakshatech.com",
                "password": "VinodPermanent@2026",
            },
        )
        assert wrong_role.status_code == 403

    TEST_DB.unlink(missing_ok=True)
