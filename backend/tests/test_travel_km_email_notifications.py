from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import json

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.travel_km.emailing import send_submission_email
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
from app.modules.travel_km.schemas import TravelKmClaimCreateRequest, TravelKmEmailRoutingRequest, TravelKmEndRequest
from app.modules.travel_km.service import claim_payload, create_claim, finish_journey, submit_claim


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


def _employee_and_project(db: Session) -> tuple[User, FinanceProject]:
    employee = User(
        email="mail.employee@nakshatech.com",
        full_name="Mail Employee",
        password_hash="test-hash",
        role="employee",
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    project = FinanceProject(
        project_code="MAIL-KM-001",
        project_name="Travel Email QA Project",
        client_name="QA Client",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )
    db.add_all([employee, project])
    db.flush()
    return employee, project


def _claim(db: Session, employee: User, project: FinanceProject) -> TravelKmClaim:
    return create_claim(
        db,
        requester=employee,
        payload=TravelKmClaimCreateRequest(
            project_id=project.id,
            travel_date=date(2026, 9, 1),
            purpose_description="Travel email notification field test",
            start_km=Decimal("100.00"),
            start_latitude=12.9716,
            start_longitude=77.5946,
            start_accuracy_m=6.0,
            start_captured_at=datetime(2026, 9, 1, 9, 0, 0),
            email_routing=TravelKmEmailRoutingRequest(
                reporting_manager_email="Manager@NakshaTech.com",
                to_emails=["hr@nakshatech.com", "manager@nakshatech.com", "admin@nakshatech.com"],
                cc_emails=["vinod@nakshatech.com", "hr@nakshatech.com"],
            ),
        ),
    )


def test_email_routing_normalizes_and_deduplicates_to_and_cc():
    db = _session()
    try:
        employee, project = _employee_and_project(db)
        claim = _claim(db, employee, project)
        assert claim.email_routing is not None
        to_emails = json.loads(claim.email_routing.to_emails_json)
        cc_emails = json.loads(claim.email_routing.cc_emails_json)
        assert to_emails == [
            "manager@nakshatech.com",
            "hr@nakshatech.com",
            "admin@nakshatech.com",
        ]
        assert cc_emails == ["vinod@nakshatech.com"]
    finally:
        db.close()


def test_submission_email_console_mode_is_audited_without_blocking_claim():
    db = _session()
    try:
        employee, project = _employee_and_project(db)
        claim = _claim(db, employee, project)
        claim = finish_journey(
            db,
            claim=claim,
            requester=employee,
            payload=TravelKmEndRequest(
                end_km=Decimal("112.00"),
                end_latitude=12.9816,
                end_longitude=77.6046,
                end_accuracy_m=7.0,
                end_captured_at=datetime(2026, 9, 1, 10, 0, 0),
            ),
        )
        for phase, lat, lon, captured in (
            ("start", 12.9716, 77.5946, datetime(2026, 9, 1, 9, 0, 0)),
            ("end", 12.9816, 77.6046, datetime(2026, 9, 1, 10, 0, 0)),
        ):
            db.add(
                TravelKmAttachment(
                    claim_id=claim.id,
                    phase=phase,
                    uploaded_by_id=employee.id,
                    original_filename=f"{phase}.jpg",
                    storage_key=f"travel-km/mail-test/{claim.id}/{phase}.jpg",
                    mime_type="image/jpeg",
                    file_size=100,
                    content_sha256=("a" if phase == "start" else "b") * 64,
                    device_latitude=lat,
                    device_longitude=lon,
                    device_accuracy_m=7.0,
                    device_captured_at=captured,
                    exif_gps_present=False,
                    verification_flag="live_gps_captured",
                )
            )
        db.commit()
        db.refresh(claim)

        claim = submit_claim(db, claim=claim, requester=employee)
        assert claim.status == "submitted"

        delivery = send_submission_email(
            db,
            claim=claim,
            actor=employee,
            public_base_url="http://localhost:8088",
        )
        db.commit()
        assert delivery.status == "console"
        assert delivery.delivery_mode == "console"
        assert "manager@nakshatech.com" in delivery.to_emails_json
        assert "vinod@nakshatech.com" in delivery.cc_emails_json

        db.refresh(claim)
        payload = claim_payload(db, claim, viewer=employee, effective_role="employee")
        assert payload["email_routing"]["reporting_manager_email"] == "manager@nakshatech.com"
        assert payload["email_history"][-1]["status"] == "console"
        assert payload["status"] == "submitted"
    finally:
        db.close()
