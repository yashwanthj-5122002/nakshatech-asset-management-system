"""Focused test: PROJECT-SCOPE atomic allocation (V8.6).

The Team Lead assigns physical files from DIFFERENT Lots / Codes / Areas to one Production
employee in ONE action, atomically. Isolated TEST DATA only.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.operations import production_allocation as alloc
from app.modules.operations.models import WorkPackageItem
from test_allocation_member_validation_v8_4 import _member
from test_production_master_excel_allocation_v8_3 import MASTER_HEADERS, setup_project, xlsx_bytes

TL = "employee"
PROD_T, QC_T, QA_T = date(2026, 10, 20), date(2026, 10, 22), date(2026, 10, 24)


def _two_areas(db, code, per_area=5):
    """One project with Area A and Area B, each holding ``per_area`` physical files."""
    ctx = setup_project(db, code)
    rows = []
    for lot, acode, area in (("LOT-031", "LOS-031", "AREA A"), ("LOT-032", "LOS-032", "AREA B")):
        for n in range(1, per_area + 1):
            rows.append([lot, acode, area, n, 6.0 if acode == "LOS-031" else 8.0, "km", ""])
    alloc.commit_master_import(
        db, actor=ctx["team"]["tl"], role=TL, project_id=ctx["project"].id,
        filename="M.xlsx", content=xlsx_bytes(MASTER_HEADERS, rows))
    items = list(db.scalars(select(WorkPackageItem).where(
        WorkPackageItem.project_id == ctx["project"].id).order_by(WorkPackageItem.id)).all())
    return ctx, items


def _options(db, ctx):
    return alloc.allocation_options(db, actor=ctx["team"]["tl"], role=TL,
                                    project_id=ctx["project"].id)


def _assign(db, ctx, items, prod, *, reassign=False):
    return alloc.assign_project_files(
        db, actor=ctx["team"]["tl"], role=TL, project_id=ctx["project"].id,
        item_ids=[i.id for i in items], production_user_id=prod.id,
        production_target_date=PROD_T, qc_user_id=ctx["team"]["qc"].id, qc_target_date=QC_T,
        qa_user_id=ctx["team"]["qa"].id, qa_target_date=QA_T, reassign=reassign)


def test_cross_area_atomic_assignment_updates_project_counters():
    with SessionLocal() as db:
        ctx, items = _two_areas(db, "PS-1")
        before = _options(db, ctx)
        assert before["total_files"] == 10
        assert before["assigned_files"] == 0
        assert before["available_files"] == 10
        assert len(before["files"]) == 10
        # every file carries its full context (lot / code / area / number)
        assert all(f["lot_or_batch"] and f["code"] and f["area"] and f["file_number"]
                   for f in before["files"])

        cross = [items[0], items[3], items[5], items[7]]      # spans Area A and Area B
        assert len({i.work_package_id for i in cross}) == 2
        summary = _assign(db, ctx, cross, ctx["team"]["prod"])
        db.flush()
        assert summary["assigned_files"] == 4
        assert summary["work_packages"] == 2

        after = _options(db, ctx)
        assert after["total_files"] == 10
        assert after["assigned_files"] == 4
        assert after["available_files"] == 6
        assert len([f for f in after["files"] if f["production_employee_id"]]) == 4


def test_failure_assigns_nothing_atomically():
    with SessionLocal() as db:
        ctx, items = _two_areas(db, "PS-2")
        other = _member(db, ctx, "ps.other@nakshatech.com", "production")
        _assign(db, ctx, items[:2], ctx["team"]["prod"])       # A owns 2 files
        db.flush()

        # Mixed selection: one file owned by A (with no history) + one free file.
        # Without explicit reassign the WHOLE action must be rejected...
        with pytest.raises(ValueError, match="already assigned"):
            _assign(db, ctx, [items[0], items[5]], other)
        db.flush()
        # ...and NOTHING may have been written (no partial allocation).
        assert db.get(WorkPackageItem, items[5].id).production_user_id is None
        assert db.get(WorkPackageItem, items[0].id).production_user_id == ctx["team"]["prod"].id


def test_file_number_is_unique_only_within_its_area():
    with SessionLocal() as db:
        ctx, items = _two_areas(db, "PS-3")
        area_a_file_1 = next(i for i in items if i.item_number == "1" and i.work_package_id == items[0].work_package_id)
        area_b_file_1 = next(i for i in items if i.item_number == "1" and i.work_package_id == items[5].work_package_id)
        assert area_a_file_1.id != area_b_file_1.id          # different physical files

        _assign(db, ctx, [area_b_file_1], ctx["team"]["prod"])
        db.flush()
        assert db.get(WorkPackageItem, area_b_file_1.id).production_user_id == ctx["team"]["prod"].id
        assert db.get(WorkPackageItem, area_a_file_1.id).production_user_id is None
