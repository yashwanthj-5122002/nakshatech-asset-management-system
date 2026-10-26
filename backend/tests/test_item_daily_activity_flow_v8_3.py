"""Focused tests: file-level Daily Activity flow (Project Operations / My Exact Assigned Work).

Pins the behaviour of the SHARED item-activity workflow used by both Project Operations and
Production Tracking: server-recorded stage timestamps/durations, workflow gates, append-only
history, automatic completed-file counting, Ready-for-Delivery / Delivery gating, PM
operational completion as a separate lifecycle step from Finance closure, and the preserved
legacy (zero-item) Daily Activity.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.operations import production_items as items_service
from app.modules.operations.models import WorkPackageItemActivity
from app.modules.operations.schemas import WorkflowDeliveryRequest, WorkflowFinanceClosure, WorkflowOperationalCompletion
from app.modules.operations.workflow_service import (
    complete_production,
    finance_close_project,
    mark_delivered,
    operational_complete,
    record_daily_activity,
    review_work,
)
from app.modules.operations.schemas import WorkflowDailyActivity, WorkflowReviewRequest
from test_production_file_tracking_v8_2 import make_area, make_user
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS,
    MASTER_ROWS,
    assign_all,
    import_master,
    items_of,
    packages_of,
    run_production,
    run_review,
    setup_project,
    xlsx_bytes,
)

TL_ROLE = "employee"


def _prepare(db, code):
    ctx = setup_project(db, code)
    import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, MASTER_ROWS))
    package = packages_of(db, ctx)[0]
    items = [i for i in items_of(db, ctx) if i.work_package_id == package.id]
    assign_all(db, ctx, package, [i.id for i in items])
    return ctx, package, items


_TEAM_KEY = {"production": "prod", "qc": "qc", "qa": "qa"}


def _start(db, ctx, item, stage, **kw):
    return items_service.start_activity(
        db, actor=ctx["team"][_TEAM_KEY[stage]], role=TL_ROLE, work_package_item_id=item.id, stage=stage, **kw)


def _stop(db, ctx, item, activity, stage, **kw):
    return items_service.stop_activity(
        db, actor=ctx["team"][_TEAM_KEY[stage]], activity_id=activity.id, **kw)


# ===========================================================================================
# timestamps + durations (backend authority)
# ===========================================================================================

def test_production_timestamps_and_duration():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA1")
        item = items[0]
        started = datetime(2026, 10, 13, 9, 35, 12)
        ended = datetime(2026, 10, 13, 11, 8, 47)
        activity = _start(db, ctx, item, "production", started_at=started)
        assert activity.started_at == started
        done = _stop(db, ctx, item, activity, "production", status="completed",
                     quantity_completed=Decimal("1.16"), unit="km", ended_at=ended)
        assert done.ended_at == ended
        assert done.duration_seconds == 5615  # 01:33:35
        assert done.files_completed == 1      # automatic
        row = items_service.build_item_rows(db, [package.id])[0]
        assert row["production_start"].startswith("2026-10-13T09:35:12")
        assert row["production_end"].startswith("2026-10-13T11:08:47")
        assert row["production_duration_seconds"] == 5615
        assert row["production_quantity"] == 1.16
        assert row["production_files"] == 1
        assert row["production_deadline"]["status"] == "completed_on_time"


def test_qc_timestamps_and_duration():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA2")
        item = items[0]
        run_production(db, ctx, item)
        started = datetime(2026, 10, 14, 10, 0, 0)
        ended = datetime(2026, 10, 14, 10, 45, 30)
        activity = _start(db, ctx, item, "qc", started_at=started)
        done = _stop(db, ctx, item, activity, "qc", status="passed", ended_at=ended, remarks="Checked")
        assert done.started_at == started and done.ended_at == ended
        assert done.duration_seconds == 2730  # 00:45:30
        row = items_service.build_item_rows(db, [package.id])[0]
        assert row["qc_duration_seconds"] == 2730 and row["qc_status"] == "passed"
        assert row["qc_deadline"]["status"] == "completed_on_time"


def test_qa_timestamps_and_duration():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA3")
        item = items[0]
        run_production(db, ctx, item)
        run_review(db, ctx, item, "qc", "passed")
        started = datetime(2026, 10, 15, 8, 0, 0)
        ended = datetime(2026, 10, 15, 8, 20, 10)
        activity = _start(db, ctx, item, "qa", started_at=started)
        done = _stop(db, ctx, item, activity, "qa", status="passed", ended_at=ended)
        assert done.duration_seconds == 1210  # 00:20:10
        row = items_service.build_item_rows(db, [package.id])[0]
        assert row["qa_duration_seconds"] == 1210 and row["qa_status"] == "passed"


def test_cross_midnight_duration():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA4")
        item = items[0]
        start = datetime(2026, 10, 13, 22, 30, 0)
        end = datetime(2026, 10, 14, 1, 15, 30)
        activity = _start(db, ctx, item, "production", started_at=start)
        done = _stop(db, ctx, item, activity, "production", status="completed",
                     quantity_completed=Decimal("1"), ended_at=end)
        assert done.duration_seconds == 9930  # 02:45:30 across midnight


# ===========================================================================================
# duplicate start / duplicate complete
# ===========================================================================================

def test_duplicate_start_is_blocked():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA5")
        item = items[0]
        _start(db, ctx, item, "production")
        with pytest.raises(ValueError, match="already have an open"):
            _start(db, ctx, item, "production")


def test_duplicate_complete_does_not_double_count():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA6")
        item = items[0]
        activity = _start(db, ctx, item, "production")
        _stop(db, ctx, item, activity, "production", status="completed",
              quantity_completed=Decimal("1.16"), unit="km")
        with pytest.raises(ValueError, match="already completed"):
            _stop(db, ctx, item, activity, "production", status="completed",
                  quantity_completed=Decimal("1.16"), unit="km")
        rows = items_service.build_item_rows(db, [package.id])
        assert rows[0]["production_files"] == 1
        assert rows[0]["production_quantity"] == 1.16
        assert db.scalar(select(func.count(WorkPackageItemActivity.id)).where(
            WorkPackageItemActivity.work_package_item_id == item.id)) == 1


# ===========================================================================================
# gates
# ===========================================================================================

def test_production_to_qc_gate():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA7")
        item = items[0]
        with pytest.raises(ValueError, match="Production must be completed"):
            _start(db, ctx, item, "qc")
        run_production(db, ctx, item)
        activity = _start(db, ctx, item, "qc")
        assert activity.stage == "qc"


def test_qc_to_qa_gate():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA8")
        item = items[0]
        run_production(db, ctx, item)
        with pytest.raises(ValueError, match="QC must pass"):
            _start(db, ctx, item, "qa")
        run_review(db, ctx, item, "qc", "passed")
        activity = _start(db, ctx, item, "qa")
        assert activity.stage == "qa"


def test_qc_reject_preserves_history_then_pass():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA9")
        item = items[0]
        run_production(db, ctx, item)
        run_review(db, ctx, item, "qc", "rejected", remarks="Misaligned tiles")
        run_review(db, ctx, item, "qc", "passed", remarks="Fixed")
        history = items_service.item_history(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                             work_package_item_id=item.id)
        assert [h["status"] for h in history if h["stage"] == "qc"] == ["rejected", "passed"]
        rows = items_service.build_item_rows(db, [package.id])
        assert rows[0]["qc_status"] == "passed"          # latest attempt
        assert rows[0]["qc_deadline"]["status"] == "completed_on_time"


def test_qa_reject_preserves_history():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA10")
        item = items[0]
        run_production(db, ctx, item)
        run_review(db, ctx, item, "qc", "passed")
        run_review(db, ctx, item, "qa", "rework", remarks="Attributes need correction")
        history = items_service.item_history(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                             work_package_item_id=item.id)
        assert [h["status"] for h in history if h["stage"] == "qa"] == ["rework"]
        assert item.status == "qa_rejected"


# ===========================================================================================
# readiness / delivery
# ===========================================================================================

def test_ready_for_delivery_gate():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA11")
        item = items[0]
        with pytest.raises(ValueError, match="Not all files passed QA"):
            items_service.mark_ready_for_delivery(
                db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=package.id)
        run_production(db, ctx, item)
        run_review(db, ctx, item, "qc", "passed")
        with pytest.raises(ValueError, match="Not all files passed QA"):
            items_service.mark_ready_for_delivery(
                db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=package.id)
        run_review(db, ctx, item, "qa", "passed")
        readiness = items_service.mark_ready_for_delivery(
            db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=package.id)
        assert readiness["ready"] is True and package.ready_for_delivery_at is not None


def test_delivery_gate_and_no_auto_finance():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA12")
        item = items[0]
        run_production(db, ctx, item)
        with pytest.raises(ValueError, match="QA must pass"):
            items_service.deliver_item(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                       work_package_item_id=item.id)
        run_review(db, ctx, item, "qc", "passed")
        run_review(db, ctx, item, "qa", "passed")
        activity = items_service.deliver_item(
            db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_item_id=item.id,
            remarks="Sent to client", reference="DLV-DA12")
        assert activity.status == "delivered"
        rows = items_service.build_item_rows(db, [package.id])
        assert rows[0]["delivery_status"] == "delivered" and rows[0]["delivery_at"] is not None
        # delivery is a technical milestone only — Finance is untouched
        assert ctx["workflow"].finance_closed_at is None
        assert ctx["workflow"].status != "closed"


# ===========================================================================================
# operational completion (PM) vs Finance closure — separate lifecycle steps
# ===========================================================================================

def test_pm_operational_completion_gate_then_finance_is_separate():
    with SessionLocal() as db:
        ctx = make_area(db, code="DA13")
        team = ctx["team"]
        package = ctx["package"]
        # not delivered yet -> PM operational completion blocked by the existing readiness rule
        with pytest.raises(ValueError, match="must be delivered"):
            operational_complete(db, actor=ctx["pm"], project_id=ctx["project"].id,
                                 payload=WorkflowOperationalCompletion(
                                     completion_date=date(2026, 10, 20),
                                     final_delivery_reference="REF-1", remarks="Operational done"))
        # complete the legacy chain, then PM completes the project operationally
        record_daily_activity(db, actor=team["prod"], work_package_id=package.id, payload=WorkflowDailyActivity(
            quantity_completed=Decimal("10"), files_completed=7, status="completed"))
        db.expire(package)  # same-session reload (the app reads across separate request sessions)
        complete_production(db, actor=team["prod"], work_package_id=package.id)
        review_work(db, actor=team["qc"], work_package_id=package.id, kind="qc",
                    payload=WorkflowReviewRequest(decision="approve"))
        review_work(db, actor=team["qa"], work_package_id=package.id, kind="qa",
                    payload=WorkflowReviewRequest(decision="approve"))
        mark_delivered(db, actor=team["tl"], work_package_id=package.id,
                       payload=WorkflowDeliveryRequest(remarks="Legacy delivery"))
        db.flush()
        workflow = operational_complete(
            db, actor=ctx["pm"], project_id=ctx["project"].id,
            payload=WorkflowOperationalCompletion(
                completion_date=date(2026, 10, 20), final_delivery_reference="REF-1",
                remarks="Operational done"))
        assert workflow.operational_completed_at is not None
        assert workflow.completion_date == date(2026, 10, 20)
        assert workflow.final_delivery_reference == "REF-1"
        # Finance closure is a SEPARATE step and must not have happened automatically
        assert workflow.finance_closed_at is None
        assert workflow.status != "closed"
        # and an explicit finance closure still goes through its own service/gate
        with pytest.raises((ValueError, PermissionError)):
            finance_close_project(db, actor=ctx["finance"], project_id=ctx["project"].id,
                                  payload=WorkflowFinanceClosure(remarks="close it"))


# ===========================================================================================
# visibility / permissions
# ===========================================================================================

def test_employee_sees_only_their_item_and_management_is_read_only():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "DA14")
        from app.modules.operations.workflow_service import ortho_dashboard
        row = next(p for p in ortho_dashboard(db, actor=ctx["team"]["prod"], role=TL_ROLE)["projects"]
                   if p["project_id"] == ctx["project"].id)
        assert [i["item_number"] for i in row["packages"][0]["items"]] == [items[0].item_number]
        management = make_user(db, "da.mgmt@nakshatech.com", "management")
        db.flush()
        with pytest.raises(PermissionError, match="read-only"):
            items_service.start_activity(db, actor=management, role="management",
                                         work_package_item_id=items[0].id, stage="production")
        # an unassigned employee cannot mutate the item either
        stranger = make_user(db, "da.stranger@nakshatech.com", "employee", "LiDAR")
        db.flush()
        with pytest.raises(PermissionError):
            items_service.start_activity(db, actor=stranger, role=TL_ROLE,
                                         work_package_item_id=items[0].id, stage="production")


# ===========================================================================================
# legacy zero-item Daily Activity remains
# ===========================================================================================

def test_legacy_daily_activity_still_records_manual_files_completed():
    with SessionLocal() as db:
        ctx = make_area(db, code="DA15")
        team = ctx["team"]
        package = ctx["package"]
        record_daily_activity(db, actor=team["prod"], work_package_id=package.id,
                              payload=WorkflowDailyActivity(
                                  quantity_completed=Decimal("2"), files_completed=7, status="on_track"))
        db.flush()
        db.expire_all()  # same-session reload (the app reads across separate request sessions)
        from app.modules.operations.workflow_service import ortho_dashboard
        row = next(p for p in ortho_dashboard(db, actor=team["tl"], role=TL_ROLE)["projects"]
                   if p["project_id"] == ctx["project"].id)
        payload = row["packages"][0]
        assert payload["has_items"] is False
        assert payload["files_completed"] == 7     # legacy manual count preserved
        assert payload["cumulative_completed"] == 2.0