from __future__ import annotations

from datetime import date, datetime
import os
from pathlib import Path
import sys
import tempfile
import uuid

import pytest
from fastapi import HTTPException
from fastapi.routing import iter_route_contexts
from pydantic import ValidationError

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
from app.models.entities import Asset, AssetHistory, ReplacementRecord, User, WorkRecord  # noqa: E402
from app.modules.batch3.purchase_completion import create_purchase_record_batch3  # noqa: E402
from app.modules.batch4.it_control import (  # noqa: E402
    create_replacement_without_management_approval,
    resubmit_legacy_replacement_as_it_controlled,
    update_work_without_management_approval,
)
from app.modules.batch4.router import management_purchase_approval_decision  # noqa: E402
from app.modules.batch4.schemas import ManagementPurchaseDecision  # noqa: E402
from app.modules.batch4.service import build_management_control_workbook, management_control_center  # noqa: E402
from app.modules.it_activity.models import ITPurchaseRequest  # noqa: E402
from app.modules.it_activity.schemas import HandoverCreate, PurchaseCreate  # noqa: E402
from app.modules.it_activity.service import create_handover_record  # noqa: E402
from app.modules.notifications.models import GlobalNotification  # noqa: E402
from app.schemas.replacement import ReplacementCreate, ReplacementResubmit  # noqa: E402
from app.schemas.work import WorkRecordUpdate  # noqa: E402
from app.services.asset_lifecycle_service import inventory_summary  # noqa: E402


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


def _matching_route_contexts(path: str, method: str):
    method = method.upper()
    return [
        context
        for context in iter_route_contexts(app.router.routes)
        if context.path == path and method in (context.methods or set())
    ]


def _assert_authoritative_route(path: str, method: str, endpoint_name: str) -> None:
    matches = _matching_route_contexts(path, method)
    assert len(matches) == 1, f"Expected one effective {method} {path} route, found {len(matches)}"
    endpoint = matches[0].endpoint
    assert endpoint is not None
    assert endpoint.__name__ == endpoint_name


def test_batch4_final_purchase_only_management_authority():
    Base.metadata.create_all(bind=engine)
    month = datetime.now().strftime("%Y-%m")
    try:
        with SessionLocal() as db:
            it_user = _user(db, "batch4-it@nakshatech.com", "it", "Batch 4 IT")
            manager = _user(db, "batch4-manager@nakshatech.com", "management", "Batch 4 Manager")

            # FastAPI 0.137+ uses nested router trees. Validate the effective
            # runtime routes, not the internal top-level route representation.
            # Each superseded operation must resolve exactly once to Batch 4.
            _assert_authoritative_route("/api/replacements", "POST", "create_replacement_batch4")
            _assert_authoritative_route(
                "/api/replacements/{replacement_id}", "PATCH", "process_legacy_replacement_batch4"
            )
            _assert_authoritative_route(
                "/api/replacements/{replacement_id}/resubmit", "PUT", "resubmit_legacy_replacement_batch4"
            )
            _assert_authoritative_route(
                "/api/work-records/{work_id}", "PATCH", "update_work_record_batch4"
            )
            _assert_authoritative_route(
                "/api/work-records/{work_id}/decision", "POST", "disabled_it_work_management_decision"
            )
            _assert_authoritative_route(
                "/api/management/approvals/{workflow}/{record_id}/decision",
                "POST",
                "management_purchase_approval_decision",
            )

            # Live custody is deliberately narrow. Historical imports may still
            # preserve older labels, but new software entries must be linked to
            # one Asset Register row and may only Handover, Transfer or Return.
            with pytest.raises(ValidationError):
                HandoverCreate(
                    asset_id=1,
                    device_category="desktop",
                    action_type="hire",
                    activity_date=date.today(),
                )
            with pytest.raises(ValidationError):
                HandoverCreate(
                    asset_id=1,
                    device_category="desktop",
                    action_type="return",
                    return_status="repair",
                    activity_date=date.today(),
                )
            with pytest.raises(ValidationError):
                HandoverCreate(
                    device_category="desktop",
                    action_type="handover",
                    activity_date=date.today(),
                )
            with pytest.raises(ValidationError):
                HandoverCreate(
                    asset_id=1,
                    device_category="desktop",
                    action_type="handover",
                    apply_to_asset=False,
                    activity_date=date.today(),
                )

            # Real custody lifecycle: Available -> Employee A -> Employee B ->
            # Available -> Employee A again. The physical asset total never
            # changes, while Assigned/Available reconcile on every movement.
            custody_asset = _asset(db, "B4-CUSTODY-001", "Computer", "available")
            db.commit()
            initial_inventory = inventory_summary([db.get(Asset, custody_asset.id)])
            assert initial_inventory["total"] == 1
            assert initial_inventory["assigned"] == 0
            assert initial_inventory["available"] == 1

            create_handover_record(
                db,
                HandoverCreate(
                    reporting_month=month,
                    asset_id=custody_asset.id,
                    device_category="desktop",
                    employee_name="QA Old Employee",
                    dc_number="QA-WS-OLD-001",
                    department="GIS / Mobile Mapping",
                    work_mode="office",
                    internal_asset_no=custody_asset.cpu_asset_tag,
                    action_type="handover",
                    activity_date=date.today(),
                    remarks="Initial QA handover",
                ),
                it_user,
            )
            assigned_a = db.get(Asset, custody_asset.id)
            assert assigned_a.status == "assigned"
            assert assigned_a.used_by == "QA Old Employee"
            after_handover = inventory_summary([assigned_a])
            assert after_handover["total"] == 1
            assert after_handover["assigned"] == 1
            assert after_handover["available"] == 0

            create_handover_record(
                db,
                HandoverCreate(
                    reporting_month=month,
                    asset_id=custody_asset.id,
                    device_category="desktop",
                    employee_name="QA New Joiner B",
                    dc_number="QA-WS-NEW-B-001",
                    department="GIS / Mobile Mapping",
                    work_mode="office",
                    internal_asset_no=custody_asset.cpu_asset_tag,
                    action_type="transfer",
                    activity_date=date.today(),
                    remarks="Direct employee transfer QA",
                ),
                it_user,
            )
            assigned_b = db.get(Asset, custody_asset.id)
            assert assigned_b.status == "assigned"
            assert assigned_b.used_by == "QA New Joiner B"
            after_transfer = inventory_summary([assigned_b])
            assert after_transfer["total"] == 1
            assert after_transfer["assigned"] == 1
            assert after_transfer["available"] == 0

            create_handover_record(
                db,
                HandoverCreate(
                    reporting_month=month,
                    asset_id=custody_asset.id,
                    device_category="desktop",
                    employee_name="QA New Joiner B",
                    dc_number="QA-WS-NEW-B-001",
                    department="GIS / Mobile Mapping",
                    work_mode="office",
                    internal_asset_no=custody_asset.cpu_asset_tag,
                    action_type="return",
                    return_status="available",
                    activity_date=date.today(),
                    remarks="Employee returned asset to IT",
                ),
                it_user,
            )
            returned = db.get(Asset, custody_asset.id)
            assert returned.status == "available"
            assert returned.used_by is None
            assert returned.workstation_no is None
            after_return = inventory_summary([returned])
            assert after_return["total"] == 1
            assert after_return["assigned"] == 0
            assert after_return["available"] == 1

            create_handover_record(
                db,
                HandoverCreate(
                    reporting_month=month,
                    asset_id=custody_asset.id,
                    device_category="desktop",
                    employee_name="QA Old Employee",
                    dc_number="QA-WS-OLD-002",
                    department="GIS / Mobile Mapping",
                    work_mode="office",
                    internal_asset_no=custody_asset.cpu_asset_tag,
                    action_type="handover",
                    activity_date=date.today(),
                    remarks="Same returned asset reissued QA",
                ),
                it_user,
            )
            reissued = db.get(Asset, custody_asset.id)
            assert reissued.status == "assigned"
            assert reissued.used_by == "QA Old Employee"
            assert reissued.workstation_no == "QA-WS-OLD-002"
            after_reissue = inventory_summary([reissued])
            assert after_reissue["total"] == 1
            assert after_reissue["assigned"] == 1
            assert after_reissue["available"] == 0

            custody_history = list(db.query(AssetHistory).filter(
                AssetHistory.asset_id == custody_asset.id,
                AssetHistory.change_type.like("handover_%"),
            ).order_by(AssetHistory.id.asc()).all())
            assert [row.change_type for row in custody_history] == [
                "handover_handover",
                "handover_transfer",
                "handover_return",
                "handover_handover",
            ]

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

            # Management Control keeps the full Purchase Request lifecycle
            # visible, while only pending requests appear in the actionable queue.
            center = management_control_center(db, month)
            assert center["authority_model"] == "purchase_approval_only"
            assert center["executive"]["pending_approvals"] == 1
            assert center["executive"]["pending_purchase_requests"] == 1
            assert {item["workflow"] for item in center["approvals"]} == {"purchase_request"}
            assert center["purchase_summary"]["pending_approval"] == 1
            assert center["purchase_summary"]["approved"] == 0
            assert len(center["purchase_requests"]) == 1
            assert center["purchase_requests"][0]["status"] == "pending_approval"

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
            assert refreshed["approvals"] == []
            assert refreshed["purchase_summary"]["pending_approval"] == 0
            assert refreshed["purchase_summary"]["approved"] == 1
            assert refreshed["purchase_summary"]["approved_purchase_value"] == 48000
            assert len(refreshed["purchase_requests"]) == 1
            assert refreshed["purchase_requests"][0]["status"] == "approved"
            assert refreshed["purchase_requests"][0]["approved_amount"] == 48000

            # IT completes the approved procurement using an Available matching
            # Smartphone. The same Management Purchase Request remains visible
            # as Purchase Completed, and the linked replacement is finalized.
            purchased_phone = _asset(db, "B4-NEW-MOB", "Smartphone", "available")
            db.commit()
            purchase_record = create_purchase_record_batch3(
                db,
                PurchaseCreate(
                    reporting_month=month,
                    purchase_request_id=request.id,
                    linked_asset_id=purchased_phone.id,
                    purchase_date=date.today(),
                    po_number="QA-PO-B4-001",
                    asset_number=purchased_phone.cpu_asset_tag,
                    supplier_name="QA Supplier",
                    item_description="Replacement Smartphone",
                    quantity=1,
                    unit_price=48000,
                    total_price=48000,
                    received_date=date.today(),
                    inspection_status="Passed",
                    department="IT",
                    remarks="Batch 4 procurement lifecycle QA",
                ),
                it_user,
            )
            assert purchase_record.purchase_request_id == request.id
            assert db.get(ITPurchaseRequest, request.id).status == "purchase_completed"
            assert db.get(Asset, old_phone.id).status == "replaced"
            allocated_phone = db.get(Asset, purchased_phone.id)
            assert allocated_phone.status == "assigned"
            assert allocated_phone.used_by == "Phone Employee"

            completed_center = management_control_center(db, month)
            assert completed_center["executive"]["pending_purchase_requests"] == 0
            assert completed_center["purchase_summary"]["pending_approval"] == 0
            assert completed_center["purchase_summary"]["approved"] == 0
            assert completed_center["purchase_summary"]["purchase_completed"] == 1
            assert completed_center["purchase_summary"]["approved_purchase_value"] == 48000
            assert len(completed_center["purchase_requests"]) == 1
            completed_request = completed_center["purchase_requests"][0]
            assert completed_request["status"] == "purchase_completed"
            assert completed_request["purchase_code"] == purchase_record.purchase_code
            assert completed_request["actual_purchase_amount"] == 48000
    finally:
        engine.dispose()
        TEST_DB.unlink(missing_ok=True)
