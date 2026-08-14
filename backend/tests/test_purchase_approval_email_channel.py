from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import Asset, User
from app.modules.batch4.it_control import create_replacement_without_management_approval
from app.modules.batch4.router import management_purchase_approval_decision
from app.modules.batch4.schemas import ITReplacementCreate, ManagementPurchaseDecision
from app.modules.it_activity.approval_email import (
    channel_for_request,
    email_logs_for_request,
    issue_purchase_approval_email,
)
from app.modules.it_activity.models import ITPurchaseRequest
from app.modules.it_activity.schemas import PurchaseRequestCreate, PurchaseRequestResubmit
from app.modules.it_activity.service import create_purchase_request, resubmit_purchase_request


@pytest.fixture
def approval_email_settings():
    original_mode = settings.email_delivery_mode
    original_url = settings.purchase_approval_public_url
    original_hours = settings.purchase_approval_email_token_hours
    settings.email_delivery_mode = "console"
    settings.purchase_approval_public_url = "http://testserver"
    settings.purchase_approval_email_token_hours = 72
    try:
        yield
    finally:
        settings.email_delivery_mode = original_mode
        settings.purchase_approval_public_url = original_url
        settings.purchase_approval_email_token_hours = original_hours


def _user(db, email: str, role: str, name: str) -> User:
    user = User(
        email=email,
        full_name=name,
        password_hash="pytest-only-password-hash",
        role=role,
        branch="Head Office",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _purchase_request(db, it_user: User, *, item_name: str = "UAT Laptop") -> ITPurchaseRequest:
    return create_purchase_request(
        db,
        PurchaseRequestCreate(
            reporting_month="2026-08",
            requesting_department="GIS",
            requested_employee="UAT Employee",
            item_type="hardware",
            item_name=item_name,
            item_description="Approval email integration regression",
            quantity=1,
            estimated_unit_price=75000,
            estimated_total_amount=75000,
            business_reason="Required for controlled UAT",
            required_by_date=date(2026, 8, 31),
            priority="high",
            it_remarks="Email approval channel test",
        ),
        it_user,
    )


def test_email_approval_updates_single_purchase_request_and_is_idempotent(approval_email_settings):
    with SessionLocal() as db:
        it_user = _user(db, "approval-it@nakshatech.com", "it", "Approval IT")
        request = _purchase_request(db, it_user)
        issued = issue_purchase_approval_email(
            db,
            request,
            "UAT Approver",
            "uat.approver@nakshatech.com",
        )
        raw_token = issued.raw_token
        assert issued.channel.email_status == "logged"
        assert len(issued.channel.token_hash) == 64
        assert raw_token not in issued.channel.token_hash
        request_id = request.id

    client = TestClient(app)
    review = client.get(f"/api/it-activity/purchase-approval-email/{raw_token}?action=approve")
    assert review.status_code == 200
    assert "Confirm Approve Purchase" in review.text

    with SessionLocal() as db:
        assert db.get(ITPurchaseRequest, request_id).status == "pending_approval"

    decision = client.post(
        f"/api/it-activity/purchase-approval-email/{raw_token}",
        data={
            "action": "approve",
            "approved_amount": "72000",
            "management_remarks": "Approved through UAT email",
        },
    )
    assert decision.status_code == 200
    assert "recorded successfully" in decision.text

    with SessionLocal() as db:
        request = db.get(ITPurchaseRequest, request_id)
        assert request is not None
        assert request.status == "approved"
        assert request.approved_amount == 72000
        assert request.decided_by_name == "UAT Approver"
        assert request.decided_by_email == "uat.approver@nakshatech.com"
        channel = channel_for_request(db, request_id)
        assert channel is not None
        assert channel.decision_source == "email"
        assert channel.token_consumed_at is not None
        logs = email_logs_for_request(db, request_id)
        assert [row.event_type for row in logs] == ["approval_requested", "decision_approved"]
        assert logs[-1].recipient_email == "approval-it@nakshatech.com"

    repeated = client.post(
        f"/api/it-activity/purchase-approval-email/{raw_token}",
        data={"action": "reject", "management_remarks": "Must not override approval"},
    )
    assert repeated.status_code == 200
    assert "already approved" in repeated.text.lower()
    with SessionLocal() as db:
        assert db.get(ITPurchaseRequest, request_id).status == "approved"


def test_email_send_back_requires_remarks_and_resubmission_rotates_token(approval_email_settings):
    with SessionLocal() as db:
        it_user = _user(db, "resubmit-it@nakshatech.com", "it", "Resubmit IT")
        request = _purchase_request(db, it_user, item_name="UAT Software")
        first = issue_purchase_approval_email(
            db,
            request,
            "Test Reviewer",
            "test.reviewer@nakshatech.com",
        )
        first_token = first.raw_token
        request_id = request.id

    client = TestClient(app)
    missing_remarks = client.post(
        f"/api/it-activity/purchase-approval-email/{first_token}",
        data={"action": "send_back", "management_remarks": ""},
    )
    assert missing_remarks.status_code == 400
    with SessionLocal() as db:
        assert db.get(ITPurchaseRequest, request_id).status == "pending_approval"

    sent_back = client.post(
        f"/api/it-activity/purchase-approval-email/{first_token}",
        data={"action": "send_back", "management_remarks": "Revise the amount"},
    )
    assert sent_back.status_code == 200
    with SessionLocal() as db:
        request = db.get(ITPurchaseRequest, request_id)
        assert request is not None
        assert request.status == "sent_back"
        assert request.management_remarks == "Revise the amount"
        it_user = db.scalar(select(User).where(User.email == "resubmit-it@nakshatech.com"))
        assert it_user is not None
        request = resubmit_purchase_request(
            db,
            request.id,
            PurchaseRequestResubmit(
                reporting_month="2026-08",
                requesting_department="GIS",
                requested_employee="UAT Employee",
                item_type="software",
                item_name="UAT Software",
                item_description="Revised request",
                quantity=1,
                estimated_unit_price=50000,
                estimated_total_amount=50000,
                business_reason="Revised controlled UAT",
                required_by_date=date(2026, 8, 31),
                priority="medium",
                it_remarks="Resubmitted after correction",
            ),
            it_user,
        )
        second = issue_purchase_approval_email(
            db,
            request,
            "Test Reviewer",
            "test.reviewer@nakshatech.com",
            resubmitted=True,
        )
        second_token = second.raw_token
        assert second_token != first_token
        assert request.status == "pending_approval"

    old_link = client.get(f"/api/it-activity/purchase-approval-email/{first_token}?action=approve")
    assert old_link.status_code == 404
    new_link = client.get(f"/api/it-activity/purchase-approval-email/{second_token}?action=approve")
    assert new_link.status_code == 200

    with SessionLocal() as db:
        request = db.get(ITPurchaseRequest, request_id)
        assert request is not None
        settings.email_delivery_mode = "disabled-for-test"
        failed = issue_purchase_approval_email(
            db,
            request,
            "Test Reviewer",
            "test.reviewer@nakshatech.com",
        )
        assert failed.channel.email_status == "failed"
        assert failed.channel.email_last_error == "Email delivery is not configured"
        assert db.get(ITPurchaseRequest, request.id).status == "pending_approval"


def test_asset_management_decision_consumes_email_link_and_records_source(approval_email_settings):
    with SessionLocal() as db:
        it_user = _user(db, "app-decision-it@nakshatech.com", "it", "App Decision IT")
        manager = _user(db, "app.manager@nakshatech.com", "management", "App Manager")
        request = _purchase_request(db, it_user, item_name="App Decision Laptop")
        issued = issue_purchase_approval_email(
            db,
            request,
            "Email Recipient",
            "email.recipient@nakshatech.com",
        )
        token = issued.raw_token
        request_id = request.id
        response = management_purchase_approval_decision(
            "purchase_request",
            request.id,
            ManagementPurchaseDecision(
                action="approve",
                remarks="Approved in Asset Management",
                approved_amount=73000,
            ),
            db,
            manager,
        )
        assert response["status"] == "approved"
        channel = channel_for_request(db, request_id)
        assert channel is not None
        assert channel.decision_source == "asset_management"
        assert channel.token_consumed_at is not None

    client = TestClient(app)
    old_email = client.get(f"/api/it-activity/purchase-approval-email/{token}?action=reject")
    assert old_email.status_code == 200
    assert "already approved" in old_email.text.lower()
    with SessionLocal() as db:
        assert db.get(ITPurchaseRequest, request_id).status == "approved"


def test_replacement_procurement_creates_same_email_approval_channel(approval_email_settings):
    with SessionLocal() as db:
        it_user = _user(db, "replacement-it@nakshatech.com", "it", "Replacement IT")
        old_asset = Asset(
            asset_code="EMAIL-RPL-OLD-001",
            cpu_asset_tag="EMAIL-RPL-TAG-001",
            device_type="Laptop",
            status="assigned",
            used_by="Replacement Employee",
            workstation_no="EMAIL-WS-001",
            work_mode="office",
        )
        db.add(old_asset)
        db.commit()
        db.refresh(old_asset)

        result = create_replacement_without_management_approval(
            db,
            ITReplacementCreate(
                reporting_month="2026-08",
                old_asset_id=old_asset.id,
                reason="UAT replacement with no available spare",
                damage_category="technical_failure",
                inspection_finding="Main board failed",
                approval_recipient_name="Replacement Approver",
                approval_recipient_email="replacement.approver@nakshatech.com",
            ),
            it_user,
        )
        assert result["final_action"] == "procurement_required"
        request = db.scalar(select(ITPurchaseRequest).where(ITPurchaseRequest.status == "pending_approval"))
        assert request is not None
        channel = channel_for_request(db, request.id)
        assert channel is not None
        assert channel.approver_name == "Replacement Approver"
        assert channel.approver_email == "replacement.approver@nakshatech.com"
        assert channel.email_status == "logged"
