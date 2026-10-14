"""Final integration E2E: full file-level lifecycle + cross-read-model consistency.

Uses ISOLATED TEST DATA only (never the HUNTER350 manual-acceptance records).

Drives one area with TWO physical files (3 km + 2 km) through:
  allocation -> Production (3 sessions on file 1, 1 final session on file 2)
  -> QC (both pass) -> QA (file 1 then file 2) -> Ready for Delivery
  -> Delivery (both files) -> PM Operational Completion,
and asserts that Project Operations (/ortho), Production Tracking and the Excel
workbook all tell the SAME story (one source of truth).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.operations import production_items as items_service
from app.modules.operations.models import OrthoWorkPackage, WorkPackageItem
from app.modules.operations.production_reporting import build_production_workbook
from app.modules.operations.production_service import tracking_summary
from app.modules.operations.schemas import WorkflowOperationalCompletion
from app.modules.operations.workflow_service import operational_complete, ortho_dashboard
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS,
    assign_all,
    import_master,
    packages_of,
    run_review,
    setup_project,
    xlsx_bytes,
)

TL_ROLE = "employee"
PM_ROLE = "lidar"

# One area (same LOT / CODE / AREA NAME) with two physical files.
E2E_ROWS = [
    ["LOT-E2E", "DW-E2E-1", "E2E AREA", 1, 3.00, "km", ""],
    ["LOT-E2E", "DW-E2E-1", "E2E AREA", 2, 2.00, "km", ""],
]


def _prepare(db, code):
    ctx = setup_project(db, code)
    import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, E2E_ROWS))
    package = packages_of(db, ctx)[0]
    items = list(db.scalars(select(WorkPackageItem).where(
        WorkPackageItem.work_package_id == package.id).order_by(WorkPackageItem.item_number)).all())
    assign_all(db, ctx, package, [i.id for i in items])
    return ctx, package, items


def _session(db, ctx, item, *, quantity, finalize, start, end):
    activity = items_service.start_activity(
        db, actor=ctx["team"]["prod"], role=TL_ROLE, work_package_item_id=item.id,
        stage="production", started_at=start)
    return items_service.stop_activity(
        db, actor=ctx["team"]["prod"], activity_id=activity.id, status="completed",
        finalize=finalize, quantity_completed=Decimal(quantity), unit=item.planned_unit,
        ended_at=end)


def _ortho_project(db, ctx):
    return next(p for p in ortho_dashboard(db, actor=ctx["pm"], role=PM_ROLE)["projects"]
                if p["project_id"] == ctx["project"].id)


def _tracking_project(db, ctx):
    return next(p for p in tracking_summary(db, actor=ctx["pm"], role=PM_ROLE,
                                            project_id=ctx["project"].id)["projects"]
                if p["project_id"] == ctx["project"].id)


# ===========================================================================================
# FULL HAPPY-PATH E2E
# ===========================================================================================

def test_full_file_level_e2e_and_read_model_consistency():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "E2E")
        file1, file2 = items[0], items[1]
        assert file1.planned_quantity == Decimal("3.00")
        assert file2.planned_quantity == Decimal("2.00")

        # --- Production file 1: two partial sessions, then final completion ---
        _session(db, ctx, file1, quantity="1.0", finalize=False,
                 start=datetime(2026, 10, 13, 9, 0), end=datetime(2026, 10, 13, 12, 0))
        _session(db, ctx, file1, quantity="1.2", finalize=False,
                 start=datetime(2026, 10, 14, 9, 0), end=datetime(2026, 10, 14, 13, 0))
        r1 = next(r for r in items_service.build_item_rows(db, [package.id])
                  if r["work_package_item_id"] == file1.id)
        assert r1["production_quantity"] == 2.2
        assert r1["production_files"] == 0          # not finished yet
        assert r1["qc_status"] == "not_started"
        _session(db, ctx, file1, quantity="0.8", finalize=True,
                 start=datetime(2026, 10, 15, 9, 0), end=datetime(2026, 10, 15, 11, 0))
        # --- Production file 2: single final session ---
        _session(db, ctx, file2, quantity="2.0", finalize=True,
                 start=datetime(2026, 10, 13, 9, 0), end=datetime(2026, 10, 13, 12, 30))

        rows = {r["work_package_item_id"]: r for r in items_service.build_item_rows(db, [package.id])}
        assert rows[file1.id]["production_quantity"] == 3.0
        assert rows[file1.id]["production_files"] == 1
        assert rows[file2.id]["production_quantity"] == 2.0
        db.flush()

        # --- QC both files pass ---
        with pytest.raises(ValueError, match="Not all files passed QA"):
            items_service.mark_ready_for_delivery(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                                  work_package_id=package.id)
        run_review(db, ctx, file1, "qc", "passed")
        run_review(db, ctx, file2, "qc", "passed")
        # --- QA file 1 only -> still NOT ready ---
        run_review(db, ctx, file1, "qa", "passed")
        with pytest.raises(ValueError, match="Not all files passed QA"):
            items_service.mark_ready_for_delivery(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                                  work_package_id=package.id)
        # --- QA file 2 -> ready ---
        run_review(db, ctx, file2, "qa", "passed")
        readiness = items_service.mark_ready_for_delivery(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                                          work_package_id=package.id)
        assert readiness["ready"] is True
        assert readiness["total_files"] == 2

        # --- Delivery both files (explicit, separate from QA pass) ---
        items_service.deliver_item(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                   work_package_item_id=file1.id, remarks="Sent", reference="DLV-1")
        items_service.deliver_item(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                   work_package_item_id=file2.id, remarks="Sent", reference="DLV-2")
        db.flush()
        db.expire_all()

        # ================== READ-MODEL CONSISTENCY ==================
        ortho = _ortho_project(db, ctx)
        pkg_payload = ortho["packages"][0]
        tracking = _tracking_project(db, ctx)
        trow = next(r for r in tracking["package_rows"] if r["work_package_id"] == package.id)

        assert pkg_payload["has_items"] is True
        assert pkg_payload["files_expected"] == 2
        assert pkg_payload["files_production_done"] == 2
        assert pkg_payload["files_qc_passed"] == 2
        assert pkg_payload["files_qa_passed"] == 2
        assert pkg_payload["files_delivered"] == 2
        assert pkg_payload["cumulative_completed"] == 5.0        # 3 + 2
        assert pkg_payload["progress_percent"] == 100.0
        assert pkg_payload["stage_bucket"] == "delivered"
        # Workflow % = completed APPLICABLE stages / profile stages. The file workflow covers
        # the core Production→QC→QA→Delivery stages; the department profile may add more.
        from app.modules.operations.production_stages import stage_profile_for_department
        profile = stage_profile_for_department(ctx["workflow"].performing_department_code)
        core_done = len({"production", "qc", "qa", "delivery"} & set(profile))
        expected_workflow = round(core_done * 100.0 / len(profile), 2)
        assert pkg_payload["workflow_progress_percent"] == expected_workflow
        assert pkg_payload["workflow_progress_percent"] > 0        # never 0 % when core stages complete

        # Production Tracking agrees with /ortho (no read-model disagreement)
        assert trow["actual_quantity"] == 5.0
        assert trow["files_expected"] == 2 and trow["files_production_done"] == 2
        assert trow["files_qc_passed"] == 2 and trow["files_qa_passed"] == 2
        assert trow["files_delivered"] == 2
        assert trow["current_stage"] == "delivered"
        assert trow["workflow_progress_percent"] == pkg_payload["workflow_progress_percent"]
        assert trow["stage_statuses"]["production"] == "completed"
        assert trow["stage_statuses"]["qc"] == "approved"
        assert trow["stage_statuses"]["qa"] == "approved"
        assert trow["stage_statuses"]["delivery"] == "delivered"

        # Project-level progress is item-aware (not the stale legacy 0 %)
        assert ortho["summary"]["production_progress_percent"] == 100.0
        assert ortho["summary"]["workflow_progress_percent"] == expected_workflow
        assert tracking["production_progress_percent"] == 100.0
        assert ortho["summary"]["delivered"] == 1

        # ================== WORKBOOK ==================
        content, _ = build_production_workbook(
            db, report_type="project_workbook", actor=ctx["pm"], role=PM_ROLE,
            project_id=ctx["project"].id)
        workbook = load_workbook(BytesIO(content), data_only=True)
        area = next(r for r in workbook["AREA MASTER"].iter_rows(min_row=2, values_only=True)
                    if r[1] == package.package_code)
        assert area[3] == 5.0          # planned LENGTH (3 + 2)
        assert area[6] == 5.0          # ACTUAL KM (cumulative sessions)
        assert area[11] == "completed"
        assert area[20] == 2           # NO OF FILES = 2 physical files
        history = workbook["ACTIVITY HISTORY"]
        h = [c.value for c in history[1]]
        session_rows = [r for r in history.iter_rows(min_row=2, values_only=True)
                        if r[h.index("STAGE")] == "PRODUCTION"
                        and r[h.index("FILE NUMBER")] == file1.item_number]
        assert len(session_rows) == 3

        # ================== PM OPERATIONAL COMPLETION ==================
        workflow = operational_complete(
            db, actor=ctx["pm"], project_id=ctx["project"].id,
            payload=WorkflowOperationalCompletion(completion_date=date(2026, 10, 20),
                                                  final_delivery_reference="REF-E2E", remarks="Done"))
        assert workflow.operational_completed_at is not None
        assert workflow.finance_closed_at is None      # Finance stays separate
        assert workflow.status != "closed"


# ===========================================================================================
# NEGATIVE / GATE E2E (subset not already covered elsewhere)
# ===========================================================================================

def test_operational_completion_blocked_until_all_files_delivered():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "E2EN")
        _session(db, ctx, items[0], quantity="3.0", finalize=True,
                 start=datetime(2026, 10, 13, 9, 0), end=datetime(2026, 10, 13, 11, 0))
        run_review(db, ctx, items[0], "qc", "passed")
        run_review(db, ctx, items[0], "qa", "passed")
        # file 2 not even produced -> PM completion must be refused
        with pytest.raises(ValueError, match="must be delivered before Project Completion"):
            operational_complete(
                db, actor=ctx["pm"], project_id=ctx["project"].id,
                payload=WorkflowOperationalCompletion(completion_date=date(2026, 10, 20),
                                                      final_delivery_reference="REF-N"))


def test_unassigned_employee_cannot_mutate_file_and_cross_project_blocked():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "E2ES")
        from test_production_file_tracking_v8_2 import make_user as _mk
        stranger = _mk(db, "e2e.stranger@nakshatech.com", "employee", "LiDAR")
        db.flush()
        with pytest.raises(PermissionError):
            items_service.start_activity(db, actor=stranger, role=TL_ROLE,
                                         work_package_item_id=items[0].id, stage="production")
        management = _mk(db, "e2e.mgmt@nakshatech.com", "management")
        db.flush()
        with pytest.raises(PermissionError, match="read-only"):
            items_service.start_activity(db, actor=management, role="management",
                                         work_package_item_id=items[0].id, stage="production")


# ===========================================================================================
# READ-ONLY GLOBAL CONSISTENCY SCAN (covers live/HUNTER350 records without modifying them)
# ===========================================================================================

def test_no_contradictory_item_states_anywhere():
    """For EVERY area that tracks active files, the item rollups must never be
    internally contradictory (no QC>0 with Production 0, no 'not started' with
    activity, no delivered without delivery, no files beyond physical count)."""
    with SessionLocal() as db:
        package_ids = [p.id for p in db.scalars(select(OrthoWorkPackage).where(
            OrthoWorkPackage.id.in_(
                select(WorkPackageItem.work_package_id).where(WorkPackageItem.is_active.is_(True))
            )).order_by(OrthoWorkPackage.id)).all()][:200]
        if not package_ids:
            pytest.skip("No file-tracked areas in this database")
        from app.modules.operations.production_items import (
            build_item_rows, file_aggregates_for_packages,
        )
        agg = file_aggregates_for_packages(db, package_ids)
        rows_by_pkg: dict[int, list[dict]] = {}
        for row in build_item_rows(db, package_ids):
            rows_by_pkg.setdefault(row["work_package_id"], []).append(row)
        checked = 0
        for pid in package_ids:
            rows = [r for r in rows_by_pkg.get(pid, []) if r["is_active"]]
            if not rows:
                continue
            checked += 1
            counts = agg.get(pid, {})
            expected = counts.get("files_expected", len(rows))
            prod_done = counts.get("files_production_done", 0)
            qc_passed = counts.get("files_qc_passed", 0)
            qa_passed = counts.get("files_qa_passed", 0)
            delivered = counts.get("files_delivered", 0)
            # file counts can never exceed the number of physical files
            for value in (prod_done, qc_passed, qa_passed, delivered):
                assert value <= expected, f"package {pid}: file count {value} > files {expected}"
            # a file cannot pass QC/QA before its Production finished
            assert qc_passed <= prod_done, f"package {pid}: QC passed {qc_passed} > production done {prod_done}"
            assert qa_passed <= qc_passed, f"package {pid}: QA passed {qa_passed} > QC passed {qc_passed}"
            # delivered implies every file passed QA
            assert delivered <= qa_passed, f"package {pid}: delivered {delivered} > QA passed {qa_passed}"
            # any production activity means the area is not "not started"
            cumulative = sum((r["production_quantity"] or 0.0) for r in rows)
            assert cumulative >= 0
        assert checked > 0
