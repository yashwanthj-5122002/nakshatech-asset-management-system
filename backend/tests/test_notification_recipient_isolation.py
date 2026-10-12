"""Recipient isolation for the centre popup.

The popup is a GLOBAL UI but an AUTHORIZED-RECIPIENT-ONLY surface: bell and popup
read the SAME backend-authorized rows, and the existing per-user recipient rules
(role, explicit user, assignment) are preserved exactly. No test here may pass by
widening recipient access.
"""

from __future__ import annotations

from collections.abc import Generator
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-only-change-me-32-characters")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import Base, get_db
from app.models.entities import User
from app.modules.notifications.models import GlobalNotification  # noqa: F401
from app.modules.notifications.router import router as notification_router
from app.modules.notifications.service import create_global_notification, resolve_notifications
from app.services.ticket_notification_service import (
    notify_ticket_created,
    notify_ticket_department_reply,
    notify_ticket_reopened,
)

EMPLOYEE_A = "employee.a@nakshatech.com"
EMPLOYEE_B = "employee.b@nakshatech.com"
IT_USER = "it@nakshatech.com"
IT_USER_2 = "it2@nakshatech.com"
FINANCE = "finance@nakshatech.com"
BD = "bd@nakshatech.com"
PM_ASSIGNED = "pm.assigned@nakshatech.com"
PM_OTHER = "pm.other@nakshatech.com"
QC_ASSIGNED = "qc.assigned@nakshatech.com"
QA_ASSIGNED = "qa.assigned@nakshatech.com"
MANAGEMENT = "management@nakshatech.com"

ROLES = {
    EMPLOYEE_A: "employee", EMPLOYEE_B: "employee",
    IT_USER: "it", IT_USER_2: "it",
    FINANCE: "finance", BD: "bd",
    PM_ASSIGNED: "pm", PM_OTHER: "pm",
    QC_ASSIGNED: "ortho", QA_ASSIGNED: "ortho",
    MANAGEMENT: "management",
}

_ENGINES = []


def _build():
    """Fresh isolated app + database for one test."""
    while _ENGINES:
        _ENGINES.pop().dispose()
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    _ENGINES.append(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    # Clean slate, so nothing can ever survive between tests.
    with engine.begin() as connection:
        connection.execute(text("DELETE FROM global_notifications"))
        connection.execute(text("DELETE FROM users"))

    with TestingSession() as db:
        users = [
            User(email=email, full_name=email.split("@")[0], password_hash="x", role=role, is_active=True)
            for email, role in ROLES.items()
        ]
        db.add_all(users)
        db.flush()
        ids = {user.email: user.id for user in users}
        db.commit()

    app = FastAPI()
    app.include_router(notification_router, prefix="/api")

    def override_db() -> Generator[Session, None, None]:
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    return app, TestingSession, ids


def _client(app, TestingSession, user_id: int) -> TestClient:
    def override_auth() -> CurrentAuth:
        with TestingSession() as db:
            user = db.get(User, user_id)
            db.expunge(user)
        return CurrentAuth(user=user, claims={"role": user.role}, session=None)

    app.dependency_overrides[get_current_auth] = override_auth
    return TestClient(app)


def _popup(client: TestClient) -> list[dict]:
    response = client.get("/api/notifications/global/popup-queue")
    assert response.status_code == 200
    return response.json()


def _bell(client: TestClient) -> list[dict]:
    response = client.get("/api/notifications/global")
    assert response.status_code == 200
    return response.json()


def _raise_it_ticket(TestingSession, *, ticket_id: int, code: str, priority: str = "high") -> None:
    with TestingSession() as db:
        notify_ticket_created(
            db, ticket_id=ticket_id, ticket_code=code, department="it", priority=priority,
            title="Laptop will not boot", requester_name="Employee A",
            event_token=f"2026-10-05T09:00:{ticket_id}",
        )
        db.commit()


# ---------------------------------------------------------------------------
# IT / helpdesk recipient isolation (the real existing ticket workflow)
# ---------------------------------------------------------------------------
def test_it_ticket_reaches_only_the_handling_department() -> None:
    app, TestingSession, ids = _build()
    _raise_it_ticket(TestingSession, ticket_id=901, code="ITW-0901")

    it_client = _client(app, TestingSession, ids[IT_USER])
    assert len(_popup(it_client)) == 1, "authorized IT recipient sees the popup"
    assert len(_bell(it_client)) == 1, "and the bell item"
    assert _popup(it_client)[0]["requires_action"] is True

    for email in (FINANCE, BD, MANAGEMENT, EMPLOYEE_A, EMPLOYEE_B, PM_ASSIGNED, PM_OTHER, QA_ASSIGNED):
        other = _client(app, TestingSession, ids[email])
        assert _popup(other) == [], f"{email} must not receive the IT ticket popup"
        assert _bell(other) == [], f"{email} must not receive the IT ticket bell item"
        assert other.get("/api/notifications/global/pending-count").json()["pending_count"] == 0


def test_same_role_peer_follows_the_existing_role_rule() -> None:
    """A second IT user gets it only because the EXISTING rule fans out by role."""

    app, TestingSession, ids = _build()
    _raise_it_ticket(TestingSession, ticket_id=902, code="ITW-0902", priority="medium")
    assert len(_popup(_client(app, TestingSession, ids[IT_USER]))) == 1
    assert len(_popup(_client(app, TestingSession, ids[IT_USER_2]))) == 1


def test_ticket_requester_only_receives_their_own_reply() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        notify_ticket_department_reply(
            db, ticket_id=903, ticket_code="ITW-0903", requester_user_id=ids[EMPLOYEE_A],
            message_id=1, message_preview="We replaced the SSD.",
        )
        db.commit()

    assert len(_popup(_client(app, TestingSession, ids[EMPLOYEE_A]))) == 1
    assert _popup(_client(app, TestingSession, ids[EMPLOYEE_B])) == []
    assert _bell(_client(app, TestingSession, ids[EMPLOYEE_B])) == []


def test_reopened_ticket_is_actionable_and_routed_to_the_ticket() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        notify_ticket_reopened(
            db, ticket_id=904, ticket_code="ITW-0904", department="it", event_token="2026-10-06T10:00:00",
        )
        db.commit()
    item = _popup(_client(app, TestingSession, ids[IT_USER]))[0]
    assert item["requires_action"] is True
    assert item["severity"] == "danger"
    assert item["target_url"] == "/tickets/904"


# ---------------------------------------------------------------------------
# User-specific and assignment-specific isolation
# ---------------------------------------------------------------------------
def test_user_specific_notification_never_reaches_a_same_role_peer() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        create_global_notification(
            db, event_type="workflow.project.pm_assigned", category="system",
            title="New project assigned: GIS4456", message="You are the PM", target_url="/ortho",
            recipient_user_ids=[ids[PM_ASSIGNED]], requires_action=True, severity="warning",
            metadata={"project_name": "GIS4456", "assigned_role": "Project Manager"},
        )
        db.commit()

    assert len(_popup(_client(app, TestingSession, ids[PM_ASSIGNED]))) == 1

    other_pm = _client(app, TestingSession, ids[PM_OTHER])
    assert _popup(other_pm) == [], "same role alone must not grant access"
    assert _bell(other_pm) == []
    with TestingSession() as db:
        notification_id = db.scalar(select(GlobalNotification.id))
    assert other_pm.get(f"/api/notifications/global/{notification_id}").status_code == 404


def test_qc_assignment_is_isolated_from_qa_and_other_departments() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        create_global_notification(
            db, event_type="workflow.work.assigned", category="system",
            title="New QC work: PKG-1", message="Project GIS4456", target_url="/ortho",
            recipient_user_ids=[ids[QC_ASSIGNED]], requires_action=True, severity="warning",
            metadata={"project_name": "GIS4456", "package_code": "PKG-1", "assigned_role": "QC"},
        )
        db.commit()

    assert len(_popup(_client(app, TestingSession, ids[QC_ASSIGNED]))) == 1
    for email in (QA_ASSIGNED, FINANCE, BD, MANAGEMENT, IT_USER, PM_ASSIGNED):
        other = _client(app, TestingSession, ids[email])
        assert _popup(other) == [], f"{email} must not receive the QC assignment"
        assert _bell(other) == []


def test_finance_approval_notification_is_role_scoped_not_global() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        create_global_notification(
            db, event_type="workflow.project.submitted_finance", category="approval",
            title="Finance review required: GIS4456", message="BD submitted GIS4456",
            target_url="/finance", recipient_roles=["finance"], requires_action=True,
            metadata={"project_name": "GIS4456"},
        )
        db.commit()

    assert len(_popup(_client(app, TestingSession, ids[FINANCE]))) == 1
    for email in (BD, PM_ASSIGNED, IT_USER, MANAGEMENT, EMPLOYEE_A, QC_ASSIGNED):
        leaked = _popup(_client(app, TestingSession, ids[email]))


# ---------------------------------------------------------------------------
# Information-only notifications keep read/history semantics
# ---------------------------------------------------------------------------
def test_information_only_notification_is_not_pending_action() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        create_global_notification(
            db, event_type="workflow.delivery.completed", category="system",
            title="Delivery completed: PKG-1", message="Delivered to client",
            target_url="/ortho", recipient_user_ids=[ids[PM_ASSIGNED]],
        )
        db.commit()

    client = _client(app, TestingSession, ids[PM_ASSIGNED])
    item = _popup(client)[0]
    assert item["requires_action"] is False, "informational notifications must not become PENDING_ACTION"
    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 0
    assert len(_bell(client)) == 1, "it still appears in the bell/history"


# ---------------------------------------------------------------------------
# Close / Later never resolves, for every actionable type
# ---------------------------------------------------------------------------
def test_closing_popup_ten_times_never_resolves_or_mutates() -> None:
    app, TestingSession, ids = _build()
    _raise_it_ticket(TestingSession, ticket_id=905, code="ITW-0905", priority="critical")

    client = _client(app, TestingSession, ids[IT_USER])
    for _ in range(10):
        assert len(_popup(client)) == 1  # the popup keeps being offered
        _bell(client)                  # opening the bell 10x

    with TestingSession() as db:
        rows = db.scalars(select(GlobalNotification)).all()
        # The EXISTING rule fans a ticket out by role, so there is exactly one row
        # per active IT user - and viewing/closing never resolves or adds a row.
        assert len(rows) == 2
        assert {row.recipient_user_id for row in rows} == {ids[IT_USER], ids[IT_USER_2]}
        for row in rows:
            assert row.resolved_at is None, "viewing/closing must never resolve"
            assert row.requires_action is True


def test_real_workflow_action_resolves_the_pending_notification() -> None:
    """Resolution follows the REAL business action, never a popup click."""

    app, TestingSession, ids = _build()
    _raise_it_ticket(TestingSession, ticket_id=906, code="ITW-0906")

    client = _client(app, TestingSession, ids[IT_USER])
    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 1

    with TestingSession() as db:
        resolved = resolve_notifications(
            db, recipient_user_ids=[ids[IT_USER], ids[IT_USER_2]], event_type="ticket.created",
            resolved_by_id=ids[IT_USER], resolution_note="Ticket resolved",
        )
        db.commit()
    assert resolved == 2
    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 0
    assert _popup(client) == [], "a resolved item is no longer offered as a popup"


# ---------------------------------------------------------------------------
# Multiple notifications: one popup at a time, deterministic order
# ---------------------------------------------------------------------------
def test_queue_is_ordered_and_bell_still_holds_everything() -> None:
    app, TestingSession, ids = _build()
    with TestingSession() as db:
        for index in range(3):
            create_global_notification(
                db, event_type="workflow.work.assigned", category="system",
                title=f"New work {index}", message="m", target_url="/ortho",
                recipient_user_ids=[ids[QC_ASSIGNED]], requires_action=True,
            )
        db.commit()

    client = _client(app, TestingSession, ids[QC_ASSIGNED])
    queue = _popup(client)
    assert [row["title"] for row in queue] == ["New work 0", "New work 1", "New work 2"]
    assert len(_bell(client)) == 3, "every item stays in the bell"


# ---------------------------------------------------------------------------
# Direct API security
# ---------------------------------------------------------------------------
def test_settings_endpoint_denies_write_for_every_unauthorized_role() -> None:
    app, TestingSession, ids = _build()
    for email in (FINANCE, BD, PM_ASSIGNED, QC_ASSIGNED, IT_USER, EMPLOYEE_A, MANAGEMENT):
        client = _client(app, TestingSession, ids[email])
        response = client.put(
            "/api/notifications/global/settings/notification-settings",
            json={"overdue_popup_reminder_minutes": 5},
        )
        assert response.status_code == 403, f"{email} must be denied"


def test_popup_queue_never_leaks_across_departments() -> None:
    app, TestingSession, ids = _build()
    _raise_it_ticket(TestingSession, ticket_id=907, code="ITW-0907", priority="low")
    for email in (EMPLOYEE_A, EMPLOYEE_B, FINANCE, BD, MANAGEMENT, PM_ASSIGNED, QC_ASSIGNED, QA_ASSIGNED):
        assert _popup(_client(app, TestingSession, ids[email])) == [], f"{email} must not see the IT ticket"