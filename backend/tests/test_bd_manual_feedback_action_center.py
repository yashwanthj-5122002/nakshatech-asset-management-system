"""V8.1 BD Feedback Action Center: manual/offline client feedback recording.

BD must be able to record a client outcome that arrived offline (call, email or
letter) when the client never responds through the secure portal link. The
manual response reuses the exact same transitions as a portal response:

- positive  -> CLIENT_ACCEPTANCE_PENDING_BD -> confirm_client_acceptance -> READY_FOR_BILLING
- negative  -> FEEDBACK_NEGATIVE -> classify_feedback_response -> rework / change request

No competing transition is introduced, and the portal path is untouched.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.operations.lifecycle_models import ProjectFeedbackRequest, ProjectFeedbackResponse
from app.modules.operations.lifecycle_schemas import (
    FeedbackClassification,
    FeedbackRequestCreate,
    ManualFeedbackResponseCreate,
)
from app.modules.operations.lifecycle_service import (
    AWAITING_CLIENT_FEEDBACK,
    CLIENT_ACCEPTANCE_PENDING_BD,
    CLIENT_ACCEPTED,
    FEEDBACK_NEGATIVE,
    FEEDBACK_NOT_SENT,
    READY_FOR_BILLING,
    REWORK_OPEN,
    classify_feedback_response,
    confirm_client_acceptance,
    create_feedback_request,
    record_manual_feedback_response,
)
from app.modules.operations.models import ProjectWorkflow


def _user(db, email: str, role: str) -> User:
    row = User(
        email=email,
        full_name=email.split("@", 1)[0],
        password_hash="test-only",
        role=role,
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _feedback_project(db, suffix: str, status: str = FEEDBACK_NOT_SENT):
    bd = _user(db, f"bd.manual.{suffix}@nakshatech.com", "bd")
    intruder = _user(db, f"prod.manual.{suffix}@nakshatech.com", "production")
    client = FinanceClient(
        client_code=f"MAN-{suffix}",
        client_name=f"Manual Feedback Client {suffix}",
        client_email=f"client.manual.{suffix}@example.com",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        source_team="bd",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=bd.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"MAN-P-{suffix}",
        project_name=f"Manual Feedback Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date.today() - timedelta(days=30),
        end_date=date.today(),
        created_by_id=bd.id,
    )
    db.add(project)
    db.flush()
    workflow = ProjectWorkflow(
        project_id=project.id,
        bd_owner_user_id=bd.id,
        performing_department_code="lidar",
        status=status,
        commercial_value=Decimal("25000"),
        currency="INR",
        created_by_id=bd.id,
        updated_by_id=bd.id,
    )
    db.add(workflow)
    db.flush()
    return bd, intruder, project, workflow


def test_manual_positive_feedback_reaches_ready_for_billing():
    with SessionLocal() as db:
        bd, _, project, workflow = _feedback_project(db, "POS")
        response = record_manual_feedback_response(
            db,
            actor=bd,
            project_id=project.id,
            payload=ManualFeedbackResponseCreate(
                response_type="accepted",
                comments="Client confirmed acceptance over phone on 2026-10-06",
                client_name="Mr. Rao",
                reference="call 2026-10-06",
            ),
        )
        db.flush()
        assert response.source == "bd_manual"
        assert response.feedback_request_id is None
        assert response.classification_status == "pending_bd"
        assert workflow.status == CLIENT_ACCEPTANCE_PENDING_BD

        # Reuse the existing BD confirmation transition (no new transition path).
        confirm_client_acceptance(db, actor=bd, response_id=response.id)
        db.flush()
        assert workflow.status == READY_FOR_BILLING
        assert response.classification_status == "confirmed"
        assert response.classified_as == "accepted"
        db.rollback()


def test_manual_negative_feedback_reuses_classification_and_rework():
    with SessionLocal() as db:
        bd, _, project, workflow = _feedback_project(db, "NEG")
        response = record_manual_feedback_response(
            db,
            actor=bd,
            project_id=project.id,
            payload=ManualFeedbackResponseCreate(
                response_type="correction",
                comments="Client emailed that the boundary layer is misaligned",
                correction_description="Fix the boundary layer alignment in the final tiles",
                client_name="Mr. Rao",
                reference="email 2026-10-06",
            ),
        )
        db.flush()
        assert response.source == "bd_manual"
        assert workflow.status == FEEDBACK_NEGATIVE

        # Reuse the existing BD classification transition -> correction rework.
        rework = classify_feedback_response(
            db,
            actor=bd,
            response_id=response.id,
            payload=FeedbackClassification(classification="correction", remarks="Confirmed correction from client email"),
        )
        db.flush()
        assert workflow.status == REWORK_OPEN
        assert rework.source_feedback_response_id == response.id
        assert response.classification_status == "confirmed"
        db.rollback()


def test_manual_feedback_requires_bd_owner_and_feedback_stage():
    with SessionLocal() as db:
        bd, intruder, project, workflow = _feedback_project(db, "GUARD")
        # A non-BD employee cannot record a manual client outcome.
        with pytest.raises(PermissionError):
            record_manual_feedback_response(
                db,
                actor=intruder,
                project_id=project.id,
                payload=ManualFeedbackResponseCreate(response_type="accepted", comments="Not allowed"),
            )
        # A BD user who does not own the project cannot record it either.
        other_bd = _user(db, "bd.other.manual@nakshatech.com", "bd")
        with pytest.raises(PermissionError):
            record_manual_feedback_response(
                db,
                actor=other_bd,
                project_id=project.id,
                payload=ManualFeedbackResponseCreate(response_type="accepted", comments="Not my project"),
            )
        # The project must still be in the client feedback stage.
        workflow.status = READY_FOR_BILLING
        db.flush()
        with pytest.raises(ValueError, match="cannot be recorded while project is READY_FOR_BILLING"):
            record_manual_feedback_response(
                db,
                actor=bd,
                project_id=project.id,
                payload=ManualFeedbackResponseCreate(response_type="accepted", comments="Too late"),
            )
        db.rollback()


def test_manual_feedback_allowed_after_request_sent_and_does_not_close_request():
    with SessionLocal() as db:
        bd, _, project, workflow = _feedback_project(db, "AWAIT")
        _, _, _ = create_feedback_request(
            db,
            actor=bd,
            project_id=project.id,
            payload=FeedbackRequestCreate(message="Please confirm delivery", expiry_days=14),
        )
        db.flush()
        assert workflow.status == AWAITING_CLIENT_FEEDBACK
        response = record_manual_feedback_response(
            db,
            actor=bd,
            project_id=project.id,
            payload=ManualFeedbackResponseCreate(
                response_type="accepted",
                comments="Client accepted by email before using the portal link",
                reference="client email 2026-10-05",
            ),
        )
        db.flush()
        assert workflow.status == CLIENT_ACCEPTANCE_PENDING_BD
        # The portal request row is untouched: original external records preserved.
        request_row = db.scalar(
            select(ProjectFeedbackRequest).where(ProjectFeedbackRequest.project_id == project.id)
        )
        assert request_row is not None
        assert request_row.status == "sent"
        assert request_row.responded_at is None
        assert response.feedback_request_id is None
        assert response.source == "bd_manual"
        db.rollback()
