"""Notification popup experience: contracts and safety boundaries.

These tests cover the ADDITIVE layer only:

* persisted business notifications still come from ``create_global_notification``;
* the center-popup queue is a pure READ (closing a popup changes nothing);
* READ and RESOLVED stay independent;
* resolution only happens through a real workflow action, never from the popup;
* the reminder interval setting is gated on the manage_notification_settings
  capability, enforced on the BACKEND.

Nothing here creates, approves, rejects or settles any finance/project record.
"""

from __future__ import annotations

from collections.abc import Generator
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-only-change-me-32-characters")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import Base, get_db
from app.core.notification_access import can_manage_notification_settings
from app.models.entities import User, utc_now
from app.modules.notifications.models import GlobalNotification  # noqa: F401
from app.modules.notifications.router import router as notification_router
from app.modules.notifications.service import (
    create_global_notification,
    list_popup_notifications,
    pending_count_for_user,
    redact_notification_metadata,
    resolve_notifications,
    resolve_reminders,
)
from app.modules.notifications.settings_service import (
    DEFAULT_OVERDUE_REMINDER_MINUTES,
    get_overdue_reminder_minutes,
    notification_settings_payload,
    set_overdue_reminder_minutes,
)

FINANCE = "finance@nakshatech.com"
BD = "bd@nakshatech.com"
PM = "pm@nakshatech.com"
CHETHAN = "chethan@nakshatech.com"
VINOD = "vinod@nakshatech.com"
OTHER_MANAGER = "random.manager@nakshatech.com"


def _build():
    engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        users = {}
        for email, role in (
            (FINANCE, "finance"),
            (BD, "bd"),
            (PM, "pm"),
            (CHETHAN, "management"),
            (VINOD, "management"),
            (OTHER_MANAGER, "management"),
        ):
            user = User(email=email, full_name=email.split("@")[0], password_hash="x", role=role, is_active=True)
            db.add(user)
            users[email] = user
        db.commit()
        ids = {email: user.id for email, user in users.items()}

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


def _client_for(app, TestingSession, user_id: int) -> TestClient:
    def override_auth() -> CurrentAuth:
        with TestingSession() as db:
            user = db.get(User, user_id)
            db.expunge(user)
        return CurrentAuth(user=user, claims={"role": user.role}, session=None)

    app.dependency_overrides[get_current_auth] = override_auth
    return TestClient(app)


def _seed(TestingSession, *, recipients, event_type, dedupe=None, **kwargs) -> None:
    with TestingSession() as db:
        create_global_notification(
            db,
            event_type=event_type,
            title=kwargs.pop("title", "Notification"),
            message=kwargs.pop("message", "Message"),
            recipient_user_ids=recipients,
            dedupe_key=dedupe,
            **kwargs,
        )
        db.commit()
# ---------------------------------------------------------------------------
# BD -> Finance
# ---------------------------------------------------------------------------
def test_bd_to_finance_creates_finance_notification_only() -> None:
    app, TestingSession, ids = _build()
    _seed(
        TestingSession,
        recipients=[ids[FINANCE]],
        event_type="workflow.project.submitted_finance",
        title="Finance review required: GIS4456",
        message="BD submitted GIS4456",
        category="approval",
        target_url="/finance",
        severity="info",
        requires_action=True,
        metadata={"project_name": "GIS4456", "client_name": "ABC Pvt Ltd"},
    )

    finance = _client_for(app, TestingSession, ids[FINANCE])
    rows = finance.get("/api/notifications/global/popup-queue").json()
    assert len(rows) == 1
    assert rows[0]["title"] == "Finance review required: GIS4456"
    assert rows[0]["requires_action"] is True
    assert rows[0]["metadata"]["project_name"] == "GIS4456"

    # The sender does NOT receive their own approval notification.
    bd = _client_for(app, TestingSession, ids[BD])
    assert bd.get("/api/notifications/global/popup-queue").json() == []


def test_closing_popup_changes_no_backend_state() -> None:
    """Rendering/dismissing the popup must never resolve or mutate anything."""

    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.x", requires_action=True)

    client = _client_for(app, TestingSession, ids[FINANCE])
    for _ in range(10):
        client.get("/api/notifications/global/popup-queue")
    with TestingSession() as db:
        row = db.scalar(select(GlobalNotification))
        assert row.resolved_at is None, "popup rendering must not resolve"
        assert row.is_read is False, "popup rendering must not mark read"


def test_notification_stays_pending_after_read() -> None:
    """Read != Resolved: clicking Later leaves the item pending in the bell."""

    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.y", requires_action=True)

    client = _client_for(app, TestingSession, ids[FINANCE])
    listed = client.get("/api/notifications/global").json()
    notification_id = listed[0]["id"]
    client.post(f"/api/notifications/global/{notification_id}/read")

    row = client.get(f"/api/notifications/global/{notification_id}").json()
    assert row["is_read"] is True
    assert row["resolved_at"] is None, "read must never imply resolved"

    pending = client.get("/api/notifications/global/pending-count").json()
    assert pending["pending_count"] == 1, "still awaiting a business decision"

    queue = client.get("/api/notifications/global/popup-queue").json()
    assert len(queue) == 1, "the popup queue still offers the pending item"


def test_finance_approval_resolves_notification() -> None:
    """Resolution is driven by the real workflow action, not by the popup."""

    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.z", requires_action=True)

    client = _client_for(app, TestingSession, ids[FINANCE])
    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 1

    # The approval service runs in the same transaction as the real action.
    with TestingSession() as db:
        resolved = resolve_notifications(
            db,
            recipient_user_ids=[ids[FINANCE]],
            event_type="approval.z",
            resolved_by_id=ids[FINANCE],
            resolution_note="Approved by Finance",
        )
        db.commit()
    assert resolved == 1

    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 0
    assert client.get("/api/notifications/global/popup-queue").json() == []
    with TestingSession() as db:
        row = db.scalar(select(GlobalNotification))
        assert row.resolved_at is not None
        assert row.resolution_note == "Approved by Finance"


def test_resolve_never_creates_new_rows() -> None:
    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.dedupe", dedupe="k1")
    with TestingSession() as db:
        for _ in range(5):
            resolve_notifications(
                db, recipient_user_ids=[ids[FINANCE]], event_type="approval.dedupe"
            )
        db.commit()
        assert len(db.scalars(select(GlobalNotification)).all()) == 1


# ---------------------------------------------------------------------------
# Rejection / return for correction
# ---------------------------------------------------------------------------
def test_rejection_notification_carries_reason_and_requires_action() -> None:
    app, TestingSession, ids = _build()
    _seed(
        TestingSession,
        recipients=[ids[BD]],
        event_type="workflow.project.finance_return",
        title="REQUEST RETURNED",
        message="Work Order attachment missing",
        severity="danger",
        requires_action=True,
        metadata={
            "project_name": "GIS4456",
            "returned_by": "Finance",
            "status": "Correction Required",
            "reason": "Work Order attachment missing",
            "required_action": "Upload the missing Work Order and resubmit.",
        },
    )
    bd = _client_for(app, TestingSession, ids[BD])
    item = bd.get("/api/notifications/global/popup-queue").json()[0]
    assert item["severity"] == "danger"
    assert item["requires_action"] is True
    assert item["metadata"]["reason"] == "Work Order attachment missing"
    assert "resubmit" in item["metadata"]["required_action"]
# ---------------------------------------------------------------------------
# Dedupe / reminder behaviour
# ---------------------------------------------------------------------------
def test_dedupe_prevents_duplicate_notification_rows() -> None:
    app, TestingSession, ids = _build()
    for _ in range(4):
        _seed(
            TestingSession,
            recipients=[ids[FINANCE]],
            event_type="finance.advance_payment.overdue",
            dedupe="advance_overdue_project_1_2026-10-05",
            is_reminder=True,
            requires_action=True,
        )
    with TestingSession() as db:
        assert len(db.scalars(select(GlobalNotification)).all()) == 1


def test_reminder_cycle_does_not_create_duplicate_rows() -> None:
    app, TestingSession, ids = _build()
    for _ in range(10):
        _seed(
            TestingSession,
            recipients=[ids[FINANCE]],
            event_type="finance.advance_payment.overdue",
            dedupe="advance_overdue_project_1_2026-10-05",
            is_reminder=True,
            requires_action=True,
        )
    client = _client_for(app, TestingSession, ids[FINANCE])
    for _ in range(10):
        assert len(client.get("/api/notifications/global/popup-queue").json()) == 1
    with TestingSession() as db:
        assert len(db.scalars(select(GlobalNotification)).all()) == 1


def test_resolved_overdue_item_stops_qualifying() -> None:
    app, TestingSession, ids = _build()
    _seed(
        TestingSession,
        recipients=[ids[FINANCE]],
        event_type="finance.advance_payment.overdue",
        dedupe="advance_overdue_project_1_2026-10-05",
        is_reminder=True,
        requires_action=True,
    )
    client = _client_for(app, TestingSession, ids[FINANCE])
    assert len(client.get("/api/notifications/global/popup-queue").json()) == 1

    with TestingSession() as db:  # the payment/advance condition cleared
        resolve_reminders(db, dedupe_key_prefixes=["advance_overdue_project_1_"])
        db.commit()

    assert client.get("/api/notifications/global/popup-queue").json() == []
    assert client.get("/api/notifications/global/pending-count").json()["pending_count"] == 0


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
def test_popup_queue_only_returns_own_notifications() -> None:
    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.own")
    _seed(TestingSession, recipients=[ids[PM]], event_type="approval.other")
    finance = _client_for(app, TestingSession, ids[FINANCE])
    assert len(finance.get("/api/notifications/global/popup-queue").json()) == 1


def test_other_users_notification_is_not_enumerable() -> None:
    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.secret")
    with TestingSession() as db:
        notification_id = db.scalar(select(GlobalNotification.id))
    bd = _client_for(app, TestingSession, ids[BD])
    assert bd.get(f"/api/notifications/global/{notification_id}").status_code == 404


def test_financial_metadata_is_redacted_by_role_server_side() -> None:
    metadata = {"project_name": "GIS4456", "amount": 500000, "pending_amount": 200000}
    assert redact_notification_metadata(metadata, effective_role="pm") == {"project_name": "GIS4456"}
    assert redact_notification_metadata(metadata, effective_role="qc") == {"project_name": "GIS4456"}
    assert redact_notification_metadata(metadata, effective_role="finance")["amount"] == 500000
# ---------------------------------------------------------------------------
# Management reminder setting
# ---------------------------------------------------------------------------
def test_default_reminder_interval_is_ten_minutes() -> None:
    _, TestingSession, _ = _build()
    with TestingSession() as db:
        assert get_overdue_reminder_minutes(db) == DEFAULT_OVERDUE_REMINDER_MINUTES == 10


def test_authorized_management_accounts_hold_the_capability() -> None:
    _, TestingSession, ids = _build()
    with TestingSession() as db:
        chethan = db.get(User, ids[CHETHAN])
        vinod = db.get(User, ids[VINOD])
        other = db.get(User, ids[OTHER_MANAGER])
        assert can_manage_notification_settings(chethan, "management") is True
        assert can_manage_notification_settings(vinod, "management") is True
        # A different Management account does NOT hold the capability.
        assert can_manage_notification_settings(other, "management") is False
        # Nor does an authorized account acting outside its role.
        assert can_manage_notification_settings(chethan, "finance") is False


def test_authorized_management_can_update_reminder_interval() -> None:
    app, TestingSession, ids = _build()
    client = _client_for(app, TestingSession, ids[CHETHAN])

    current = client.get("/api/notifications/global/settings/notification-settings").json()
    assert current["overdue_popup_reminder_minutes"] == 10
    assert current["can_manage"] is True

    updated = client.put(
        "/api/notifications/global/settings/notification-settings",
        json={"overdue_popup_reminder_minutes": 5},
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["overdue_popup_reminder_minutes"] == 5
    assert body["previous_overdue_popup_reminder_minutes"] == 10
    assert 5 in body["suggested_minutes"]
    assert client.get("/api/notifications/global/settings/notification-settings").json()[
        "overdue_popup_reminder_minutes"
    ] == 5


def test_unauthorized_users_cannot_update_reminder_interval() -> None:
    app, TestingSession, ids = _build()
    for email in (FINANCE, BD, PM, OTHER_MANAGER):
        client = _client_for(app, TestingSession, ids[email])
        response = client.put(
            "/api/notifications/global/settings/notification-settings",
            json={"overdue_popup_reminder_minutes": 5},
        )
        assert response.status_code == 403, f"{email} must not change the reminder interval"

    with TestingSession() as db:
        assert get_overdue_reminder_minutes(db) == 10, "a denied update must not persist"


def test_unauthorized_user_cannot_read_manage_flag() -> None:
    app, TestingSession, ids = _build()
    client = _client_for(app, TestingSession, ids[FINANCE])
    body = client.get("/api/notifications/global/settings/notification-settings").json()
    assert body["can_manage"] is False
    assert body["overdue_popup_reminder_minutes"] == 10


def test_reminder_interval_rejects_out_of_range_values() -> None:
    _, TestingSession, _ = _build()
    with TestingSession() as db:
        for bad in (0, -5, 5000):
            try:
                set_overdue_reminder_minutes(db, minutes=bad, actor_id=None)
            except Exception as exc:  # noqa: BLE001 - HTTPException expected
                assert getattr(exc, "status_code", None) == 422
            else:  # pragma: no cover - guard
                raise AssertionError(f"{bad} must be rejected")
        assert get_overdue_reminder_minutes(db) == 10


def test_settings_payload_shape() -> None:
    _, TestingSession, _ = _build()
    with TestingSession() as db:
        payload = notification_settings_payload(db)
    assert payload["suggested_minutes"] == [5, 10, 15, 30, 60]
    assert payload["default_minutes"] == 10


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------
def test_popup_queue_is_ordered_and_capped() -> None:
    app, TestingSession, ids = _build()
    for index in range(7):
        _seed(
            TestingSession,
            recipients=[ids[FINANCE]],
            event_type=f"approval.q{index}",
            title=f"Item {index}",
        )
    with TestingSession() as db:
        rows = list_popup_notifications(
            db, user_id=ids[FINANCE], effective_role="finance", limit=3
        )
    assert [row["title"] for row in rows] == ["Item 0", "Item 1", "Item 2"]


def test_pending_count_only_counts_action_items() -> None:
    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="info.plain")
    _seed(
        TestingSession,
        recipients=[ids[FINANCE]],
        event_type="approval.needs_action",
        requires_action=True,
    )
    with TestingSession() as db:
        assert pending_count_for_user(db, user_id=ids[FINANCE]) == 1


def test_read_state_is_still_persisted_for_history() -> None:
    app, TestingSession, ids = _build()
    _seed(TestingSession, recipients=[ids[FINANCE]], event_type="approval.history", requires_action=True)
    client = _client_for(app, TestingSession, ids[FINANCE])
    notification_id = client.get("/api/notifications/global").json()[0]["id"]
    client.post(f"/api/notifications/global/{notification_id}/read")
    with TestingSession() as db:
        row = db.get(GlobalNotification, notification_id)
        assert row.is_read is True
        assert row.read_at is not None
        assert row.read_at <= utc_now()


def test_popup_api_redacts_amount_for_pm() -> None:
    app, TestingSession, ids = _build()
    _seed(
        TestingSession,
        recipients=[ids[PM]],
        event_type="workflow.assignment",
        metadata={"project_name": "GIS2234", "amount": 500000},
    )
    pm = _client_for(app, TestingSession, ids[PM])
    item = pm.get("/api/notifications/global/popup-queue").json()[0]
    assert "amount" not in item["metadata"]
    assert item["metadata"]["project_name"] == "GIS2234"