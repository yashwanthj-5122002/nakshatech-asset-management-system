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
from app.models.entities import User
from app.modules.backup import models as backup_models  # noqa: F401
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.employee_portal import models as employee_portal_models  # noqa: F401
from app.modules.it_activity import models as it_activity_models  # noqa: F401
from app.modules.notifications.models import GlobalNotification  # noqa: F401
from app.modules.notifications.router import router as notification_router
from app.modules.notifications.service import create_global_notification


def _build_test_context():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSession() as db:
        management_one = User(
            email="manager.one@example.com",
            full_name="Manager One",
            password_hash="unused",
            role="management",
            is_active=True,
        )
        management_two = User(
            email="manager.two@example.com",
            full_name="Manager Two",
            password_hash="unused",
            role="management",
            is_active=True,
        )
        it_user = User(
            email="it@example.com",
            full_name="IT User",
            password_hash="unused",
            role="it",
            is_active=True,
        )
        inactive_management = User(
            email="inactive.manager@example.com",
            full_name="Inactive Manager",
            password_hash="unused",
            role="management",
            is_active=False,
        )
        db.add_all([management_one, management_two, it_user, inactive_management])
        db.commit()
        db.refresh(management_one)
        db.refresh(management_two)
        db.refresh(it_user)
        ids = {
            "management_one": management_one.id,
            "management_two": management_two.id,
            "it": it_user.id,
        }

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


def _auth_override(TestingSession, user_id: int):
    def override_auth() -> CurrentAuth:
        with TestingSession() as db:
            user = db.get(User, user_id)
            assert user is not None
            db.expunge(user)
        return CurrentAuth(user=user, claims={"role": user.role}, session=None)

    return override_auth


def test_role_fanout_dedupe_and_private_read_state() -> None:
    app, TestingSession, ids = _build_test_context()

    with TestingSession() as db:
        first = create_global_notification(
            db,
            event_type="approval_required",
            category="approval",
            title="Management approval required",
            message="ITW-1000 is ready for review.",
            target_url="/work?focus=ITW-1000",
            recipient_roles=["management"],
            dedupe_key="approval:itw-1000:submitted",
        )
        db.commit()
        assert len(first) == 2

        duplicate = create_global_notification(
            db,
            event_type="approval_required",
            category="approval",
            title="Management approval required",
            message="ITW-1000 is ready for review.",
            target_url="/work?focus=ITW-1000",
            recipient_roles=["management"],
            dedupe_key="approval:itw-1000:submitted",
        )
        db.commit()
        assert duplicate == []
        assert len(db.scalars(select(GlobalNotification)).all()) == 2

    app.dependency_overrides[get_current_auth] = _auth_override(TestingSession, ids["management_one"])
    with TestClient(app) as client:
        listed = client.get("/api/notifications/global")
        assert listed.status_code == 200, listed.text
        assert len(listed.json()) == 1
        notification_id = listed.json()[0]["id"]
        assert listed.json()[0]["target_url"] == "/work?focus=ITW-1000"
        assert client.get("/api/notifications/global/unread-count").json() == {"unread_count": 1}

        marked = client.post(f"/api/notifications/global/{notification_id}/read")
        assert marked.status_code == 200, marked.text
        assert marked.json()["is_read"] is True
        assert marked.json()["read_at"] is not None
        assert client.get("/api/notifications/global/unread-count").json() == {"unread_count": 0}

    # The second manager still has their own unread receipt.
    app.dependency_overrides[get_current_auth] = _auth_override(TestingSession, ids["management_two"])
    with TestClient(app) as client:
        assert client.get("/api/notifications/global/unread-count").json() == {"unread_count": 1}
        listed = client.get("/api/notifications/global?unread_only=true&category=approval")
        assert listed.status_code == 200, listed.text
        assert len(listed.json()) == 1

        marked_all = client.post("/api/notifications/global/read-all?category=approval")
        assert marked_all.status_code == 200, marked_all.text
        assert marked_all.json() == {"updated": 1}
        assert client.get("/api/notifications/global/unread-count").json() == {"unread_count": 0}


def test_notification_access_is_user_scoped_and_target_url_is_internal() -> None:
    app, TestingSession, ids = _build_test_context()

    with TestingSession() as db:
        created = create_global_notification(
            db,
            event_type="ticket_updated",
            category="ticket",
            title="Ticket updated",
            message="Your ticket has a new response.",
            target_url="/employee/tickets/42",
            recipient_user_ids=[ids["it"]],
            dedupe_key="ticket:42:update:1",
        )
        db.commit()
        assert len(created) == 1
        notification_id = created[0].id

        try:
            create_global_notification(
                db,
                event_type="bad_link",
                title="Bad link",
                message="Should fail",
                target_url="https://example.com/phish",
                recipient_user_ids=[ids["it"]],
            )
        except ValueError as exc:
            assert "internal application path" in str(exc)
        else:
            raise AssertionError("External notification target URL was accepted")

    app.dependency_overrides[get_current_auth] = _auth_override(TestingSession, ids["management_one"])
    with TestClient(app) as client:
        assert client.get(f"/api/notifications/global/{notification_id}").status_code == 404
        assert client.post(f"/api/notifications/global/{notification_id}/read").status_code == 404

    app.dependency_overrides[get_current_auth] = _auth_override(TestingSession, ids["it"])
    with TestClient(app) as client:
        response = client.get(f"/api/notifications/global/{notification_id}")
        assert response.status_code == 200, response.text
        assert response.json()["event_type"] == "ticket_updated"
