"""New Joiner onboarding workflow: HR draft -> IT official email -> Management OR approval."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("TOTP_ENCRYPTION_KEY", "new-joiner-totp-secret-at-least-32-characters")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.modules.employee_portal import onboarding_service  # noqa: E402
from app.modules.employee_portal.models import (  # noqa: E402
    EmployeeMaster,
    EmployeeOnboardingRequest,
)
from app.modules.notifications.models import GlobalNotification  # noqa: E402

pytestmark = pytest.mark.usefixtures("isolated_application_database")

HR_EMAIL = "hr.onboarding@nakshatech.com"
IT_EMAIL = "it.onboarding@nakshatech.com"
CHETHAN_EMAIL = "chethan@nakshatech.com"
VINOD_EMAIL = "vinod@nakshatech.com"
OTHER_MANAGER_EMAIL = "other.manager@nakshatech.com"
JOINER_NAME = "Future Joiner"
JOINER_PERSONAL_EMAIL = "future.joiner@gmail.com"
JOINER_OFFICIAL_EMAIL = "future.joiner@nakshatech.com"


def _make_user(db, email: str, role: str) -> User:
    row = User(
        email=email,
        full_name=email.split("@", 1)[0],
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


def _draft_payload(**overrides):
    values = dict(
        employee_name=JOINER_NAME,
        personal_email=JOINER_PERSONAL_EMAIL,
        phone="9000000001",
        employee_number="3001",
        access_card_no="NT3001",
        department_code="laser_scanning",
        designation="Survey Engineer",
        joining_date=date(2026, 11, 1),
        notes="Joining after approval",
    )
    values.update(overrides)
    return values


def test_hr_creates_draft() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        db.flush()
        draft = onboarding_service.create_draft(db, hr, **_draft_payload())
        assert draft.status == "hr_draft"
        assert draft.created_by_user_id == hr.id
        assert draft.department_code == "laser_scanning"


def test_normal_employee_cannot_create_onboarding_request_http() -> None:
    with SessionLocal() as db:
        _make_user(db, "random.employee@nakshatech.com", "employee")
        db.commit()
    from app.core.security import create_access_token

    token = create_access_token("random.employee@nakshatech.com", "employee", token_version=0)
    with TestClient(app) as client:
        response = client.post(
            "/api/onboarding/requests",
            json=_draft_payload(joining_date=None),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


def test_full_hr_it_management_flow() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        it = _make_user(db, IT_EMAIL, "it")
        chethan = _make_user(db, CHETHAN_EMAIL, "management")
        vinod = _make_user(db, VINOD_EMAIL, "management")
        other_manager = _make_user(db, OTHER_MANAGER_EMAIL, "management")
        db.flush()

        draft = onboarding_service.create_draft(db, hr, **_draft_payload())
        request_id = draft.id

        # HR submits to IT.
        submitted = onboarding_service.submit_to_it(db, hr, request_id)
        assert submitted.status == "hr_submitted"
        assert submitted.submitted_to_it_at is not None

        # IT cannot approve before submission state check; IT approves with official email.
        approved = onboarding_service.it_approve(db, it, request_id, official_email=JOINER_OFFICIAL_EMAIL)
        assert approved.status == "management_pending"
        assert approved.official_email == JOINER_OFFICIAL_EMAIL
        assert approved.it_approved_by_user_id == it.id

        # Unauthorized management user cannot approve.
        with pytest.raises(Exception):
            onboarding_service.management_approve(db, other_manager, request_id)

        # Chethan's approval finalizes (OR approval — only one needed).
        finalized = onboarding_service.management_approve(db, chethan, request_id)
        assert finalized.status == "final_approved"
        assert finalized.decided_by == CHETHAN_EMAIL
        assert finalized.employee_master_id is not None

        # Second approval (Vinod) is idempotent and does not corrupt state.
        again = onboarding_service.management_approve(db, vinod, request_id)
        assert again.status == "final_approved"
        assert again.decided_by == CHETHAN_EMAIL
        assert again.employee_master_id == finalized.employee_master_id

        # Employee Master row created with the official email and department scope.
        master = db.get(EmployeeMaster, finalized.employee_master_id)
        assert master is not None
        assert master.email_normalized == JOINER_OFFICIAL_EMAIL
        assert master.employee_number == "3001"
        assert master.access_card_no == "NT3001"
        assert master.department_code == "laser_scanning"
        assert master.employment_status == "active"
        assert master.crm_account_status == "not_registered"

        # Notifications: HR + IT + management queue all received events.
        notifications = list(
            db.scalars(
                select(GlobalNotification).where(GlobalNotification.event_type.like("onboarding.%"))
            ).all()
        )
        recipients = {n.recipient_role for n in notifications if n.recipient_role}
        assert "it" in recipients
        assert "management" in recipients
        hr_notifications = [n for n in notifications if n.recipient_user_id == hr.id]
        assert hr_notifications


def test_vinod_approval_alone_finalizes() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        it = _make_user(db, IT_EMAIL, "it")
        vinod = _make_user(db, VINOD_EMAIL, "management")
        db.flush()
        draft = onboarding_service.create_draft(db, hr, **_draft_payload(employee_number="3009"))
        onboarding_service.submit_to_it(db, hr, draft.id)
        onboarding_service.it_approve(db, it, draft.id, official_email="vinod.joiner@nakshatech.com")
        finalized = onboarding_service.management_approve(db, vinod, draft.id)
        assert finalized.status == "final_approved"
        assert finalized.decided_by == VINOD_EMAIL


def test_final_approved_employee_can_register_but_pending_cannot() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        it = _make_user(db, IT_EMAIL, "it")
        chethan = _make_user(db, CHETHAN_EMAIL, "management")
        db.flush()
        draft = onboarding_service.create_draft(db, hr, **_draft_payload())
        onboarding_service.submit_to_it(db, hr, draft.id)
        onboarding_service.it_approve(db, it, draft.id, official_email=JOINER_OFFICIAL_EMAIL)
        db.commit()
    # Not yet finally approved: registration must be blocked.
    with TestClient(app) as client:
        blocked = client.post("/api/auth/register/request-otp", json={"email": JOINER_OFFICIAL_EMAIL})
        assert blocked.status_code == 403
    with SessionLocal() as db:
        draft_id = draft.id
        onboarding_service.management_approve(db, chethan, draft_id)
        db.commit()
    # Finally approved: registration OTP is now allowed.
    with TestClient(app) as client:
        allowed = client.post("/api/auth/register/request-otp", json={"email": JOINER_OFFICIAL_EMAIL})
        assert allowed.status_code == 200, allowed.text


def test_personal_email_notification_has_official_email_and_no_password() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        it = _make_user(db, IT_EMAIL, "it")
        chethan = _make_user(db, CHETHAN_EMAIL, "management")
        db.flush()
        draft = onboarding_service.create_draft(db, hr, **_draft_payload())
        onboarding_service.submit_to_it(db, hr, draft.id)
        onboarding_service.it_approve(db, it, draft.id, official_email=JOINER_OFFICIAL_EMAIL)

        sent: list[tuple[str, str, str]] = []
        original = onboarding_service.send_email
        onboarding_service.send_email = lambda **kwargs: sent.append((kwargs["recipient"], kwargs["subject"], kwargs["body"]))
        try:
            onboarding_service.management_approve(db, chethan, draft.id)
        finally:
            onboarding_service.send_email = original
        assert len(sent) == 1
        recipient, subject, body = sent[0]
        assert recipient == JOINER_PERSONAL_EMAIL
        assert JOINER_OFFICIAL_EMAIL in body
        assert "Create CRM Account" in body
        # No credential material is ever emailed.
        assert "Password:" not in body
        assert "OTP" not in body
        assert "TOTP" not in body


def test_rejection_flow() -> None:
    with SessionLocal() as db:
        hr = _make_user(db, HR_EMAIL, "hr")
        it = _make_user(db, IT_EMAIL, "it")
        db.flush()
        draft = onboarding_service.create_draft(db, hr, **_draft_payload())
        onboarding_service.submit_to_it(db, hr, draft.id)
        rejected = onboarding_service.reject_request(db, it, draft.id, reason="Incomplete documents")
        assert rejected.status == "rejected"
        assert rejected.rejected_reason == "Incomplete documents"
        # Rejected request cannot be approved afterwards.
        with pytest.raises(Exception):
            onboarding_service.it_approve(db, it, draft.id, official_email=JOINER_OFFICIAL_EMAIL)
