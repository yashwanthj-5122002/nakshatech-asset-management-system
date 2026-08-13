from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import uuid

import pytest
from sqlalchemy import select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_batch3_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "batch3-test-secret-only-change-me-32-characters"
os.environ["EMAIL_DELIVERY_MODE"] = "console"
os.environ["NAKSHA_COPILOT_ENABLED"] = "false"
os.environ["LOCAL_BACKUP_AGENT_ENABLED"] = "false"

# Import the Batch 3 runtime so all existing and Batch 3 models are registered
# before Base.metadata creates the isolated test database.
from app.batch3_main import app  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.entities import Asset, AssetHistory, ReplacementRecord, User  # noqa: E402
from app.modules.batch3.models import ReplacementWorkflowState  # noqa: E402
from app.modules.batch3.service import (  # noqa: E402
    approve_replacement_batch3,
    complete_monthly_activity_data,
    create_purchase_record_batch3,
    reconciliation_report,
)
from app.modules.it_activity.models import ITPurchaseRequest  # noqa: E402
from app.modules.it_activity.schemas import PurchaseCreate  # noqa: E402


@pytest.fixture(scope="module", autouse=True)
def database():
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()
    TEST_DB.unlink(missing_ok=True)


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test",
        role=role,
        branch="Head Office",
        department="IT" if role == "it" else "Management",
        email_verified=True,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _asset(
    db,
    code: str,
    device_type: str,
    *,
    status: str,
    used_by: str | None = None,
    workstation_no: str | None = None,
) -> Asset:
    row = Asset(
        asset_code=code,
        cpu_asset_tag=f"TAG-{code}",
        device_type=device_type,
        status=status,
        used_by=used_by,
        workstation_no=workstation_no,
        department="IT",
        location="Head Office",
        work_mode="office",
        asset_date=date.today(),
        original_asset_date=date.today(),
    )
    db.add(row)
    db.flush()
    return row


def test_batch3_spare_first_and_procurement_lifecycle():
    month = datetime.now().strftime("%Y-%m")
    with SessionLocal() as db:
        it_user = _user(db, "batch3-it@nakshatech.com", "it", "Batch 3 IT")
        manager = _user(db, "batch3-manager@nakshatech.com", "management", "Batch 3 Manager")

        old_laptop = _asset(
            db, "B3-OLD-LAP", "Laptop", status="replacement_pending",
            used_by="Employee A", workstation_no="WS-B3-01",
        )
        spare_laptop = _asset(db, "B3-SPARE-LAP", "Laptop", status="available")
        request = ReplacementRecord(
            replacement_code="B3-RPL-SPARE",
            old_asset_id=old_laptop.id,
            reason="QA spare-first replacement",
            approval_status="pending",
            final_action="replacement_pending",
            requested_by_user_id=it_user.id,
            requested_by=it_user.full_name,
            requested_by_email=it_user.email,
            requested_by_role=it_user.role,
            reporting_month=month,
        )
        db.add(request)
        db.flush()
        db.add(ReplacementWorkflowState(
            replacement_record_id=request.id,
            previous_asset_status="assigned",
        ))
        db.commit()

        result = approve_replacement_batch3(
            db,
            replacement_id=request.id,
            approval_status="approved",
            selected_new_asset_id=None,
            final_action=None,
            remarks="Use available stock first",
            user=manager,
        )
        db.refresh(old_laptop)
        db.refresh(spare_laptop)
        state = db.scalar(select(ReplacementWorkflowState).where(
            ReplacementWorkflowState.replacement_record_id == result.id
        ))
        assert result.approval_status == "approved"
        assert result.new_asset_id == spare_laptop.id
        assert state is not None and state.procurement_mode == "spare"
        assert state.purchase_request_id is None
        assert old_laptop.status == "replaced"
        assert old_laptop.used_by is None
        assert old_laptop.workstation_no is None
        assert spare_laptop.status == "assigned"
        assert spare_laptop.used_by == "Employee A"
        assert spare_laptop.workstation_no == "WS-B3-01"

        old_phone = _asset(
            db, "B3-OLD-MOB", "Smartphone", status="replacement_pending",
            used_by="Employee B", workstation_no="MOBILE-B3",
        )
        no_spare_request = ReplacementRecord(
            replacement_code="B3-RPL-PURCHASE",
            old_asset_id=old_phone.id,
            reason="QA no-spare replacement",
            approval_status="pending",
            final_action="replacement_pending",
            requested_by_user_id=it_user.id,
            requested_by=it_user.full_name,
            requested_by_email=it_user.email,
            requested_by_role=it_user.role,
            reporting_month=month,
        )
        db.add(no_spare_request)
        db.flush()
        db.add(ReplacementWorkflowState(
            replacement_record_id=no_spare_request.id,
            previous_asset_status="assigned",
        ))
        db.commit()

        approved = approve_replacement_batch3(
            db,
            replacement_id=no_spare_request.id,
            approval_status="approved",
            selected_new_asset_id=None,
            final_action=None,
            remarks="Procure only because no spare exists",
            user=manager,
        )
        db.refresh(old_phone)
        state = db.scalar(select(ReplacementWorkflowState).where(
            ReplacementWorkflowState.replacement_record_id == approved.id
        ))
        assert state is not None
        assert state.procurement_mode == "purchase"
        assert state.purchase_request_id is not None
        assert old_phone.status == "replacement_pending"
        purchase_request = db.get(ITPurchaseRequest, state.purchase_request_id)
        assert purchase_request is not None
        assert purchase_request.status == "pending_approval"
        assert purchase_request.requested_by_user_id == it_user.id

        purchase_request.status = "approved"
        purchase_request.decided_by_name = manager.full_name
        purchase_request.decided_by_user_id = manager.id
        purchase_request.decided_by_email = manager.email
        purchase_request.decided_by_role = manager.role
        db.commit()

        purchased_phone = _asset(db, "B3-NEW-MOB", "Smartphone", status="available")
        db.commit()
        purchase = create_purchase_record_batch3(
            db,
            PurchaseCreate(
                reporting_month=month,
                purchase_request_id=purchase_request.id,
                linked_asset_id=purchased_phone.id,
                purchase_date=date.today(),
                supplier_name="QA Supplier",
                item_description="Smartphone replacement",
                quantity=1,
                unit_price=1000,
                total_price=1000,
                department="IT",
            ),
            it_user,
        )
        db.refresh(old_phone)
        db.refresh(purchased_phone)
        db.refresh(purchase_request)
        db.refresh(approved)
        assert purchase.purchase_request_id == purchase_request.id
        assert purchase_request.status == "purchase_completed"
        assert old_phone.status == "replaced"
        assert old_phone.used_by is None
        assert purchased_phone.status == "assigned"
        assert purchased_phone.used_by == "Employee B"
        assert approved.new_asset_id == purchased_phone.id
        assert approved.final_action == "procurement_completed_replacement"

        history = list(db.scalars(select(AssetHistory).where(
            AssetHistory.asset_id.in_([old_laptop.id, spare_laptop.id, old_phone.id, purchased_phone.id])
        )).all())
        assert any(item.change_type == "replacement_completed_spare" for item in history)
        assert any(item.change_type == "replacement_procurement_required" for item in history)

        activity = complete_monthly_activity_data(db, month, limit=5000)
        action_types = {item["action_type"] for item in activity["items"]}
        assert "asset_replacement_approved" in action_types
        assert "purchase_request_purchase_completed" in action_types

        reconciliation = reconciliation_report(db)
        assert reconciliation["checks"]["device_breakdown_reconciled"] is True
        assert reconciliation["checks"]["lifecycle_breakdown_reconciled"] is True
        assert reconciliation["checks"]["external_hdd_separate"] is True
