"""Organisation Policies acknowledgement persistence and status synchronisation.

Isolated in-memory SQLite only. These tests pin the database down as the single
source of truth for acknowledgement state:

* an acknowledgement is stored once per (employee, published version) and stays
  there across sessions / restarts,
* repeated submissions are idempotent and never create duplicate rows,
* the library payload reports the stored acknowledgement for EVERY employee
  role the module serves (employee + bd_employee) so Pending / Acknowledged
  filters, progress counts and the HR compliance dashboard stay in sync,
* a new published version requires a fresh acknowledgement while every older
  acknowledgement record is retained,
* reminder generation stops once the current version is acknowledged.
"""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from datetime import timedelta

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-only-change-me-32-characters")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import Base, get_db
from app.models.entities import User, utc_now
from app.modules.notifications.models import GlobalNotification
from app.modules.organisation_policies import router as policy_router
from app.modules.organisation_policies.router import (
    Ack,
    OrganisationPolicySettings,
    OrganisationPolicyReminderState,
    router,
)


BASE = "/api/organisation-policies"

ROLE_BY_KEY = {
    "hr": "hr",
    "employee": "employee",
    "bd": "bd_employee",
    "finance": "finance",
    "admin": "admin",
    "management": "management",
}

# Roles that must never reach the module (their ERP workflows are unrelated).
OUTSIDE_ROLES = ("finance", "admin", "management")


def _build_context():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    with testing_session() as db:
        users = {}
        for key, role in ROLE_BY_KEY.items():
            user = User(
                email=f"{key}@example.test",
                full_name=f"{key.title()} Person",
                password_hash="unused",
                role=role,
                employee_id=f"NT-{key.upper()}",
                department="Operations",
                is_active=True,
            )
            db.add(user)
            db.flush()
            users[key] = user.id
        db.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api")

    def override_db() -> Generator[Session, None, None]:
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db

    identity = {"id": users["employee"], "role": "employee"}

    def override_auth() -> CurrentAuth:
        with testing_session() as db:
            user = db.get(User, identity["id"])
            assert user is not None
            db.expunge(user)
        return CurrentAuth(user=user, claims={"role": identity["role"]}, session=None)

    app.dependency_overrides[get_current_auth] = override_auth

    # run_policy_reminders() opens its own session through SessionLocal; point
    # the module at the isolated test database for the duration of the test.
    original_session_local = policy_router.SessionLocal
    policy_router.SessionLocal = testing_session
    return app, testing_session, users, identity, original_session_local


def _restore(original_session_local):
    policy_router.SessionLocal = original_session_local


def _as(identity, users, key):
    identity.update(id=users[key], role=ROLE_BY_KEY[key])


def _publish_policy(client, identity, users, title="Workplace Discipline Policy"):
    _as(identity, users, "hr")
    created = client.post(
        BASE,
        data={
            "title": title,
            "category": "Workplace Discipline",
            "content": "Official policy text v1.",
            "effective_date": "",
            "revision_notes": "",
            "remove_pdf": "false",
        },
    )
    assert created.status_code == 201, created.text
    policy = created.json()

    published = client.post(
        f"{BASE}/{policy['id']}/publish",
        json={
            "version_id": policy["draft"]["id"],
            "revision": policy["draft"]["revision"],
        },
    )
    assert published.status_code == 200, published.text
    return policy["id"], published.json()["published"]["id"]


def _ack(client, policy_id, version_id, confirmed=True):
    return client.post(
        f"{BASE}/{policy_id}/acknowledge",
        json={"version_id": version_id, "confirmed": confirmed},
    )


def _ack_rows(session_factory, user_id, version_id=None):
    with session_factory() as db:
        query = select(Ack).where(Ack.user_id == user_id)
        if version_id is not None:
            query = query.where(Ack.version_id == version_id)
        return db.scalars(query).all()


def _library(client, key, users, identity):
    _as(identity, users, key)
    response = client.get(BASE)
    assert response.status_code == 200, response.text
    return response.json()


def _entry(library, policy_id):
    return next(p for p in library["policies"] if p["id"] == policy_id)


def _revise_and_publish(client, identity, users, policy_id, version_id):
    _as(identity, users, "hr")
    edited = client.patch(
        f"{BASE}/{policy_id}/draft",
        data={
            "title": "Workplace Discipline Policy",
            "category": "Workplace Discipline",
            "content": "Official policy text v2.",
            "effective_date": "",
            "revision_notes": "Updated",
            "remove_pdf": "false",
            "expected_version_id": str(version_id),
            "expected_revision": "1",
        },
    )
    assert edited.status_code == 200, edited.text
    draft = edited.json()["draft"]

    published = client.post(
        f"{BASE}/{policy_id}/publish",
        json={"version_id": draft["id"], "revision": draft["revision"]},
    )
    assert published.status_code == 200, published.text
    return published.json()["published"]["id"]


def _age_reminder_clock(session_factory, hours=48):
    with session_factory() as db:
        db.execute(
            update(OrganisationPolicyReminderState).values(
                last_sent_at=utc_now() - timedelta(hours=hours)
            )
        )
        db.commit()


def test_employee_acknowledgement_persists_and_is_idempotent():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)

            library = _library(client, "employee", users, identity)
            assert _entry(library, policy_id)["acknowledged_at"] is None

            first = _ack(client, policy_id, version_id)
            assert first.status_code == 200, first.text
            assert first.json()["acknowledged_at"]

            # Repeated submission stays idempotent: same payload, no new row.
            for _ in range(3):
                again = _ack(client, policy_id, version_id)
                assert again.status_code == 200, again.text

            assert len(_ack_rows(session_factory, users["employee"])) == 1

            # Status is read back from the database, not from client state.
            library = _library(client, "employee", users, identity)
            assert _entry(library, policy_id)["acknowledged_at"] is not None

            history = client.get(f"{BASE}/my-acknowledgements")
            assert history.status_code == 200
            assert len(history.json()["records"]) == 1
    finally:
        _restore(restore)


def test_bd_employee_acknowledgement_status_is_reported():
    """Regression: bd_employee acknowledgements were stored but never reported."""
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)

            library = _library(client, "bd", users, identity)
            assert _entry(library, policy_id)["acknowledged_at"] is None

            response = _ack(client, policy_id, version_id)
            assert response.status_code == 200, response.text
            assert len(_ack_rows(session_factory, users["bd"])) == 1

            library = _library(client, "bd", users, identity)
            entry = _entry(library, policy_id)
            assert entry["acknowledged_at"] is not None, (
                "A stored acknowledgement must be reported so the policy moves "
                "from Pending Acknowledgement to Acknowledged."
            )

            # The published-only employee view must also apply to bd_employee.
            assert entry["published"] is not None
            assert all(p["published"] for p in library["policies"])

            history = client.get(f"{BASE}/my-acknowledgements")
            assert history.status_code == 200
            assert len(history.json()["records"]) == 1
    finally:
        _restore(restore)


def test_fresh_acknowledgement_required_only_for_new_version():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_one = _publish_policy(client, identity, users)
            _as(identity, users, "employee")
            assert _ack(client, policy_id, version_one).status_code == 200

            version_two = _revise_and_publish(
                client, identity, users, policy_id, version_one
            )
            assert version_two != version_one

            for key in ("employee", "bd"):
                library = _library(client, key, users, identity)
                assert _entry(library, policy_id)["acknowledged_at"] is None, (
                    "A newly published version must require fresh acknowledgement."
                )
                assert _ack(client, policy_id, version_two).status_code == 200

            # The superseded acknowledgement row is never deleted.
            assert len(_ack_rows(session_factory, users["employee"], version_one)) == 1
            assert len(_ack_rows(session_factory, users["employee"], version_two)) == 1
            assert len(_ack_rows(session_factory, users["employee"])) == 2

            _as(identity, users, "employee")
            history = client.get(f"{BASE}/my-acknowledgements")
            assert len(history.json()["records"]) == 2
    finally:
        _restore(restore)


def test_hr_compliance_dashboard_matches_stored_acknowledgements():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)
            _as(identity, users, "employee")
            assert _ack(client, policy_id, version_id).status_code == 200

            _as(identity, users, "hr")
            compliance = client.get(f"{BASE}/compliance")
            assert compliance.status_code == 200
            rows = {
                (row["user_id"], row["policy_id"]): row
                for row in compliance.json()["rows"]
            }

            assert rows[(users["employee"], policy_id)]["acknowledged_at"]
            assert rows[(users["bd"], policy_id)]["acknowledged_at"] is None
            assert rows[(users["employee"], policy_id)]["pending_days"] == 0
            assert rows[(users["bd"], policy_id)]["employee_id"] == "NT-BD"
            assert rows[(users["employee"], policy_id)]["department"] == "Operations"

            export = client.get(f"{BASE}/compliance/export")
            assert export.status_code == 200
    finally:
        _restore(restore)


def test_reminders_stop_once_current_version_is_acknowledged():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)

            # Publishing arms the reminder clock; age it so a round can fire.
            _age_reminder_clock(session_factory)
            policy_router.run_policy_reminders()

            with session_factory() as db:
                first_round = db.scalars(
                    select(GlobalNotification).where(
                        GlobalNotification.is_reminder.is_(True),
                        GlobalNotification.is_read.is_(False),
                    )
                ).all()
            assert {n.recipient_user_id for n in first_round} == {
                users["employee"],
                users["bd"],
            }

            _as(identity, users, "employee")
            assert _ack(client, policy_id, version_id).status_code == 200
            _as(identity, users, "bd")
            assert _ack(client, policy_id, version_id).status_code == 200

            # Acknowledged employees leave the pending set, so the next run
            # retires their reminders instead of resending them.
            policy_router.run_policy_reminders()
            with session_factory() as db:
                remaining = db.scalars(
                    select(GlobalNotification).where(
                        GlobalNotification.is_reminder.is_(True),
                        GlobalNotification.is_read.is_(False),
                        GlobalNotification.recipient_user_id.in_(
                            [users["employee"], users["bd"]]
                        ),
                    )
                ).all()
            assert remaining == []

            # A newly published version re-arms reminders for both roles.
            version_two = _revise_and_publish(
                client, identity, users, policy_id, version_id
            )
            assert version_two != version_id

            with session_factory() as db:
                published_notice = db.scalars(
                    select(GlobalNotification).where(
                        GlobalNotification.event_type
                        == "organisation_policy.published",
                        GlobalNotification.is_read.is_(False),
                    )
                ).all()
            assert {n.recipient_user_id for n in published_notice} == {
                users["employee"],
                users["bd"],
            }

            # Reminder dedupe keys carry second granularity, so step past the
            # second in which the first reminder round was created.
            time.sleep(1.1)

            _age_reminder_clock(session_factory)
            policy_router.run_policy_reminders()
            with session_factory() as db:
                rearmed = db.scalars(
                    select(GlobalNotification).where(
                        GlobalNotification.is_reminder.is_(True),
                        GlobalNotification.is_read.is_(False),
                        GlobalNotification.recipient_user_id.in_(
                            [users["employee"], users["bd"]]
                        ),
                    )
                ).all()
            assert {n.recipient_user_id for n in rearmed} == {
                users["employee"],
                users["bd"],
            }
    finally:
        _restore(restore)


def test_outside_roles_are_denied_and_settings_require_hr():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)

            for key in OUTSIDE_ROLES:
                _as(identity, users, key)
                assert client.get(BASE).status_code == 403
                assert client.get(f"{BASE}/compliance").status_code == 403
                assert client.get(f"{BASE}/my-acknowledgements").status_code == 403
                assert _ack(client, policy_id, version_id).status_code == 403
                assert client.put(
                    f"{BASE}/settings", json={"reminder_hours": 12}
                ).status_code == 403

            # HR keeps full management of the module.
            _as(identity, users, "hr")
            assert client.get(f"{BASE}/compliance").status_code == 200
            assert client.put(
                f"{BASE}/settings", json={"reminder_hours": 12}
            ).status_code == 200
            with session_factory() as db:
                assert db.get(OrganisationPolicySettings, 1).reminder_hours == 12
    finally:
        _restore(restore)


def test_unconfirmed_or_stale_acknowledgement_is_rejected():
    app, session_factory, users, identity, restore = _build_context()
    try:
        with TestClient(app) as client:
            policy_id, version_id = _publish_policy(client, identity, users)
            _as(identity, users, "employee")

            rejected = _ack(client, policy_id, version_id, confirmed=False)
            assert rejected.status_code == 422
            assert _ack_rows(session_factory, users["employee"]) == []

            # Acknowledging a superseded or foreign version id is refused.
            assert _ack(client, policy_id, version_id + 999).status_code == 409
            assert _ack_rows(session_factory, users["employee"]) == []
    finally:
        _restore(restore)
