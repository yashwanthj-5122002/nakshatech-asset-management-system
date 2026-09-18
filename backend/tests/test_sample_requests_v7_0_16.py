from __future__ import annotations

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import BDOpportunity
from app.modules.operations.sample_models import TechnicalSampleDepartment, TechnicalSampleRequest
from app.modules.operations.sample_schemas import (
    TechnicalSampleClientDecision,
    TechnicalSampleRequestCreate,
    TechnicalSampleSubmit,
)
from app.modules.operations.sample_service import (
    DEMO_DEPARTMENT_EMAILS,
    DEMO_EMPLOYEE_IDS,
    create_finance_client_approved_notifications,
    create_sample_request,
    create_sample_team_notifications,
    record_sample_client_decision,
    send_sample_to_client_review,
    start_sample_department,
    submit_sample_department,
)

DEMO_PASSWORD_HASH = "test-only-unused-hash"


def add_user(db, *, email: str, role: str, employee_id: str, full_name: str | None = None) -> User:
    user = User(
        email=email,
        full_name=full_name or email.split("@", 1)[0],
        password_hash=DEMO_PASSWORD_HASH,
        role=role,
        branch="Head Office",
        employee_id=employee_id,
        department=role,
        designation="Phase 2 Test",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def add_demo_user(db, department_code: str, role: str) -> User:
    return add_user(
        db,
        email=DEMO_DEPARTMENT_EMAILS[department_code],
        role=role,
        employee_id=DEMO_EMPLOYEE_IDS[department_code],
        full_name=f"{department_code} demo",
    )


def add_opportunity(db, bd: User, suffix: str) -> BDOpportunity:
    row = BDOpportunity(
        opportunity_code=f"BD-SAMPLE-{suffix}",
        title=f"Sample workflow {suffix}",
        client_name_snapshot=f"Demo Client {suffix}",
        requirement="Prepare a technical sample before project creation",
        service_type="multi_department",
        priority="medium",
        stage="opportunity",
        owner_user_id=bd.id,
    )
    db.add(row)
    db.flush()
    return row


def test_sample_request_notifies_only_reserved_demo_technical_accounts():
    with SessionLocal() as db:
        bd = add_user(db, email="bd.phase2@nakshatech.com", role="bd", employee_id="T-BD-1")
        lidar_demo = add_demo_user(db, "lidar", "lidar")
        bim_demo = add_demo_user(db, "bim", "bim")
        real_lidar = add_user(db, email="real.lidar@nakshatech.com", role="lidar", employee_id="REAL-LIDAR-1")
        opportunity = add_opportunity(db, bd, "A")

        sample = create_sample_request(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=TechnicalSampleRequestCreate(
                title="LiDAR + BIM sample",
                instructions="Prepare demonstration outputs for client review",
                department_codes=["lidar", "bim"],
            ),
        )
        db.commit()
        created = create_sample_team_notifications(db, sample_request_id=sample.id)
        db.commit()

        assert created == 2
        recipients = set(db.scalars(select(GlobalNotification.recipient_user_id).where(
            GlobalNotification.event_type == "technical.sample.requested"
        )).all())
        assert recipients == {lidar_demo.id, bim_demo.id}
        assert real_lidar.id not in recipients
        assert opportunity.stage == "technical_sample"


def test_unselected_technical_department_cannot_work_on_sample():
    with SessionLocal() as db:
        bd = add_user(db, email="bd.phase2b@nakshatech.com", role="bd", employee_id="T-BD-2")
        lidar_demo = add_demo_user(db, "lidar", "lidar")
        bim_demo = add_demo_user(db, "bim", "bim")
        opportunity = add_opportunity(db, bd, "B")
        sample = create_sample_request(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=TechnicalSampleRequestCreate(
                title="LiDAR-only sample",
                instructions="Prepare LiDAR classification sample",
                department_codes=["lidar"],
            ),
        )
        db.flush()

        start_sample_department(db, sample_request=sample, actor=lidar_demo, effective_role="lidar")
        try:
            start_sample_department(db, sample_request=sample, actor=bim_demo, effective_role="bim")
            raised = False
        except PermissionError:
            raised = True
        assert raised is True


def test_multi_team_submission_revision_and_client_approval_finance_handoff():
    with SessionLocal() as db:
        bd = add_user(db, email="bd.phase2c@nakshatech.com", role="bd", employee_id="T-BD-3")
        lidar = add_demo_user(db, "lidar", "lidar")
        bim = add_demo_user(db, "bim", "bim")
        finance = add_user(db, email="finance.phase2@nakshatech.com", role="finance", employee_id="T-FIN-1")
        opportunity = add_opportunity(db, bd, "C")
        sample = create_sample_request(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=TechnicalSampleRequestCreate(
                title="Combined technical sample",
                instructions="LiDAR output feeds the BIM demonstration",
                department_codes=["lidar", "bim"],
            ),
        )
        db.flush()

        start_sample_department(db, sample_request=sample, actor=lidar, effective_role="lidar")
        submit_sample_department(
            db,
            sample_request=sample,
            actor=lidar,
            effective_role="lidar",
            payload=TechnicalSampleSubmit(sample_reference="DEMO/LIDAR/V1", notes="LiDAR sample v1"),
        )
        start_sample_department(db, sample_request=sample, actor=bim, effective_role="bim")
        submit_sample_department(
            db,
            sample_request=sample,
            actor=bim,
            effective_role="bim",
            payload=TechnicalSampleSubmit(sample_reference="DEMO/BIM/V1", notes="BIM sample v1"),
        )
        assert sample.status == "ready_for_client_review"

        send_sample_to_client_review(db, sample_request=sample, actor=bd)
        assert sample.status == "client_review"
        record_sample_client_decision(
            db,
            sample_request=sample,
            actor=bd,
            payload=TechnicalSampleClientDecision(
                decision="revision",
                feedback="Improve LiDAR roof classification only",
                revision_department_codes=["lidar"],
            ),
        )
        states = {row.department_code: row.status for row in sample.departments}
        assert states == {"lidar": "revision_requested", "bim": "submitted"}
        assert opportunity.stage == "revision"

        start_sample_department(db, sample_request=sample, actor=lidar, effective_role="lidar")
        submit_sample_department(
            db,
            sample_request=sample,
            actor=lidar,
            effective_role="lidar",
            payload=TechnicalSampleSubmit(sample_reference="DEMO/LIDAR/V2", notes="Corrected roof classification"),
        )
        assert sample.status == "ready_for_client_review"
        lidar_row = next(row for row in sample.departments if row.department_code == "lidar")
        assert len(lidar_row.submissions) == 2

        send_sample_to_client_review(db, sample_request=sample, actor=bd)
        record_sample_client_decision(
            db,
            sample_request=sample,
            actor=bd,
            payload=TechnicalSampleClientDecision(decision="approved", feedback="Client approved the sample"),
        )
        db.commit()

        assert sample.status == "client_approved"
        assert opportunity.stage == "finance_handoff"
        assert opportunity.finance_handoff_at is not None
        assert all(row.status == "client_approved" for row in sample.departments)

        count = create_finance_client_approved_notifications(db, sample_request_id=sample.id)
        db.commit()
        assert count == 1
        notification = db.scalar(select(GlobalNotification).where(
            GlobalNotification.recipient_user_id == finance.id,
            GlobalNotification.event_type == "finance.bd_opportunity.client_approved",
        ))
        assert notification is not None
        assert "Client ID and Project ID" in notification.message
