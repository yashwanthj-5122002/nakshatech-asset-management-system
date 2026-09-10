from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.travel_km.models import (TravelKmAttachment, TravelKmClaim, TravelKmEmailDelivery, TravelKmEmailRouting, TravelKmEvent, TravelKmProjectGeofence, TravelKmTrackPoint, TravelKmVerificationSnapshot)
from app.modules.travel_km.reporting import build_travel_km_workbook
from app.modules.travel_km.schemas import (
    TravelKmClaimCreateRequest,
    TravelKmDecisionRequest,
    TravelKmEmailRoutingRequest,
    TravelKmEndRequest,
    TravelKmFinanceDecisionRequest,
)
from app.modules.travel_km.service import (
    admin_decision,
    claim_payload,
    create_claim,
    dashboard_payload,
    finance_decision,
    finish_journey,
    haversine_km,
    hr_decision,
    submit_claim,
)


def _isolated_session() -> Session:
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
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return TestingSession()


def _user(db: Session, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _project(db: Session) -> FinanceProject:
    row = FinanceProject(
        project_code="KM-TEST-001",
        project_name="Travel KM QA Project",
        client_name="QA Client",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def test_haversine_is_deterministic_and_non_negative():
    same = haversine_km(12.9716, 77.5946, 12.9716, 77.5946)
    moved = haversine_km(12.9716, 77.5946, 12.9816, 77.6046)
    assert same == 0
    assert 1.0 < moved < 2.0


def test_employee_admin_hr_finance_travel_km_lifecycle_isolated():
    db = _isolated_session()
    try:
        project = _project(db)
        employee = _user(db, "travel.employee@nakshatech.com", "employee", "Travel Employee")
        admin = _user(db, "travel.admin@nakshatech.com", "admin", "Travel Admin")
        hr = _user(db, "travel.hr@nakshatech.com", "hr", "Travel HR")
        finance = _user(db, "travel.finance@nakshatech.com", "finance", "Travel Finance")
        management = _user(db, "travel.management@nakshatech.com", "management", "Travel Management")
        db.commit()

        claim = create_claim(
            db,
            requester=employee,
            payload=TravelKmClaimCreateRequest(
                project_id=project.id,
                travel_date=date(2026, 8, 31),
                purpose_description="Project site survey travel",
                start_km=Decimal("1000.00"),
                start_latitude=12.9716,
                start_longitude=77.5946,
                start_accuracy_m=8.0,
                start_captured_at=datetime(2026, 8, 31, 8, 0, 0),
                email_routing=TravelKmEmailRoutingRequest(
                    reporting_manager_email="manager@nakshatech.com",
                    to_emails=["hr@nakshatech.com", "admin@nakshatech.com"],
                    cc_emails=["management@nakshatech.com"],
                ),
            ),
        )
        assert claim.status == "draft"
        assert claim.email_routing is not None
        assert "manager@nakshatech.com" in claim.email_routing.to_emails_json

        claim = finish_journey(
            db,
            claim=claim,
            requester=employee,
            payload=TravelKmEndRequest(
                end_km=Decimal("1066.00"),
                end_latitude=12.9816,
                end_longitude=77.6046,
                end_accuracy_m=9.0,
                end_captured_at=datetime(2026, 8, 31, 18, 0, 0),
            ),
        )
        assert float(claim.odometer_km) == 66.0
        assert float(claim.calculated_allowance) == 330.0
        assert float(claim.rate_per_km) == 5.0

        for phase, lat, lon, captured in (
            ("start", 12.9716, 77.5946, datetime(2026, 8, 31, 8, 0, 0)),
            ("end", 12.9816, 77.6046, datetime(2026, 8, 31, 18, 0, 0)),
        ):
            db.add(
                TravelKmAttachment(
                    claim_id=claim.id,
                    phase=phase,
                    uploaded_by_id=employee.id,
                    original_filename=f"{phase}.jpg",
                    storage_key=f"travel-km/test/{claim.id}/{phase}.jpg",
                    mime_type="image/jpeg",
                    file_size=100,
                    content_sha256=("a" if phase == "start" else "b") * 64,
                    device_latitude=lat,
                    device_longitude=lon,
                    device_accuracy_m=8.0,
                    device_captured_at=captured,
                    exif_gps_present=False,
                    verification_flag="live_gps_captured",
                )
            )
        db.commit()
        db.refresh(claim)

        claim = submit_claim(db, claim=claim, requester=employee)
        assert claim.status == "submitted"
        snapshot = db.query(TravelKmVerificationSnapshot).filter_by(claim_id=claim.id).one()
        assert snapshot.score >= 0
        assert snapshot.outcome in {"verified", "review", "needs_review", "high_variance", "insufficient_gps"}

        claim = admin_decision(
            db,
            claim=claim,
            actor=admin,
            payload=TravelKmDecisionRequest(
                action="approve",
                eligible_km=Decimal("65.00"),
                comments="One KM excluded after odometer/GPS verification.",
            ),
        )
        assert claim.status == "admin_approved"
        assert float(claim.admin_eligible_km) == 65.0

        try:
            hr_decision(
                db,
                claim=claim,
                actor=hr,
                payload=TravelKmDecisionRequest(action="approve", eligible_km=Decimal("66.00"), comments="Too high"),
            )
            raise AssertionError("HR must not be able to exceed the Admin verified KM")
        except ValueError as exc:
            assert "cannot exceed" in str(exc)

        claim = hr_decision(
            db,
            claim=claim,
            actor=hr,
            payload=TravelKmDecisionRequest(
                action="approve",
                eligible_km=Decimal("64.00"),
                comments="HR policy verification excludes one additional KM.",
            ),
        )
        assert claim.status == "hr_approved"
        assert float(claim.final_allowance) == 320.0

        management_view = claim_payload(db, claim, viewer=management, effective_role="management")
        assert management_view["permissions"]["read_only_management"] is True
        assert management_view["permissions"]["can_admin_decide"] is False
        assert management_view["permissions"]["can_hr_decide"] is False
        assert len(management_view["attachments"]) == 2
        assert len(management_view["events"]) >= 5

        claim = finance_decision(
            db,
            claim=claim,
            actor=finance,
            payload=TravelKmFinanceDecisionRequest(
                action="approve",
                comments="Approved for monthly salary addition.",
            ),
        )
        assert claim.status == "finance_approved"
        assert claim.paid_amount is None
        assert claim.payment_reference is None
        assert claim.payment_mode is None
        assert claim.paid_at is None
        assert claim.finance_decision_at is not None
        assert len(claim.events) >= 6

        employee_final = claim_payload(db, claim, viewer=employee, effective_role="employee")
        assert employee_final["status"] == "finance_approved"
        management_final = claim_payload(db, claim, viewer=management, effective_role="management")
        assert management_final["status"] == "finance_approved"
        summary = dashboard_payload(db, viewer=management, effective_role="management")
        assert summary["finance_approved_count"] == 1
        assert summary["salary_approved_amount"] == 320.0
        assert summary["paid_amount"] == 0.0

        workbook = build_travel_km_workbook(db, viewer=management, effective_role="management")
        assert workbook.getbuffer().nbytes > 1000
    finally:
        db.close()
