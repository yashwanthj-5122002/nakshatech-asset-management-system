from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import uuid

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

TEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_batch4_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "batch4-test-secret-only-change-me-32-characters"
os.environ["EMAIL_DELIVERY_MODE"] = "console"
os.environ["NAKSHA_COPILOT_ENABLED"] = "false"
os.environ["LOCAL_BACKUP_AGENT_ENABLED"] = "false"

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.batch4_main import app  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models.entities import Asset, ReplacementRecord, User, WorkRecord  # noqa: E402
from app.modules.batch4.it_control import (  # noqa: E402
    create_replacement_without_management_approval,
    resubmit_legacy_replacement_as_it_controlled,
    update_work_without_management_approval,
)
from app.modules.batch4.router import management_purchase_approval_decision  # noqa: E402
from app.modules.batch4.schemas import ManagementPurchaseDecision  # noqa: E402
from app.modules.batch4.service import build_management_control_workbook, management_control_center  # noqa: E402
from app.modules.it_activity.models import ITPurchaseRequest  # noqa: E402
from app.modules.notifications.models import GlobalNotification  # noqa: E402
from app.schemas.replacement import ReplacementCreate, ReplacementResubmit  # noqa: E402
from app.schemas.work import WorkRecordUpdate  # noqa: E402


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
        account_status="active",
    )
    db.add(row)
    db.flush()
    return row


def _asset(db, code: str, device_type: str, status: str, used_by: str | None = None) -> Asset:
    row = Asset(
        asset_code=code,
        cpu_asset_tag=f"QA-{code}",
        device_type=device_type,
        status=status,
        used_by=used_by,
        workstation_no=f"WS-{code}" if used_by else None,
        department="IT",
        location="Head Office",
        work_mode="office",
        asset_date=date.today(),
        original_asset_date=date.today(),
    )
    db.add(row)
    db.flush()
    return row


def _matching_route_count(path: str, method: str) -> int:
    method = method.upper()
    return sum(
        1
        for route in app.router.routes
        if isinstance(route, APIRoute)
        and route.path == path
        and method in (route.methods or set())
    )


def test_batch4_final_purchase_only_management_authority():
    Base.metadata.create_all(bind=engine)
    month = datetime.now().strftime("%Y-%m")
    try:
        with SessionLocal() as db:
            it_user = _user(db, "batch4-it@nakshatech.com", "it", "Batch 4 IT")
            manager = _user(db, "batch4-manager@nakshatech.com", "management", "Batch 4 Manager")

            # Runtime dispatch must expose one authoritative Batch 4 handler for
            # every superseded Batch 3 route. Duplicate route registration would
            # allow an older approval workflow to win based on route order.
            assert _matching_route_count("/api/replacements", "POST") == 1
            assert _matching_route_count("/api/replacements/{replacement_id}", "PATCH") == 1
            assert _matching_route_count("/api/replacements/{replacement_id}/resubmit", "PUT") == 1
            assert _matching_route_count("/api/work-records/{work_id}", "PATCH") == 1
            assert _matching_route_count("/api/work-records/{work_id}/decision", "POST") == 1

            # IT Work is operational: IT completes it directly and no Management
            # approval state or approval notification is created.
            work_asset = _asset(db, "B4-WORK-001", "Laptop", "assigned", "Batch 4 Employee")
            work = WorkRecord(
                work_code="ITW-B4-001",
                module="it",
                asset_id=work_asset.id,
                title="Batch 4 operational work",
                work_type="Maintenance",
                priority="high",
                issue_description="QA work controlled by IT",
                status="open",
                approval_status="not_required",
                reporting_month=month,
            )
            db.add(work)
            db.commit()

            update_work_without_management_approval(
                db, work.id, WorkRecordUpdate(status="in_progress", reporting_month=month), it_user
            )
            completed = update_work_without_management_approval(
                db,
                work.id,
                WorkRecordUpdate(status="completed", resolution="Resolved by IT", reporting_month=month),
                it_user,
            )
            assert completed["status"] == "completed"
            assert completed["approval_status"] == "not_required"
            assert completed["approved_by_name"] is None
            assert db.query(GlobalNotification).filter(GlobalNotification.event_type.like("approval.it_work.%")).count() == 0

            with pytest.raises(HTTPException) as management_work_edit:
                update_work_without_management_approval(
                    db, work.id, WorkRecordUpdate(status="completed"), manager
                )
            assert management_work_edit.value.status_code == 403

            # Replacement with spare stock is completed directly by IT. No
            # Management approval, approval notification or Purchase Request.
            old_laptop = _asset(db, "B4-OLD-LAP", "Laptop", "assigned", "Laptop Employee")
            spare_laptop = _asset(db, "B4-SPARE-LAP", "Laptop", "available")
            db.commit()
            spare_result = create_replacement_without_management_approval(
                db,
                ReplacementCreate(
                    reporting_month=month,
                    old_asset_id=old_laptop.id,
                    reason="QA spare-first replacement",
                    damage_category="technical_failure",
                    inspection_finding="Motherboard failed",
                ),
                it_user,
            )
            assert spare_result["approval_status"] == "not_required"
            assert spare_result["final_action"] == "replace_with_spare"
            assert spare_result["new_asset_id"] == spare_laptop.id
            assert db.get(Asset, old_laptop.id).status == "replaced"
            assert db.get(Asset, spare_laptop.id).used_by == "Laptop Employee"
            assert db.query(GlobalNotification).filter(GlobalNotification.event_type.like("approval.replacement.%")).count() == 0

            # A returned/pending legacy replacement cannot resubmit itself back
            # into the removed Management approval loop. The backward-compatible
            # PUT path is absorbed into immediate IT processing.
            old_printer = _asset(db, "B4-OLD-PRN", "Printer", "assigned", "Printer Employee")
            spare_printer = _asset(db, "B4-SPARE-PRN", "Printer", "available")
            legacy = ReplacementRecord(
                replacement_code="RPL-B4-LEGACY",
                old_asset_id=old_printer.id,
                reason="Legacy returned replacement",
                damage_category="technical_failure",
                approval_status="returned",
                final_action="replacement_pending",
                requested_by_user_id=it_user.id,
                requested_by=it_user.full_name,
                requested_by_email=it_user.email,
                requested_by_role=it_user.role,
                reporting_month=month,
            )
            old_printer.status = "replacement_pending"
            db.add(legacy)
            db.commit()
            migrated = resubmit_legacy_replacement_as_it_controlled(
                db,
                legacy.id,
                ReplacementResubmit(
                    reporting_month=month,
                    new_asset_id=spare_printer.id,
                    reason="Legacy replacement corrected by IT",
                    damage_category="technical_failure",
                    inspection_finding="Printer main board failed",
                    final_action="replacement_pending",
                ),
                it_user,
            )
            assert migrated["approval_status"] == "not_required"
            assert migrated["final_action"] == "replace_with_spare"
            assert migrated["new_asset_id"] == spare_printer.id

            # No spare means IT creates the technical replacement workflow and
            # the system creates exactly one Purchase Request for Management.
            old_phone = _asset(db, "B4-OLD-MOB", "Smartphone", "assigned", "Phone Employee")
            db.commit()
            purchase_result = create_replacement_without_management_approval(
                db,
                ReplacementCreate(
                    reporting_month=month,
                    old_asset_id=old_phone.id,
                    reason="QA no-spare replacement",
                    damage_category="technical_failure",
                    inspection_finding="Phone failed inspection",
                ),
                it_user,
            )
            assert purchase_result["approval_status"] == "not_required"
            assert purchase_result["final_action"] == "procurement_required"
            requests = list(db.query(ITPurchaseRequest).filter(ITPurchaseRequest.status == "pending_approval").all())
            assert len(requests) == 1
            request = requests[0]
            assert "Management purchase permission is required" in (request.it_remarks or "")
            assert db.query(GlobalNotification).filter(GlobalNotification.event_type == "approval.purchase_request.submitted").count() == 1

            with pytest.raises(HTTPException) as duplicate_replacement:
                create_replacement_without_management_approval(
                    db,
                    ReplacementCreate(
                        reporting_month=month,
                        old_asset_id=old_phone.id,
                        reason="Duplicate QA replacement",
                    ),
                    it_user,
                )
            assert duplicate_replacement.value.status_code == 409

            # Management Control contains only the Purchase Request in its
            # approval queue. IT Work and Replacement stay visible elsewhere,
            # but they are not permission gates.
            center = management_control_center(db, month)
            assert center["authority_model"] == "purchase_approval_only"
            assert center["executive"]["pending_approvals"] == 1
            assert center["executive"]["pending_purchase_requests"] == 1
            assert {item["workflow"] for item in center["approvals"]} == {"purchase_request"}

            with pytest.raises(HTTPException) as forbidden_replacement_decision:
                management_purchase_approval_decision(
                    "replacement",
                    purchase_result["id"],
                    ManagementPurchaseDecision(action="approve", remarks="Should be blocked"),
                    db,
                    manager,
                )
            assert forbidden_replacement_decision.value.status_code == 403

            workbook = build_management_control_workbook(center)
            assert workbook[:2] == b"PK"

            approved = management_purchase_approval_decision(
                "purchase_request",
                request.id,
                ManagementPurchaseDecision(
                    action="approve",
                    remarks="Approved purchase only",
                    approved_amount=48000,
                ),
                db,
                manager,
            )
            assert approved["status"] == "approved"
            assert approved["approved_amount"] == 48000

            refreshed = management_control_center(db, month)
            assert refreshed["executive"]["pending_approvals"] == 0
            assert refreshed["executive"]["pending_purchase_requests"] == 0
    finally:
        engine.dispose()
        TEST_DB.unlink(missing_ok=True)
