"""Focused tests: Project Operations (/ortho) item-level visibility, counts and assignees.

The /ortho dashboard was reading ONLY the legacy package-level singular columns, so
imported file-based areas showed Files = 0, assignees '—', and employees saw nothing.
These tests pin the corrected behaviour: WorkPackageItem (+ activities) is the single
source of truth whenever an area has ACTIVE files, while zero-item packages keep the
legacy package-level flow.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.operations import production_allocation as alloc
from app.modules.operations import production_items as items_service
from app.modules.operations.models import OrthoProjectMember
from app.modules.operations.workflow_service import ortho_dashboard
from test_production_file_tracking_v8_2 import make_area, make_user
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS,
    MASTER_ROWS,
    assign_all,
    import_master,
    items_of,
    packages_of,
    run_production,
    setup_project,
    xlsx_bytes,
)

TL_ROLE = "employee"


def _dashboard(db, user, role):
    return ortho_dashboard(db, actor=user, role=role)


def _project_row(dash, ctx):
    return next(p for p in dash["projects"] if p["project_id"] == ctx["project"].id)


def _prepare(db, code):
    """One imported area (FOGNATURA 1, file 1) allocated to the standard team."""
    ctx = setup_project(db, code)
    import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, MASTER_ROWS))
    package = packages_of(db, ctx)[0]
    items = [i for i in items_of(db, ctx) if i.work_package_id == package.id]
    assign_all(db, ctx, package, [i.id for i in items])
    return ctx, package, items


# ===========================================================================================
# package-level counts and assignees (file-based areas)
# ===========================================================================================

def test_imported_package_reports_files_count():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV1")
        payload = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)["packages"][0]
        assert payload["has_items"] is True
        assert payload["files_expected"] == 1          # active imported file
        assert payload["files_completed"] == 1         # legacy field now item-based
        assert payload["cumulative_completed"] == 0.0
        assert payload["remaining_quantity"] == float(package.area)


def test_imported_package_shows_item_level_assignees():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV2")
        payload = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)["packages"][0]
        assignees = payload["item_assignees"]
        assert [u["full_name"] for u in assignees["production"]] == ["prod.ft.OV2"]
        assert [u["full_name"] for u in assignees["qc"]] == ["qc.ft.OV2"]
        assert [u["full_name"] for u in assignees["qa"]] == ["qa.ft.OV2"]
        # legacy assignments stay empty for imported areas (no copied values)
        assert payload["assignments"]["production"] is None


def test_multi_assignee_aggregation_not_lost():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV3")
        team = ctx["team"]
        # a second production member assigned to a second file of the same area
        extra = make_user(db, "prod2.ov3@nakshatech.com", "employee", "LiDAR")
        db.add(OrthoProjectMember(project_id=ctx["project"].id, user_id=extra.id,
                                  member_role="production", is_active=True, assigned_by_id=team["tl"].id))
        db.flush()
        item2 = items_service.add_items(
            db, actor=team["tl"], role=TL_ROLE, work_package_id=package.id,
            entries=[{"item_number": "EXTRA-1", "production_user_id": extra.id}])[0]
        db.flush()
        payload = _project_row(_dashboard(db, team["tl"], TL_ROLE), ctx)["packages"][0]
        names = {u["full_name"] for u in payload["item_assignees"]["production"]}
        assert names == {"prod.ft.OV3", "prod2.ov3"}


# ===========================================================================================
# employee visibility (file-level assignment is authoritative)
# ===========================================================================================

def test_production_employee_sees_package_when_assigned_to_one_item():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV4")
        dash = _dashboard(db, ctx["team"]["prod"], TL_ROLE)
        row = _project_row(dash, ctx)
        assert row["summary"]["packages"] == 1
        assert row["summary"]["production"] == 1
        payload = row["packages"][0]
        assert payload["package_code"] == package.package_code
        assert "production" in payload["my_roles"]


def test_employee_sees_only_their_assigned_files():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV5")
        team = ctx["team"]
        other = make_user(db, "prod9.ov5@nakshatech.com", "employee", "LiDAR")
        db.add(OrthoProjectMember(project_id=ctx["project"].id, user_id=other.id,
                                  member_role="production", is_active=True, assigned_by_id=team["tl"].id))
        db.flush()
        item2 = items_service.add_items(
            db, actor=team["tl"], role=TL_ROLE, work_package_id=package.id,
            entries=[{"item_number": "SIBLING-1", "production_user_id": other.id}])[0]
        db.flush()
        payload = _project_row(_dashboard(db, team["prod"], TL_ROLE), ctx)["packages"][0]
        visible = [row["item_number"] for row in payload["items"]]
        assert visible == [items[0].item_number]      # NOT the sibling file
        assert item2.item_number not in visible
        # PM sees every file of the area
        pm_payload = _project_row(_dashboard(db, ctx["pm"], "lidar"), ctx)["packages"][0]
        assert {row["item_number"] for row in pm_payload["items"]} == {items[0].item_number, "SIBLING-1"}


def test_unrelated_production_employee_sees_nothing():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV6")
        stranger = make_user(db, "stranger.ov6@nakshatech.com", "employee", "LiDAR")
        db.flush()
        dash = _dashboard(db, stranger, TL_ROLE)
        assert all(p["project_id"] != ctx["project"].id for p in dash["projects"])


def test_qc_and_qa_employee_filtering_uses_item_assignment():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV7")
        team = ctx["team"]
        qc_dash = _dashboard(db, team["qc"], TL_ROLE)
        qc_row = _project_row(qc_dash, ctx)
        assert qc_row["summary"]["packages"] == 1
        assert "qc" in qc_row["packages"][0]["my_roles"]
        qa_dash = _dashboard(db, team["qa"], TL_ROLE)
        qa_row = _project_row(qa_dash, ctx)
        assert "qa" in qa_row["packages"][0]["my_roles"]
        # an unrelated employee is not granted QC visibility
        stranger = make_user(db, "stranger.ov7@nakshatech.com", "employee", "LiDAR")
        db.flush()
        assert all(p["project_id"] != ctx["project"].id for p in _dashboard(db, stranger, TL_ROLE)["projects"])


# ===========================================================================================
# PM / TL keep full visibility
# ===========================================================================================

def test_pm_still_sees_all_project_packages():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV8")
        row = _project_row(_dashboard(db, ctx["pm"], "lidar"), ctx)
        assert row["summary"]["packages"] == 3
        assert all(p["has_items"] for p in row["packages"])


def test_team_lead_still_sees_all_lead_project_packages():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV9")
        row = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)
        assert row["summary"]["packages"] == 3


# ===========================================================================================
# counts, consistency, legacy flow
# ===========================================================================================

def test_employee_dashboard_counts_are_correct():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV10")
        dash = _dashboard(db, ctx["team"]["prod"], TL_ROLE)
        row = _project_row(dash, ctx)
        assert row["summary"]["packages"] == 1
        assert row["summary"]["production"] == 1
        assert row["summary"]["qc"] == 0 and row["summary"]["qa"] == 0
        assert row["summary"]["delivered"] == 0


def test_no_duplicate_file_or_quantity_counting():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV11")
        run_production(db, ctx, items[0], quantity="1.16")
        payload = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)["packages"][0]
        assert payload["files_expected"] == 1
        assert payload["files_completed"] == 1            # not 2, not legacy + item
        assert payload["files_production_done"] == 1
        assert payload["cumulative_completed"] == 1.16    # single occurrence
        assert abs(payload["remaining_quantity"] - (float(package.area) - 1.16)) < 1e-9
        assert payload["progress_percent"] == round(1.16 / float(package.area) * 100, 2)


def test_project_operations_and_production_tracking_agree():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV12")
        agg = items_service.file_aggregates_for_packages(db, [package.id])[package.id]
        payload = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)["packages"][0]
        assert payload["files_expected"] == agg["files_expected"]
        assert payload["files_production_done"] == agg["files_production_done"]
        assert payload["files_qa_passed"] == agg["files_qa_passed"]


def test_stage_bucket_drives_summary_counts():
    with SessionLocal() as db:
        ctx, package, items = _prepare(db, "OV13")
        run_production(db, ctx, items[0])
        row = _project_row(_dashboard(db, ctx["team"]["tl"], TL_ROLE), ctx)
        buckets = {p["package_code"]: p["stage_bucket"] for p in row["packages"]}
        assert buckets[package.package_code] == "qc"      # production done -> QC
        assert row["summary"]["qc"] == 1
        assert row["summary"]["production"] == 2          # the two untouched areas


def test_legacy_zero_item_package_keeps_package_level_assignment():
    with SessionLocal() as db:
        ctx = make_area(db, code="OV14")                  # legacy allocate_work, no items
        team = ctx["team"]
        row = _project_row(_dashboard(db, team["prod"], TL_ROLE), ctx)
        payload = row["packages"][0]
        assert payload["has_items"] is False
        assert "production" in payload["my_roles"]        # legacy package-level assignment
        assert payload["files_completed"] == 0            # legacy daily-update count stays authoritative
        assert payload["quantity"] == float(ctx["package"].area)  # legacy Assigned value intact