from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.travel_km.models import TravelKmClaim, TravelKmEvent, TravelKmTrackPoint
from app.modules.travel_km.router import _tracking_is_active, _tracking_snapshot
from app.modules.travel_km.schemas import TravelKmClaimCreateRequest, TravelKmTrackPointRequest
from app.modules.travel_km.service import add_event, create_claim


def _session() -> Session:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            FinanceClient.__table__,
            FinanceProject.__table__,
            TravelKmClaim.__table__,
            TravelKmEvent.__table__,
            TravelKmTrackPoint.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def test_live_tracking_snapshot_is_consent_scoped_and_route_distance_is_reference_only():
    db = _session()
    try:
        employee = User(
            email="live.gps.employee@nakshatech.com",
            full_name="Live GPS Employee",
            password_hash="test-hash",
            role="employee",
            branch="Head Office",
            email_verified=True,
            account_status="active",
            is_active=True,
        )
        project = FinanceProject(
            project_code="GPS-LIVE-001",
            project_name="Live GPS QA Project",
            client_name="QA Client",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        db.add_all([employee, project]); db.flush()
        claim = create_claim(
            db,
            requester=employee,
            payload=TravelKmClaimCreateRequest(
                project_id=project.id,
                travel_date=date(2026, 8, 31),
                purpose_description="Live GPS field travel verification",
                start_km=Decimal("100.00"),
                start_latitude=12.9716,
                start_longitude=77.5946,
                start_accuracy_m=7.0,
                start_captured_at=datetime(2026, 8, 31, 9, 0, 0),
            ),
        )
        add_event(
            db,
            claim=claim,
            action="live_tracking_started",
            actor=employee,
            from_status="draft",
            to_status="draft",
            comments="Employee explicitly started live GPS tracking.",
            metadata={"consent_action": "employee_tapped_start_live_gps"},
        )
        db.add_all([
            TravelKmTrackPoint(
                claim_id=claim.id,
                latitude=12.9716,
                longitude=77.5946,
                accuracy_m=7.0,
                captured_at=datetime(2026, 8, 31, 9, 0, 0),
            ),
            TravelKmTrackPoint(
                claim_id=claim.id,
                latitude=12.9816,
                longitude=77.6046,
                accuracy_m=8.0,
                captured_at=datetime(2026, 8, 31, 9, 10, 0),
            ),
        ])
        db.commit()

        assert _tracking_is_active(db, claim) is True
        snapshot = _tracking_snapshot(db, claim)
        assert snapshot["tracking_active"] is True
        assert snapshot["point_count"] == 2
        assert 1.0 < snapshot["route_distance_km"] < 2.0
        assert len(snapshot["points"]) == 2

        add_event(
            db,
            claim=claim,
            action="live_tracking_stopped",
            actor=employee,
            from_status="draft",
            to_status="draft",
            comments="Employee stopped live GPS tracking.",
        )
        db.commit()
        assert _tracking_is_active(db, claim) is False
    finally:
        db.close()


def test_live_tracking_schema_rejects_invalid_coordinates():
    try:
        TravelKmTrackPointRequest(
            latitude=123.0,
            longitude=77.0,
            accuracy_m=5.0,
            captured_at=datetime(2026, 8, 31, 9, 0, 0),
        )
        raise AssertionError("Invalid latitude must be rejected")
    except ValueError as exc:
        assert "Latitude" in str(exc)
