from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.travel_km.models import (
    TravelKmAttachment,
    TravelKmClaim,
    TravelKmEmailDelivery,
    TravelKmEmailRouting,
    TravelKmEvent,
    TravelKmProjectGeofence,
    TravelKmTrackPoint,
    TravelKmVerificationSnapshot,
)
from app.modules.travel_km.schemas import (
    TravelKmClaimCreateRequest,
    TravelKmEmailRoutingRequest,
    TravelKmEndRequest,
    TravelKmProjectGeofenceRequest,
)
from app.modules.travel_km.service import create_claim, finish_journey, submit_claim
from app.modules.travel_km.verification import (
    build_verification,
    project_geofence_payload,
    set_project_geofence,
    verification_payload,
)


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
            TravelKmAttachment.__table__,
            TravelKmEvent.__table__,
            TravelKmEmailRouting.__table__,
            TravelKmEmailDelivery.__table__,
            TravelKmTrackPoint.__table__,
            TravelKmProjectGeofence.__table__,
            TravelKmVerificationSnapshot.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def _seed(db: Session) -> tuple[User, User, FinanceProject, TravelKmClaim]:
    employee = User(
        email="smart.employee@nakshatech.com",
        full_name="Smart Travel Employee",
        password_hash="test-hash",
        role="employee",
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    admin = User(
        email="smart.admin@nakshatech.com",
        full_name="Smart Travel Admin",
        password_hash="test-hash",
        role="admin",
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    project = FinanceProject(
        project_code="SMART-KM-001",
        project_name="Smart Journey QA Project",
        client_name="QA Client",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )
    db.add_all([employee, admin, project]); db.flush()
    claim = create_claim(
        db,
        requester=employee,
        payload=TravelKmClaimCreateRequest(
            project_id=project.id,
            travel_date=date(2026, 9, 1),
            purpose_description="Smart verification and project geofence field test",
            start_km=Decimal("1000.00"),
            start_latitude=12.9716,
            start_longitude=77.5946,
            start_accuracy_m=8.0,
            start_captured_at=datetime(2026, 9, 1, 9, 0, 0),
            email_routing=TravelKmEmailRoutingRequest(
                reporting_manager_email="manager@nakshatech.com",
                to_emails=["admin@nakshatech.com"],
                cc_emails=[],
            ),
        ),
    )
    return employee, admin, project, claim


def _finish_with_evidence(db: Session, employee: User, claim: TravelKmClaim, end_km: str = "1002.00") -> TravelKmClaim:
    claim = finish_journey(
        db,
        claim=claim,
        requester=employee,
        payload=TravelKmEndRequest(
            end_km=Decimal(end_km),
            end_latitude=12.9896,
            end_longitude=77.5946,
            end_accuracy_m=9.0,
            end_captured_at=datetime(2026, 9, 1, 9, 10, 0),
        ),
    )
    for phase, lat, captured in (
        ("start", 12.9716, datetime(2026, 9, 1, 9, 0, 0)),
        ("end", 12.9896, datetime(2026, 9, 1, 9, 10, 0)),
    ):
        db.add(
            TravelKmAttachment(
                claim_id=claim.id,
                phase=phase,
                uploaded_by_id=employee.id,
                original_filename=f"{phase}.jpg",
                storage_key=f"travel-km/smart/{claim.id}/{phase}.jpg",
                mime_type="image/jpeg",
                file_size=100,
                content_sha256=("a" if phase == "start" else "b") * 64,
                device_latitude=lat,
                device_longitude=77.5946,
                device_accuracy_m=8.0,
                device_captured_at=captured,
                exif_gps_present=False,
                verification_flag="live_gps_captured",
            )
        )
    start = datetime(2026, 9, 1, 9, 0, 0)
    # 21 points over about 2 km, 30 seconds apart.
    for index in range(21):
        db.add(
            TravelKmTrackPoint(
                claim_id=claim.id,
                latitude=12.9716 + (0.0009 * index),
                longitude=77.5946,
                accuracy_m=8.0 + (index % 3),
                captured_at=start + timedelta(seconds=30 * index),
            )
        )
    db.commit(); db.refresh(claim)
    return claim


def test_smart_verification_confirms_consistent_route_and_project_geofence():
    db = _session()
    try:
        employee, admin, project, claim = _seed(db)
        set_project_geofence(
            db,
            project_id=project.id,
            actor=admin,
            payload=TravelKmProjectGeofenceRequest(
                site_name="QA Survey Site",
                center_latitude=12.9896,
                center_longitude=77.5946,
                radius_m=200,
                is_active=True,
            ),
        )
        db.commit()
        config = project_geofence_payload(db, project.id)
        assert config["configured"] is True
        assert config["site_name"] == "QA Survey Site"

        claim = _finish_with_evidence(db, employee, claim)
        preview = build_verification(db, claim)
        assert preview["score"] is not None
        assert preview["score"] >= 80
        assert preview["outcome"] == "verified"
        assert preview["geofence"]["site_entered"] is True
        assert preview["route"]["point_count"] == 21
        assert preview["route"]["variance_percent"] < 15

        claim = submit_claim(db, claim=claim, requester=employee)
        frozen = verification_payload(db, claim)
        assert frozen["source"] == "submission_snapshot"
        assert frozen["snapshot_locked"] is True
        assert frozen["outcome"] == "verified"
        snapshot = db.query(TravelKmVerificationSnapshot).filter_by(claim_id=claim.id).one()
        assert snapshot.site_entered is True
        assert snapshot.score >= 80
    finally:
        db.close()


def test_smart_verification_flags_large_odometer_route_variance_without_auto_rejecting():
    db = _session()
    try:
        employee, _admin, _project, claim = _seed(db)
        claim = _finish_with_evidence(db, employee, claim, end_km="1010.00")
        preview = build_verification(db, claim)
        assert preview["outcome"] == "high_variance"
        assert preview["route"]["variance_percent"] > 50
        assert any(flag["code"] == "high_route_variance" for flag in preview["flags"])

        claim = submit_claim(db, claim=claim, requester=employee)
        # Advisory score never auto-rejects or changes the normal approval workflow.
        assert claim.status == "submitted"
        assert float(claim.odometer_km) == 10.0
        assert float(claim.calculated_allowance) == 50.0
        snapshot = db.query(TravelKmVerificationSnapshot).filter_by(claim_id=claim.id).one()
        assert snapshot.outcome == "high_variance"
    finally:
        db.close()


def test_geofence_schema_rejects_unreasonable_radius():
    try:
        TravelKmProjectGeofenceRequest(
            site_name="Bad radius",
            center_latitude=12.9,
            center_longitude=77.5,
            radius_m=20,
        )
        raise AssertionError("Radius below 50 metres must be rejected")
    except ValueError as exc:
        assert "greater than or equal to 50" in str(exc)
