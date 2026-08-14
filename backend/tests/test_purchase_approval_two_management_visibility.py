from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.batch4.router import (
    management_control_center_endpoint,
    management_purchase_approval_decision,
)
from app.modules.batch4.schemas import ManagementPurchaseDecision
from app.modules.it_activity.approval_email import (
    email_logs_for_request,
    issue_purchase_approval_email,
)
from app.modules.it_activity.models import ITPurchaseRequest
from app.modules.it_activity.schemas import PurchaseRequestCreate
from app.modules.it_activity.service import create_purchase_request


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


def _purchase_request(db, it_user: User) -> ITPurchaseRequest:
    return create_purchase_request(
        db,
        PurchaseRequestCreate(
            reporting_month="2026-08",
            requesting_department="IT",
            requested_employee="UAT Two Manager Visibility",
            item_type="hardware",
            item_name="UAT Dual Management Approval",
            item_description="Regression for one selected email and shared Management visibility",
            quantity=1,
            estimated_unit_price=100,
            estimated_total_amount=100,
            business_reason="Controlled UAT only - do not purchase",
            required_by_date=date(2026, 8, 31),
            priority="medium",
            it_remarks="Verify one email recipient and both Management dashboards",
        ),
        it_user,
    )


def _request_item(control_center: dict, request_id: int) -> dict:
    return next(item for item in control_center["purchase_requests"] if item["id"] == request_id)


def test_selected_email_approval_is_visible_to_both_management_users_and_first_decision_wins(
    approval_email_settings,
):
    with SessionLocal() as db:
        it_user = _user(db, "two-manager-it@nakshatech.com", "it", "Two Manager IT")
        chethan = _user(db, "chethan.uat@nakshatech.com", "management", "Chethan UAT")
        vinod = _user(db, "vinod.uat@nakshatech.com", "management", "Vinod UAT")
        request = _purchase_request(db, it_user)
        issued = issue_purchase_approval_email(
            db,
            request,
            chethan.full_name,
            chethan.email,
        )
        request_id = request.id
        token = issued.raw_token

        requested_logs = [
            row for row in email_logs_for_request(db, request_id)
            if row.event_type == "approval_requested"
        ]
        assert len(requested_logs) == 1
        assert requested_logs[0].recipient_email == chethan.email
        assert all(row.recipient_email != vinod.email for row in requested_logs)

    client = TestClient(app)
    email_decision = client.post(
        f"/api/it-activity/purchase-approval-email/{token}",
        data={
            "action": "approve",
            "approved_amount": "100",
            "management_remarks": "Approved by selected Management email",
        },
    )
    assert email_decision.status_code == 200
    assert "recorded successfully" in email_decision.text

    with SessionLocal() as db:
        request = db.get(ITPurchaseRequest, request_id)
        assert request is not None
        assert request.status == "approved"
        assert request.decided_by_name == "Chethan UAT"
        assert request.decided_by_email == "chethan.uat@nakshatech.com"

        chethan = db.scalar(select(User).where(User.email == "chethan.uat@nakshatech.com"))
        vinod = db.scalar(select(User).where(User.email == "vinod.uat@nakshatech.com"))
        assert chethan is not None
        assert vinod is not None

        chethan_view = management_control_center_endpoint("2026-08", db, chethan)
        vinod_view = management_control_center_endpoint("2026-08", db, vinod)

        chethan_item = _request_item(chethan_view, request_id)
        vinod_item = _request_item(vinod_view, request_id)
        assert chethan_item["status"] == "approved"
        assert vinod_item["status"] == "approved"
        assert chethan_item["decided_by"] == "Chethan UAT"
        assert vinod_item["decided_by"] == "Chethan UAT"
        assert chethan_view["purchase_summary"]["pending_approval"] == 0
        assert vinod_view["purchase_summary"]["pending_approval"] == 0
        assert chethan_view["purchase_summary"]["approved"] == 1
        assert vinod_view["purchase_summary"]["approved"] == 1

        with pytest.raises(HTTPException):
            management_purchase_approval_decision(
                "purchase_request",
                request_id,
                ManagementPurchaseDecision(
                    action="reject",
                    remarks="Must not override Chethan approval",
                ),
                db,
                vinod,
            )

        db.refresh(request)
        assert request.status == "approved"
        assert request.decided_by_name == "Chethan UAT"
        assert request.decided_by_email == "chethan.uat@nakshatech.com"
