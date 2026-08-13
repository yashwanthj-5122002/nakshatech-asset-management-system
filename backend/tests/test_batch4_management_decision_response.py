from __future__ import annotations

import json

from app.core.database import Base, SessionLocal, engine
from app.models.entities import User
from app.modules.batch4.router import management_purchase_approval_decision
from app.modules.batch4.schemas import ManagementPurchaseDecision
from app.modules.it_activity.models import ITPurchaseRequest


def _user(db, *, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test",
        role=role,
        branch="Head Office",
        department="Management" if role == "management" else "IT",
        email_verified=True,
        is_active=True,
        account_status="active",
    )
    db.add(row)
    db.flush()
    return row


def test_management_purchase_approval_returns_json_safe_history_payload() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        requester = _user(
            db,
            email="batch4-response-it@nakshatech.com",
            role="it",
            name="Batch 4 Response IT",
        )
        manager = _user(
            db,
            email="batch4-response-manager@nakshatech.com",
            role="management",
            name="Batch 4 Response Manager",
        )

        request = ITPurchaseRequest(
            request_code="ITPR-B4-RESPONSE-001",
            requesting_department="IT",
            requested_employee="QA Employee",
            item_type="hardware",
            item_name="QA Laptop",
            quantity=1,
            estimated_unit_price=75000,
            estimated_total_amount=75000,
            business_reason="Verify Management approval response serialization",
            priority="medium",
            status="pending_approval",
            branch="Head Office",
            requested_by_user_id=requester.id,
            requested_by_name=requester.full_name,
            requested_by_email=requester.email,
            requested_by_role=requester.role,
        )
        db.add(request)
        db.commit()
        db.refresh(request)

        result = management_purchase_approval_decision(
            "purchase_request",
            request.id,
            ManagementPurchaseDecision(
                action="approve",
                remarks="Approved during response serialization QA",
                approved_amount=74000,
            ),
            db,
            manager,
        )

        assert result["status"] == "approved"
        assert result["approved_amount"] == 74000
        assert result["decided_by_name"] == manager.full_name
        assert result["histories"]
        assert all(isinstance(item, dict) for item in result["histories"])
        assert any(item["to_status"] == "approved" for item in result["histories"])

        # This is the important browser-facing regression: the post-commit
        # response must already be JSON-safe and must not fail after the DB
        # decision has been persisted.
        encoded = json.dumps(result)
        assert '"status": "approved"' in encoded
