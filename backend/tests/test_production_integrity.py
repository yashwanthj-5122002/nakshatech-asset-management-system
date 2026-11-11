"""Production output is a planned file total, not a sum of completion snapshots."""
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.modules.operations import production_allocation as allocation
from app.modules.operations import production_items as items
from app.modules.operations.models import WorkPackageItemActivity
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS, assign_all, import_master, items_of, packages_of, setup_project, xlsx_bytes,
)


@pytest.fixture
def production_case():
    with SessionLocal() as db:
        ctx = setup_project(db, "INTEGRITY")
        import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, [["LOT", "CODE", "AREA", "F1", 3000, "m", ""]]))
        package = packages_of(db, ctx)[0]
        item = items_of(db, ctx)[0]
        assign_all(db, ctx, package, [item.id])
        yield db, ctx, package, item


def session(case, *, start, quantity=None, unit="km", finalize=True, stage="production", status=None):
    db, ctx, _, item = case
    actor = ctx["team"][{"production": "prod", "qc": "qc", "qa": "qa"}[stage]]
    activity = items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id,
                                    stage=stage, started_at=start)
    return items.stop_activity(db, actor=actor, activity_id=activity.id,
                               status=status or ("completed" if stage == "production" else "passed"),
                               quantity_completed=quantity, unit=unit, finalize=finalize,
                               ended_at=start + timedelta(minutes=10))


def test_partial_final_rework_and_exports_attribute_the_plan_once(production_case):
    db, ctx, package, item = production_case
    start = datetime(2026, 10, 10, 9)
    partial = session(production_case, start=start, quantity=Decimal("1200"), unit="m", finalize=False)
    final = session(production_case, start=start + timedelta(hours=1), quantity=Decimal("9999"))
    assert final.quantity_completed == Decimal("3")  # full plan is server-authoritative
    assert final.unit == "km"
    session(production_case, start=start + timedelta(hours=2), stage="qc", status="rejected")
    session(production_case, start=start + timedelta(hours=3), quantity=Decimal("9999"))
    row = items.build_item_rows(db, [package.id])[0]
    assert row["production_quantity"] == 3
    assert row["production_files"] == 1
    history = items.activity_rows_for_packages(db, [package.id])
    assert [r["quantity_completed"] for r in history if r["stage"] == "production"] == [1.2, 1.8, 0]
    assert history[1]["recorded_quantity"] == 3
    assert sum(r["quantity_completed"] for r in items.employee_productivity_rows(db, [package.id])) == 3
    assert sum(r["quantity_completed"] for r in items.employee_file_totals(db, [package.id])) == 3
    assert partial.quantity_completed == Decimal("1.2")  # normalized once, never rewritten


def test_legacy_completion_snapshot_is_not_added_to_previous_progress(production_case):
    db, _, package, _ = production_case
    start = datetime(2026, 10, 10, 9)
    session(production_case, start=start, quantity=Decimal("2.2"), finalize=False)
    final = session(production_case, start=start + timedelta(hours=1))
    assert final.quantity_completed == Decimal("3")
    assert items.build_item_rows(db, [package.id])[0]["production_quantity"] == 3


def test_missing_plan_is_blocked_before_assignment_and_can_be_corrected(production_case):
    db, ctx, package, _ = production_case
    draft = items.add_items(db, actor=ctx["team"]["tl"], role="employee", work_package_id=package.id,
                            entries=[{"item_number": "DRAFT"}])[0]
    with pytest.raises(ValueError, match="planned quantity"):
        assign_all(db, ctx, package, [draft.id])
    assert draft.production_user_id is None
    items.update_item(db, actor=ctx["team"]["tl"], role="employee", work_package_item_id=draft.id,
                      changes={"planned_quantity": "100", "planned_unit": "m"},
                      provided={"planned_quantity", "planned_unit"})
    assign_all(db, ctx, package, [draft.id])
    assert draft.production_user_id == ctx["team"]["prod"].id


@pytest.mark.parametrize("quantity,unit,message", [
    (Decimal("4"), "km", "remaining"), (Decimal("1"), "files", "unit"),
    (Decimal("NaN"), "km", "quantity"), (Decimal("-1"), "km", "quantity"),
])
def test_invalid_progress_keeps_session_open(production_case, quantity, unit, message):
    db, ctx, _, item = production_case
    actor = ctx["team"]["prod"]
    activity = items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id, stage="production")
    with pytest.raises(ValueError, match=message):
        items.stop_activity(db, actor=actor, activity_id=activity.id, finalize=False,
                            quantity_completed=quantity, unit=unit,
                            ended_at=activity.started_at + timedelta(minutes=1))
    assert activity.ended_at is None


def test_same_clock_tick_is_valid_but_backwards_time_is_rejected(production_case):
    db, ctx, _, item = production_case
    actor = ctx["team"]["prod"]
    activity = items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id, stage="production")
    with pytest.raises(ValueError, match="before"):
        items.stop_activity(db, actor=actor, activity_id=activity.id, ended_at=activity.started_at - timedelta(seconds=1))
    done = items.stop_activity(db, actor=actor, activity_id=activity.id, ended_at=activity.started_at)
    assert done.duration_seconds == 0
    with pytest.raises(ValueError, match="already completed"):
        items.stop_activity(db, actor=actor, activity_id=activity.id)


def test_database_rejects_a_second_open_session(production_case):
    db, ctx, package, item = production_case
    actor = ctx["team"]["prod"]
    activity = items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id, stage="production")
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(WorkPackageItemActivity(project_id=package.project_id, work_package_id=package.id,
                                       work_package_item_id=item.id, employee_user_id=actor.id,
                                       stage="production", started_at=activity.started_at, status="in_progress"))
        db.flush()


def test_completed_plan_cannot_rewrite_historical_output(production_case):
    db, ctx, _, item = production_case
    session(production_case, start=datetime(2026, 10, 10, 9))
    with pytest.raises(ValueError, match="cannot be changed"):
        items.update_item(db, actor=ctx["team"]["tl"], role="employee", work_package_item_id=item.id,
                          changes={"planned_quantity": 5000}, provided={"planned_quantity"})


def test_small_distance_conversion_survives_database_reload(production_case):
    db, ctx, package, item = production_case
    items.update_item(db, actor=ctx["team"]["tl"], role="employee", work_package_item_id=item.id,
                      changes={"planned_quantity": "0.001", "planned_unit": "mm"},
                      provided={"planned_quantity", "planned_unit"})
    activity = session(production_case, start=datetime(2026, 10, 10, 9))
    activity_id = activity.id
    db.flush()
    db.expire_all()
    assert db.get(WorkPackageItemActivity, activity_id).quantity_completed == Decimal("0.000000001")
    assert items.build_item_rows(db, [package.id])[0]["production_quantity"] == 0.000000001


def test_same_timestamp_correction_still_requires_a_new_production_attempt(production_case):
    db, ctx, _, item = production_case
    stamp = datetime(2026, 10, 10, 9)
    for stage, state in [("production", "completed"), ("qc", "rejected"),
                         ("production", "completed"), ("qc", "passed")]:
        actor = ctx["team"]["prod" if stage == "production" else "qc"]
        activity = items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id,
                                        stage=stage, started_at=stamp)
        items.stop_activity(db, actor=actor, activity_id=activity.id, status=state, ended_at=stamp, remarks="Correction")
        if stage == "qc" and state == "rejected":
            with pytest.raises(ValueError, match="correction"):
                items.start_activity(db, actor=actor, role="employee", work_package_item_id=item.id,
                                      stage="qc", started_at=stamp)


def test_blocked_session_never_counts_as_a_completed_file(production_case):
    db, ctx, package, item = production_case
    session(production_case, start=datetime(2026, 10, 10, 9), status="blocked", quantity=Decimal("0.5"))
    row = items.build_item_rows(db, [package.id])[0]
    assert row["production_files"] == 0
    assert row["production_status"] == "blocked"
    with pytest.raises(ValueError, match="Production must be completed"):
        items.start_activity(db, actor=ctx["team"]["qc"], role="employee", work_package_item_id=item.id, stage="qc")
