from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-only-change-me-32-characters")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User, utc_now
from app.modules.backup import models as backup_models  # noqa: F401
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.employee_portal import models as employee_portal_models  # noqa: F401
from app.modules.it_activity import models as it_activity_models  # noqa: F401
from app.modules.notifications.models import GlobalNotification
from app.services.ticket_notification_service import (
    notify_ticket_created,
    notify_ticket_department_reply,
    notify_ticket_reopened,
    notify_ticket_requester_reply,
    notify_ticket_status_to_requester,
)


def _session():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    return TestingSession


def _add_users(db):
    employee = User(
        email="employee@example.com",
        full_name="Employee User",
        password_hash="unused",
        role="employee",
        is_active=True,
    )
    it_one = User(
        email="it.one@example.com",
        full_name="IT One",
        password_hash="unused",
        role="it",
        is_active=True,
    )
    it_two = User(
        email="it.two@example.com",
        full_name="IT Two",
        password_hash="unused",
        role="it",
        is_active=True,
    )
    db.add_all([employee, it_one, it_two])
    db.commit()
    return employee, it_one, it_two


def test_ticket_creation_critical_reopen_and_dedupe_route_to_it() -> None:
    TestingSession = _session()
    with TestingSession() as db:
        employee, it_one, it_two = _add_users(db)
        token = utc_now()
        notify_ticket_created(
            db,
            ticket_id=42,
            ticket_code="NT-IT-2026-00042",
            department="it",
            priority="critical",
            title="Laptop cannot boot",
            requester_name=employee.full_name,
            event_token=token,
        )
        notify_ticket_created(
            db,
            ticket_id=42,
            ticket_code="NT-IT-2026-00042",
            department="it",
            priority="critical",
            title="Laptop cannot boot",
            requester_name=employee.full_name,
            event_token=token,
        )
        db.commit()

        rows = list(db.scalars(select(GlobalNotification).order_by(GlobalNotification.recipient_user_id)).all())
        assert len(rows) == 2
        assert {row.recipient_user_id for row in rows} == {it_one.id, it_two.id}
        assert all(row.category == "ticket" for row in rows)
        assert all(row.event_type == "ticket.created.critical" for row in rows)
        assert all(row.target_url == "/tickets/42" for row in rows)
        assert all("Critical" in row.title for row in rows)

        notify_ticket_reopened(
            db,
            ticket_id=42,
            ticket_code="NT-IT-2026-00042",
            department="it",
            event_token="reopen-1",
        )
        db.commit()
        reopened = list(
            db.scalars(select(GlobalNotification).where(GlobalNotification.event_type == "ticket.reopened")).all()
        )
        assert len(reopened) == 2
        assert {row.recipient_user_id for row in reopened} == {it_one.id, it_two.id}


def test_ticket_reply_and_resolution_notifications_are_user_scoped() -> None:
    TestingSession = _session()
    with TestingSession() as db:
        employee, it_one, it_two = _add_users(db)

        notify_ticket_requester_reply(
            db,
            ticket_id=9,
            ticket_code="NT-IT-2026-00009",
            department="it",
            message_id=101,
            message_preview="The problem is still happening.",
        )
        notify_ticket_department_reply(
            db,
            ticket_id=9,
            ticket_code="NT-IT-2026-00009",
            requester_user_id=employee.id,
            message_id=102,
            message_preview="We are checking the device.",
        )
        notify_ticket_status_to_requester(
            db,
            ticket_id=9,
            ticket_code="NT-IT-2026-00009",
            requester_user_id=employee.id,
            status="resolved",
            event_token="resolved-1",
            resolution="Replaced faulty RAM.",
        )
        db.commit()

        employee_rows = list(
            db.scalars(
                select(GlobalNotification)
                .where(GlobalNotification.recipient_user_id == employee.id)
                .order_by(GlobalNotification.id)
            ).all()
        )
        assert [row.event_type for row in employee_rows] == ["ticket.department_reply", "ticket.resolved"]
        assert all(row.target_url == "/tickets/9" for row in employee_rows)
        assert "Replaced faulty RAM" in employee_rows[-1].message

        it_rows = list(
            db.scalars(select(GlobalNotification).where(GlobalNotification.event_type == "ticket.requester_reply")).all()
        )
        assert len(it_rows) == 2
        assert {row.recipient_user_id for row in it_rows} == {it_one.id, it_two.id}
