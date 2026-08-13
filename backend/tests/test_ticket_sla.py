from __future__ import annotations

from datetime import datetime, timedelta
import os

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-only-change-me-32-characters")

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User
from app.modules.backup import models as backup_models  # noqa: F401
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.employee_portal import models as employee_portal_models  # noqa: F401
from app.modules.employee_portal.models import AuditEvent, SupportTicket
from app.modules.it_activity import models as it_activity_models  # noqa: F401
from app.modules.notifications.models import GlobalNotification
from app.services.ticket_sla_service import (
    build_ticket_sla_snapshot,
    build_ticket_sla_snapshot_map,
    ensure_critical_sla_breach_notifications,
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


def _ticket(*, created_at: datetime, priority: str, target: int) -> SupportTicket:
    return SupportTicket(
        id=1,
        ticket_code="NT-IT-2026-00001",
        requester_id=1,
        branch_id=1,
        department="it",
        title="SLA validation ticket",
        description="Used for SLA validation.",
        priority=priority,
        status="new",
        sla_target_minutes=target,
        created_at=created_at,
        updated_at=created_at,
    )


def test_sla_snapshot_on_track_warning_met_and_breached() -> None:
    now = datetime(2026, 8, 12, 10, 0, 0)

    on_track = build_ticket_sla_snapshot(
        _ticket(created_at=now - timedelta(minutes=30), priority="high", target=120),
        first_response_at=None,
        now=now,
    )
    assert on_track["sla_status"] == "on_track"
    assert on_track["sla_remaining_seconds"] == 90 * 60

    warning = build_ticket_sla_snapshot(
        _ticket(created_at=now - timedelta(minutes=100), priority="high", target=120),
        first_response_at=None,
        now=now,
    )
    assert warning["sla_status"] == "warning"
    assert warning["sla_warning"] is True
    assert warning["sla_remaining_seconds"] == 20 * 60

    met_ticket = _ticket(created_at=now - timedelta(minutes=100), priority="high", target=120)
    met = build_ticket_sla_snapshot(
        met_ticket,
        first_response_at=met_ticket.created_at + timedelta(minutes=60),
        now=now,
    )
    assert met["sla_status"] == "met"
    assert met["sla_breached"] is False

    late_ticket = _ticket(created_at=now - timedelta(minutes=150), priority="high", target=120)
    breached = build_ticket_sla_snapshot(
        late_ticket,
        first_response_at=late_ticket.created_at + timedelta(minutes=130),
        now=now,
    )
    assert breached["sla_status"] == "breached"
    assert breached["sla_breached"] is True
    assert breached["sla_escalation_level"] == "breach"


def test_critical_unanswered_breach_notifies_management_and_department_once() -> None:
    TestingSession = _session()
    now = datetime(2026, 8, 12, 10, 0, 0)
    with TestingSession() as db:
        employee = User(email="employee@example.com", full_name="Employee", password_hash="unused", role="employee", is_active=True)
        it_user = User(email="it@example.com", full_name="IT User", password_hash="unused", role="it", is_active=True)
        manager = User(email="manager@example.com", full_name="Manager", password_hash="unused", role="management", is_active=True)
        db.add_all([employee, it_user, manager])
        db.flush()
        ticket = SupportTicket(
            ticket_code="NT-IT-2026-00420",
            requester_id=employee.id,
            branch_id=1,
            department="it",
            title="Critical outage",
            description="Critical outage requires immediate response.",
            priority="critical",
            status="new",
            sla_target_minutes=30,
            created_at=now - timedelta(minutes=45),
            updated_at=now - timedelta(minutes=45),
        )
        db.add(ticket)
        db.commit()

        created = ensure_critical_sla_breach_notifications(db, now=now, force=True)
        db.commit()
        assert created == 2

        rows = list(db.scalars(select(GlobalNotification).where(GlobalNotification.event_type == "ticket.sla.critical_breach")).all())
        assert len(rows) == 2
        assert {row.recipient_user_id for row in rows} == {it_user.id, manager.id}
        assert all(row.target_url == f"/tickets/{ticket.id}" for row in rows)
        assert all("Critical SLA breached" in row.title for row in rows)

        duplicate = ensure_critical_sla_breach_notifications(db, now=now + timedelta(minutes=1), force=True)
        db.commit()
        assert duplicate == 0
        assert len(db.scalars(select(GlobalNotification).where(GlobalNotification.event_type == "ticket.sla.critical_breach")).all()) == 2


def test_sla_first_response_uses_first_non_requester_ticket_action() -> None:
    TestingSession = _session()
    created_at = datetime(2026, 8, 12, 8, 0, 0)
    with TestingSession() as db:
        employee = User(email="requester@example.com", full_name="Requester", password_hash="unused", role="employee", is_active=True)
        it_user = User(email="handler@example.com", full_name="Handler", password_hash="unused", role="it", is_active=True)
        db.add_all([employee, it_user])
        db.flush()
        ticket = SupportTicket(
            ticket_code="NT-IT-2026-00421",
            requester_id=employee.id,
            branch_id=1,
            department="it",
            title="High priority issue",
            description="High priority issue for SLA response testing.",
            priority="high",
            status="in_progress",
            sla_target_minutes=120,
            created_at=created_at,
            updated_at=created_at + timedelta(minutes=25),
        )
        db.add(ticket)
        db.flush()
        db.add_all([
            AuditEvent(
                user_id=employee.id,
                actor_email=employee.email,
                event_type="TICKET_MESSAGE_ADDED",
                module="tickets",
                target_type="ticket",
                target_id=str(ticket.id),
                created_at=created_at + timedelta(minutes=5),
            ),
            AuditEvent(
                user_id=it_user.id,
                actor_email=it_user.email,
                event_type="TICKET_UPDATED",
                module="tickets",
                target_type="ticket",
                target_id=str(ticket.id),
                created_at=created_at + timedelta(minutes=20),
            ),
        ])
        db.commit()

        snapshot = build_ticket_sla_snapshot_map(db, [ticket], now=created_at + timedelta(minutes=60))[ticket.id]
        assert snapshot["sla_first_response_at"] == created_at + timedelta(minutes=20)
        assert snapshot["sla_status"] == "met"
        assert snapshot["sla_breached"] is False
