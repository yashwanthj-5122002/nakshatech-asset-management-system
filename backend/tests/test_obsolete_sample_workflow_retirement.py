from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.notifications.models import GlobalNotification
from app.modules.notifications.service import (
    OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES,
    OBSOLETE_SAMPLE_NOTIFICATION_RESOLUTION,
    create_global_notification,
    list_notifications_for_user,
    list_popup_notifications,
    retire_obsolete_sample_notifications,
)


def _user(db, *, email: str, role: str) -> User:
    row = User(
        email=email,
        full_name=email.split("@")[0],
        password_hash="test",
        role=role,
        is_active=True,
        account_status="active",
    )
    db.add(row)
    db.flush()
    return row


def test_sample_request_routes_are_retired_but_current_workflow_routes_remain() -> None:
    """Route presence/absence must be proven by real HTTP dispatch, not by walking
    ``router.routes`` — this FastAPI version defers ``include_router`` sub-router
    expansion into lazy wrapper objects, so a flat ``.routes`` scan undercounts
    perfectly normal, correctly-wired endpoints. A 404 is the only unambiguous
    "not mounted" signal; any other status (even 401/403/422) proves the route exists.
    """
    with SessionLocal() as db:
        bd = _user(db, email="bd.route.retirement@nakshatech.com", role="bd")
        db.commit()
        bd_email = bd.email

    def auth_override():
        with SessionLocal() as db:
            selected = db.scalar(select(User).where(User.email == bd_email))
            return CurrentAuth(user=selected, claims={"role": selected.role}, session=None)

    app.dependency_overrides[get_current_auth] = auth_override
    client = TestClient(app)
    try:
        # Retired Sample Request API: every one of its routes must be gone (404),
        # not merely unauthorized, across the full method set it used to expose.
        assert client.get("/api/operations/samples/dashboard").status_code == 404
        assert client.post("/api/operations/bd/opportunities/1/samples").status_code == 404
        assert client.post("/api/operations/samples/1/start").status_code == 404
        assert client.post("/api/operations/samples/1/submit").status_code == 404
        assert client.post("/api/operations/samples/1/client-review").status_code == 404
        assert client.post("/api/operations/samples/1/client-decision").status_code == 404

        # Current authoritative workflow routes remain live (any non-404 proves wiring).
        assert client.get("/api/operations/workflow/bd/dashboard").status_code != 404
        assert client.get("/api/operations/workflow/bd/projects").status_code != 404
        assert client.get("/api/operations/workflow/finance/dashboard").status_code != 404
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


def test_all_exact_obsolete_events_are_suppressed_without_affecting_current_events() -> None:
    with SessionLocal() as db:
        finance = _user(db, email="finance.sample.retirement@nakshatech.com", role="finance")
        for event_type in OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES:
            assert create_global_notification(
                db,
                event_type=event_type,
                title="Legacy sample event",
                message="This must not be inserted",
                recipient_user_ids=[finance.id],
            ) == []

        created = create_global_notification(
            db,
            event_type="workflow.project.submitted_finance",
            title="Finance review required",
            message="Current BD workflow remains active",
            category="approval",
            target_url="/finance",
            recipient_user_ids=[finance.id],
            requires_action=True,
        )
        db.commit()

        assert len(created) == 1
        events = list(db.scalars(select(GlobalNotification.event_type)).all())
        assert events == ["workflow.project.submitted_finance"]


def test_historical_sample_notifications_are_resolved_idempotently_and_preserved() -> None:
    with SessionLocal() as db:
        bd = _user(db, email="bd.sample.retirement@nakshatech.com", role="bd")
        for index, event_type in enumerate(sorted(OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES), start=1):
            db.add(GlobalNotification(
                recipient_user_id=bd.id,
                event_type=event_type,
                category="system",
                title=f"Legacy event {index}",
                message="Historical Sample Request notification",
                target_url="/sample-requests",
                dedupe_key=f"legacy-sample-{index}",
                requires_action=True,
            ))
        current = GlobalNotification(
            recipient_user_id=bd.id,
            event_type="workflow.project.returned_bd",
            category="approval",
            title="Finance returned current project",
            message="Current workflow notification",
            target_url="/bd-dashboard",
            dedupe_key="current-bd-event",
            requires_action=True,
        )
        db.add(current)
        db.flush()

        assert retire_obsolete_sample_notifications(db) == 4
        db.commit()
        assert retire_obsolete_sample_notifications(db) == 0

        rows = list(db.scalars(select(GlobalNotification).order_by(GlobalNotification.id)).all())
        assert len(rows) == 5, "historical rows are preserved, not deleted"
        legacy_rows = [row for row in rows if row.event_type in OBSOLETE_SAMPLE_NOTIFICATION_EVENT_TYPES]
        assert len(legacy_rows) == 4
        for row in legacy_rows:
            assert row.is_read is True
            assert row.read_at is not None
            assert row.requires_action is False
            assert row.resolved_at is not None
            assert row.resolution_note == OBSOLETE_SAMPLE_NOTIFICATION_RESOLUTION
            assert row.target_url is None

        db.refresh(current)
        assert current.is_read is False
        assert current.resolved_at is None
        assert current.requires_action is True
        assert current.target_url == "/bd-dashboard"

        popup = list_popup_notifications(db, user_id=bd.id, effective_role="bd")
        assert [item["event_type"] for item in popup] == ["workflow.project.returned_bd"]
        history = list_notifications_for_user(db, user_id=bd.id)
        assert len(history) == 5

