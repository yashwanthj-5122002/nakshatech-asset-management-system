"""Focused tests: Team Lead allocation membership + exclusivity contracts (V8.4 UX pass).

These verify the AUTHORITATIVE backend rules behind the new per-employee
"+ Add Employee" allocation UI:

  * the allocation options expose ONLY active PM-selected project-team members
    (per role) — never the whole company employee list;
  * a forged assign-files request with a non-member / wrong-role / removed member
    is rejected by the backend (frontend filtering alone is never the guard);
  * physical-file exclusivity holds (an assigned file is not available to a second
    production employee);
  * an UNSTARTED, history-free file can be explicitly reassigned, while a file that
    already has work history cannot be silently reassigned;
  * historical ownership stays readable if the PM later removes the member.

Isolated TEST DATA only. Not the release regression.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.operations import production_allocation as alloc
from app.modules.operations import production_items as items_service
from app.modules.operations.models import OrthoProjectMember
from test_production_file_tracking_v8_2 import make_user
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS,
    MASTER_ROWS,
    items_of,
    packages_of,
    setup_project,
    xlsx_bytes,
)

TL = "employee"
PROD_T, QC_T, QA_T = date(2026, 10, 20), date(2026, 10, 22), date(2026, 10, 24)


def _area(db, code):
    ctx = setup_project(db, code)
    alloc.commit_master_import(
        db, actor=ctx["team"]["tl"], role=TL, project_id=ctx["project"].id,
        filename="M.xlsx", content=xlsx_bytes(MASTER_HEADERS, MASTER_ROWS))
    pkg = packages_of(db, ctx)[0]
    items = sorted([i for i in items_of(db, ctx) if i.work_package_id == pkg.id], key=lambda i: i.id)
    return ctx, pkg, items


def _area_multi(db, code, count):
    """One area holding ``count`` explicit physical files (FILE NUMBER 1..count)."""
    ctx = setup_project(db, code)
    rows = [["LOT-MV", "MV-CODE-1", "MV AREA", i, 1.00, "km", ""]
            for i in range(1, count + 1)]
    alloc.commit_master_import(
        db, actor=ctx["team"]["tl"], role=TL, project_id=ctx["project"].id,
        filename="M.xlsx", content=xlsx_bytes(MASTER_HEADERS, rows))
    pkg = packages_of(db, ctx)[0]
    items = sorted([i for i in items_of(db, ctx) if i.work_package_id == pkg.id],
                   key=lambda i: int(i.item_number))
    return ctx, pkg, items


def _member(db, ctx, email, role, *, active=True):
    """Create an employee and give them a project-team membership for ``role``."""
    user = make_user(db, email, "employee", "LiDAR")
    db.flush()
    db.add(OrthoProjectMember(project_id=ctx["project"].id, user_id=user.id,
                              member_role=role, is_active=active,
                              assigned_by_id=ctx["pm"].id))
    db.flush()
    return user


def _options(db, ctx):
    return alloc.allocation_options(db, actor=ctx["team"]["tl"], role=TL,
                                    project_id=ctx["project"].id)


def _assign(db, ctx, pkg, items, prod, *, reassign=False):
    return alloc.assign_files(
        db, actor=ctx["team"]["tl"], role=TL, work_package_id=pkg.id,
        item_ids=[i.id for i in items], production_user_id=prod.id,
        production_target_date=PROD_T,
        qc_user_id=ctx["team"]["qc"].id, qc_target_date=QC_T,
        qa_user_id=ctx["team"]["qa"].id, qa_target_date=QA_T,
        reassign=reassign)


# ================== 1,2,20,21: PM-selected members only ==================================

def test_options_expose_only_pm_selected_active_members_per_role():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-1")
        stranger = make_user(db, "mv.stranger@nakshatech.com", "employee", "LiDAR")   # no membership
        wrong_role = _member(db, ctx, "mv.wrongrole@nakshatech.com", "qc")            # qc only
        removed = _member(db, ctx, "mv.removed@nakshatech.com", "production", active=False)
        prod11 = _member(db, ctx, "mv.prod11@nakshatech.com", "production")
        db.flush()

        opts = _options(db, ctx)
        prod_ids = {u["user_id"] for u in opts["team"]["production"]}
        qc_ids = {u["user_id"] for u in opts["team"]["qc"]}
        qa_ids = {u["user_id"] for u in opts["team"]["qa"]}

        assert prod11.id in prod_ids                      # active PM-selected member shown
        assert ctx["team"]["prod"].id in prod_ids
        assert stranger.id not in prod_ids                # not on the team -> hidden
        assert removed.id not in prod_ids                 # removed/inactive -> hidden
        assert wrong_role.id not in prod_ids              # wrong project role -> hidden
        assert wrong_role.id in qc_ids                    # ...but shown under their own role
        assert ctx["team"]["qa"].id in qa_ids
        assert stranger.id not in qc_ids and stranger.id not in qa_ids


# ================== 3,4: forged / invalid requests rejected ==============================

def test_forged_assignment_to_non_project_member_is_rejected():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-2")
        stranger = make_user(db, "mv.stranger2@nakshatech.com", "employee", "LiDAR")
        db.flush()
        with pytest.raises(ValueError, match="PM-approved project team member"):
            _assign(db, ctx, pkg, items[:1], stranger)
        assert not items[0].production_user_id            # nothing was written


def test_wrong_role_member_is_rejected_for_production():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-3")
        qc_only = _member(db, ctx, "mv.qconly@nakshatech.com", "qc")
        with pytest.raises(ValueError, match="PM-approved project team member"):
            _assign(db, ctx, pkg, items[:1], qc_only)


def test_inactive_member_is_rejected_for_new_assignment():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-4")
        removed = _member(db, ctx, "mv.removed2@nakshatech.com", "production", active=False)
        with pytest.raises(ValueError, match="PM-approved project team member"):
            _assign(db, ctx, pkg, items[:1], removed)


# ================== 5,6,7: exclusivity + reassignment ====================================

def test_assigned_file_is_unavailable_to_a_second_employee():
    with SessionLocal() as db:
        ctx, pkg, items = _area_multi(db, "MV-5", 4)
        assert len(items) == 4
        prod11 = _member(db, ctx, "mv.prod11b@nakshatech.com", "production")
        _assign(db, ctx, pkg, items[:2], ctx["team"]["prod"])          # A owns files 1,2
        with pytest.raises(ValueError):
            _assign(db, ctx, pkg, items[:2], prod11)                   # A's files refused
        _assign(db, ctx, pkg, items[2:], prod11)                       # B gets only free files
        files = alloc.area_files(db, actor=ctx["team"]["tl"], role=TL,
                                 work_package_id=pkg.id)
        owners = {f["item_number"]: f["production_user_id"] for f in files["files"]}
        assert owners[items[0].item_number] == ctx["team"]["prod"].id
        assert owners[items[2].item_number] == prod11.id
        assert files["assigned_files"] == len(files["files"])
        assert files["available_files"] == 0


def test_unstarted_file_can_be_explicitly_reassigned():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-6")
        prod11 = _member(db, ctx, "mv.prod11c@nakshatech.com", "production")
        _assign(db, ctx, pkg, items[:1], ctx["team"]["prod"])
        # no work yet -> explicit reassign is allowed
        _assign(db, ctx, pkg, items[:1], prod11, reassign=True)
        db.flush()
        assert db.get(type(items[0]), items[0].id).production_user_id == prod11.id


def test_started_file_cannot_be_reassigned_even_explicitly():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-7")
        prod11 = _member(db, ctx, "mv.prod11d@nakshatech.com", "production")
        _assign(db, ctx, pkg, items[:1], ctx["team"]["prod"])
        items_service.start_activity(db, actor=ctx["team"]["prod"], role=TL,
                                     work_package_item_id=items[0].id, stage="production")
        db.flush()
        with pytest.raises(ValueError, match="work history"):
            _assign(db, ctx, pkg, items[:1], prod11, reassign=True)
        db.flush()
        assert db.get(type(items[0]), items[0].id).production_user_id == ctx["team"]["prod"].id


# ================== 8,9: area payload contract + removed member readability =============

def test_area_files_expose_owner_target_and_readonly_remarks():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-8")
        _assign(db, ctx, pkg, items[:1], ctx["team"]["prod"])
        payload = alloc.area_files(db, actor=ctx["team"]["tl"], role=TL, work_package_id=pkg.id)
        row = next(f for f in payload["files"] if f["work_package_item_id"] == items[0].id)
        assert row["production_user_id"] == ctx["team"]["prod"].id
        assert row["production_user"]                              # display name for the card
        assert row["production_target_date"].startswith("2026-10-20")
        # The UI reads the imported master remarks from the read-only area field.
        assert "remarks" in payload
        assert payload["remarks"] == pkg.remarks
        assert payload["total_files"] == len(payload["files"])
        assert payload["assigned_files"] == 1


def test_historical_assignment_stays_readable_after_member_removed():
    with SessionLocal() as db:
        ctx, pkg, items = _area(db, "MV-9")
        prod11 = _member(db, ctx, "mv.leaver@nakshatech.com", "production")
        _assign(db, ctx, pkg, items[:1], prod11)
        db.flush()
        # PM removes the member from the project team
        row = db.scalar(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == ctx["project"].id,
            OrthoProjectMember.user_id == prod11.id))
        row.is_active = False
        db.flush()

        opts = _options(db, ctx)
        assert prod11.id not in {u["user_id"] for u in opts["team"]["production"]}   # hidden from NEW
        payload = alloc.area_files(db, actor=ctx["team"]["tl"], role=TL, work_package_id=pkg.id)
        keeper = next(f for f in payload["files"] if f["work_package_item_id"] == items[0].id)
        assert keeper["production_user_id"] == prod11.id          # history/ownership preserved
