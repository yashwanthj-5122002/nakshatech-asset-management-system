"""V8.2 optional FILE / TILE / ITEM tracking — focused tests.

Covers the required matrix: optional file tracking (area-only packages keep working),
TL file management (add / bulk / sequence / import / assign), real Start/Stop timings
with automatic + overnight duration, employee-wise attribution and aggregation,
1-day buffer / overdue / completed-in-buffer / completed-late, delay & system
malfunction capture, QC/QA timings and pass/reject/rework history, delivery,
authorization (unauthorized employee + Management read-only), and the selected-project
Excel workbook (AREA MASTER exact 26 columns, FILE ACTIVITY, EMPLOYEE PRODUCTIVITY).

All sessions run transactional (flush only, rollback on close) like the V8.1 suite.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.commercial import models as _commercial_models  # noqa: F401  (register tables before conftest create_all)
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.finance.models import FinanceClient
from app.modules.operations.models import WorkPackageItem
from app.modules.operations.production_items import (
    add_items,
    assign_items,
    buffer_days_for,
    deadline_status,
    deliver_item,
    employee_file_totals,
    employee_productivity_rows,
    file_aggregates_for_packages,
    generate_sequence,
    item_history,
    item_list,
    parse_items_file,
    start_activity,
    stop_activity,
    update_item,
)
from app.modules.operations.production_reporting import (
    AREA_MASTER_HEADERS,
    EMPLOYEE_PRODUCTIVITY_HEADERS,
    FILE_ACTIVITY_HEADERS,
    build_production_workbook,
)
from app.modules.operations.schemas import (
    WorkflowFinanceReview,
    WorkflowPMAssignment,
    WorkflowProjectCreate,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)
from app.modules.operations.workflow_service import (
    allocate_work,
    assign_project_manager,
    configure_team,
    create_bd_project,
    finance_review_project,
    submit_project_to_finance,
)


def make_user(db, email: str, role: str, department: str | None = None) -> User:
    row = User(
        email=email, full_name=email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", department=department, email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def make_client(db, owner: User, code: str) -> FinanceClient:
    client = FinanceClient(
        client_code=f"C-{code}", client_name="File Tracking Client", contact_person_name="Contact",
        contact_person_phone="9999999999", source_team="bd_team", source_person_name=owner.full_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def approved_project(db, *, code: str, department_code: str = "lidar", department_label: str = "LiDAR"):
    bd = make_user(db, f"bd.ft.{code}@nakshatech.com", "bd")
    finance = make_user(db, f"fin.ft.{code}@nakshatech.com", "finance")
    pm = make_user(db, f"pm.ft.{code}@nakshatech.com", department_code, department_label)
    client = make_client(db, bd, code)
    project, workflow = create_bd_project(db, actor=bd, payload=WorkflowProjectCreate(
        client_id=client.id, project_code=f"FT-{code}", project_name="File Tracking Project",
        start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
        performing_department_code=department_code,
        commercial=ProjectCommercialInput(
            scope_description="Survey and deliver", billing_type="fixed_price", payment_terms="30 days",
            currency_code="INR", estimated_amount=Decimal("500000"), taxable_base_amount=Decimal("500000"),
            tax_percent=Decimal("18"), estimate_date=date(2026, 9, 22),
        ),
    ))
    db.flush()
    submit_project_to_finance(db, actor=bd, project_id=project.id)
    db.flush()
    finance_review_project(db, actor=finance, project_id=project.id,
                           payload=WorkflowFinanceReview(decision="approve", comments="Approved"))
    db.flush()
    assign_project_manager(db, actor=bd, project_id=project.id,
                           payload=WorkflowPMAssignment(project_manager_id=pm.id))
    db.flush()
    return bd, finance, pm, project, workflow


def full_team(db, pm: User, project, code: str):
    tl = make_user(db, f"tl.ft.{code}@nakshatech.com", "employee", "LiDAR")
    prod = make_user(db, f"prod.ft.{code}@nakshatech.com", "employee", "LiDAR")
    qc = make_user(db, f"qc.ft.{code}@nakshatech.com", "employee", "LiDAR")
    qa = make_user(db, f"qa.ft.{code}@nakshatech.com", "employee", "LiDAR")
    configure_team(db, actor=pm, project_id=project.id, payload=WorkflowTeamSetup(
        team_leader_user_id=tl.id, production_user_ids=[prod.id], qc_user_ids=[qc.id], qa_user_ids=[qa.id],
    ))
    db.flush()
    return {"tl": tl, "prod": prod, "qc": qc, "qa": qa}


def make_area(db, *, code: str, target: date = date(2026, 10, 15), quantity: str = "10", unit: str = "km"):
    """BD -> Finance -> PM -> team -> Team Lead allocation (existing engine untouched)."""
    bd, finance, pm, project, workflow = approved_project(db, code=code)
    team = full_team(db, pm, project, code)
    package = allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
        package_code=f"AR-{code}", area_name=f"Area {code}", quantity=Decimal(quantity), quantity_unit=unit,
        target_date=target, instructions="Deliver",
        production_user_id=team["prod"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
    ))
    db.flush()
    return {"bd": bd, "finance": finance, "pm": pm, "project": project, "team": team, "package": package}


TL_ROLE = "employee"
PM_ROLE = "lidar"


# ===========================================================================================
# optional file tracking + Team Lead file management
# ===========================================================================================

def test_area_without_files_still_works():
    with SessionLocal() as db:
        ctx = make_area(db, code="NOFILE")
        listing = item_list(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        assert listing["items"] == []
        agg = file_aggregates_for_packages(db, [ctx["package"].id])[ctx["package"].id]
        assert agg["files_expected"] == 0 and agg["files_production_done"] == 0
        # area-level engine untouched
        assert ctx["package"].current_stage in {"not_started", "production"}


def test_tl_adds_one_file():
    with SessionLocal() as db:
        ctx = make_area(db, code="ONE")
        created = add_items(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                            entries=[{"item_number": "BLDG_001", "item_name": "BLDG_001.dxf"}])
        assert len(created) == 1
        db.flush()
        listing = item_list(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        assert [i["item_number"] for i in listing["items"]] == ["BLDG_001"]
        assert listing["items"][0]["production_status"] == "not_started"
        assert listing["can_manage"] is True


def test_tl_adds_multiple_files():
    with SessionLocal() as db:
        ctx = make_area(db, code="MULTI")
        entries = [{"item_number": f"TILE_{n:03d}"} for n in range(1, 6)]
        created = add_items(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                            entries=entries)
        assert len(created) == 5
        listing = item_list(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        assert len(listing["items"]) == 5


def test_sequence_generation():
    with SessionLocal() as db:
        ctx = make_area(db, code="SEQ")
        created = generate_sequence(db, actor=ctx["team"]["tl"], role=TL_ROLE,
                                    work_package_id=ctx["package"].id,
                                    prefix="FILE", start=1, count=3, padding=3)
        assert [i.item_number for i in created] == ["FILE_001", "FILE_002", "FILE_003"]
        assert [i.sequence_no for i in created] == [1, 2, 3]


def test_duplicate_file_numbers_rejected():
    with SessionLocal() as db:
        ctx = make_area(db, code="DUP")
        with pytest.raises(ValueError, match="Duplicate"):
            add_items(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                      entries=[{"item_number": "D1"}, {"item_number": "D1"}])
        # nothing partial was created, then a valid add still works
        assert db.scalar(select(WorkPackageItem.id).where(
            WorkPackageItem.work_package_id == ctx["package"].id)) is None
        created = add_items(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                            entries=[{"item_number": "D1"}])
        assert len(created) == 1
        with pytest.raises(ValueError, match="Duplicate"):
            add_items(db, actor=ctx["team"]["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                      entries=[{"item_number": "D1"}])


def test_import_validation():
    good = b"item_number,item_name,planned_quantity,planned_unit\nF1,First.dxf,5,km\nF2,Second.dxf,7,km\n"
    entries = parse_items_file("files.csv", good)
    assert [e["item_number"] for e in entries] == ["F1", "F2"]
    # headerless fallback
    entries = parse_items_file("files.csv", b"F3,Third\n")
    assert entries[0]["item_number"] == "F3"
    # missing file number -> row-level validation error
    with pytest.raises(ValueError, match="row 2"):
        parse_items_file("files.csv", b"item_number,item_name\n,noname\n")
    # header-only file has no data rows
    with pytest.raises(ValueError, match="No valid file rows"):
        parse_items_file("files.csv", b"item_number,item_name\n")
    # completely empty file
    with pytest.raises(ValueError, match="empty"):
        parse_items_file("files.csv", b"")


def test_file_assignment():
    with SessionLocal() as db:
        ctx = make_area(db, code="ASGN")
        team = ctx["team"]
        created = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                            entries=[{"item_number": "A1"}, {"item_number": "A2"}])
        ids = [i.id for i in created]
        assign_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                     item_ids=ids, production_user_id=team["prod"].id,
                     qc_user_id=team["qc"].id, qa_user_id=team["qa"].id)
        db.flush()
        listing = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        row = next(r for r in listing["items"] if r["item_number"] == "A1")
        assert row["production_user_id"] == team["prod"].id
        assert row["qc_user_id"] == team["qc"].id
        assert row["qa_user_id"] == team["qa"].id
        # assignee must be an approved team member for that role
        outsider = make_user(db, "outsider.ft@nakshatech.com", "employee", "LiDAR")
        with pytest.raises(ValueError, match="team member"):
            assign_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         item_ids=ids, production_user_id=outsider.id)


# ===========================================================================================
# authorization
# ===========================================================================================

def test_employee_sees_only_assigned_files():
    with SessionLocal() as db:
        ctx = make_area(db, code="SEEF")
        team = ctx["team"]
        outsider = make_user(db, "noshow.ft@nakshatech.com", "employee", "LiDAR")
        add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id, entries=[
            {"item_number": "MINE", "production_user_id": team["prod"].id},
            {"item_number": "THEIRS", "qc_user_id": team["qc"].id},
        ])
        db.flush()
        listing = item_list(db, actor=team["prod"], role="employee", work_package_id=ctx["package"].id)
        assert [i["item_number"] for i in listing["items"]] == ["MINE"]
        assert listing["can_manage"] is False
        other = item_list(db, actor=outsider, role="employee", work_package_id=ctx["package"].id)
        assert other["items"] == []
        # Team Lead sees everything
        tl_listing = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        assert len(tl_listing["items"]) == 2


def test_unauthorized_employee_cannot_update_file():
    with SessionLocal() as db:
        ctx = make_area(db, code="UNAUTH")
        team = ctx["team"]
        outsider = make_user(db, "evil.ft@nakshatech.com", "employee", "LiDAR")
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "U1", "production_user_id": team["prod"].id}])[0]
        db.flush()
        with pytest.raises(PermissionError):
            update_item(db, actor=outsider, role="employee", work_package_item_id=item.id,
                        changes={"is_active": False}, provided={"is_active"})
        with pytest.raises(PermissionError, match="Production employee assigned"):
            start_activity(db, actor=outsider, role="employee", work_package_item_id=item.id, stage="production")
        # QC stage strictly requires the QC assignee
        with pytest.raises(PermissionError, match="QC employee assigned"):
            start_activity(db, actor=team["prod"], role="employee", work_package_item_id=item.id, stage="qc")
        # activity completion belongs to the starter only
        activity = start_activity(db, actor=team["prod"], role="employee", work_package_item_id=item.id, stage="production")
        with pytest.raises(PermissionError):
            stop_activity(db, actor=team["qc"], activity_id=activity.id, status="completed")


def test_management_is_read_only():
    with SessionLocal() as db:
        ctx = make_area(db, code="MGMT")
        team = ctx["team"]
        management = make_user(db, "mgmt.ft@nakshatech.com", "management")
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "R1"}])[0]
        db.flush()
        listing = item_list(db, actor=management, role="management", work_package_id=ctx["package"].id)
        assert listing["can_manage"] is False and listing["can_deliver"] is False
        assert len(listing["items"]) == 1  # read-only visibility
        with pytest.raises(PermissionError, match="read-only"):
            add_items(db, actor=management, role="management", work_package_id=ctx["package"].id,
                      entries=[{"item_number": "NOPE"}])
        with pytest.raises(PermissionError, match="read-only"):
            start_activity(db, actor=management, role="management", work_package_item_id=item.id, stage="production")
        with pytest.raises(PermissionError, match="read-only"):
            deliver_item(db, actor=management, role="management", work_package_item_id=item.id)


def test_team_lead_can_personally_perform_production():
    with SessionLocal() as db:
        ctx = make_area(db, code="TLPRD")
        team = ctx["team"]
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "TL1", "production_user_id": team["prod"].id}])[0]
        db.flush()
        # TL (not the production assignee) may personally work — recorded under TL's own id
        activity = start_activity(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id, stage="production")
        assert activity.employee_user_id == team["tl"].id
        done = stop_activity(db, actor=team["tl"], activity_id=activity.id, status="completed",
                             quantity_completed=Decimal("10"), unit="km", files_completed=1)
        assert done.duration_seconds is not None and done.duration_seconds >= 0
        assert done.performed_role == "team_leader"


# ===========================================================================================
# production timing / duration / attribution
# ===========================================================================================

def test_production_start_end_timestamps_and_duration():
    with SessionLocal() as db:
        ctx = make_area(db, code="TIME")
        team = ctx["team"]
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "T1", "production_user_id": team["prod"].id}])[0]
        db.flush()
        started = datetime(2026, 10, 1, 9, 0, 0)
        activity = start_activity(db, actor=team["prod"], role="employee",
                                  work_package_item_id=item.id, stage="production", started_at=started)
        assert activity.started_at == started
        assert activity.ended_at is None and activity.duration_seconds is None
        ended = datetime(2026, 10, 1, 11, 30, 0)
        done = stop_activity(db, actor=team["prod"], activity_id=activity.id, status="completed",
                             quantity_completed=Decimal("10"), unit="km", files_completed=4, ended_at=ended)
        assert done.ended_at == ended
        assert done.duration_seconds == int((ended - started).total_seconds()) == 9000
        db.flush()
        listing = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        row = listing["items"][0]
        assert row["production_start"].startswith("2026-10-01T09:00:00")
        assert row["production_end"].startswith("2026-10-01T11:30:00")
        assert row["production_duration_seconds"] == 9000
        assert row["production_quantity"] == 10.0 and row["production_unit"] == "km"
        # V8.3: files completed is automatic for the file-level workflow (1 per file),
        # so a manually supplied count is intentionally ignored.
        assert row["production_files"] == 1
        assert row["production_status"] == "completed"


def test_overnight_session_duration():
    # 24-Sep-2026 18:07:02 -> 25-Sep-2026 10:19:18 must be 16h 12m 16s, not Excel #VALUE
    with SessionLocal() as db:
        ctx = make_area(db, code="NIGHT")
        team = ctx["team"]
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "N1", "production_user_id": team["prod"].id}])[0]
        db.flush()
        start = datetime(2026, 9, 24, 18, 7, 2)
        end = datetime(2026, 9, 25, 10, 19, 18)
        activity = start_activity(db, actor=team["prod"], role="employee",
                                  work_package_item_id=item.id, stage="production", started_at=start)
        done = stop_activity(db, actor=team["prod"], activity_id=activity.id, status="completed",
                             quantity_completed=Decimal("3"), files_completed=2, ended_at=end)
        assert done.duration_seconds == 58336  # 16h 12m 16s across midnight


def test_employee_files_attribution_and_aggregation():
    with SessionLocal() as db:
        ctx = make_area(db, code="ATTR")
        team = ctx["team"]
        created = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id, entries=[
            {"item_number": "P1", "production_user_id": team["prod"].id},
            {"item_number": "P2", "production_user_id": team["prod"].id},
        ])
        db.flush()
        for index, item in enumerate(created):
            activity = start_activity(db, actor=team["prod"], role="employee",
                                      work_package_item_id=item.id, stage="production")
            stop_activity(db, actor=team["prod"], activity_id=activity.id, status="completed",
                          quantity_completed=Decimal("5"), unit="km",
                          files_completed=3 if index == 0 else 2)
        totals = employee_file_totals(db, [ctx["package"].id])
        prod_row = next(t for t in totals if t["employee_user_id"] == team["prod"].id)
        # V8.3: automatic file counting — one completed file per completed file item.
        assert prod_row["files_completed"] == 2
        assert prod_row["production_completed"] == 2 and prod_row["production_pending"] == 0
        assert prod_row["quantity_completed"] == 10.0
        assert prod_row["unit"] == "km"
        # package aggregation
        agg = file_aggregates_for_packages(db, [ctx["package"].id])[ctx["package"].id]
        assert agg["files_expected"] == 2
        assert agg["files_production_done"] == 2
        assert agg["production_item_percent"] == 100.0


def test_employee_productivity_summary():
    with SessionLocal() as db:
        ctx = make_area(db, code="PROD")
        team = ctx["team"]
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "E1", "production_user_id": team["prod"].id}])[0]
        db.flush()
        started = datetime(2026, 10, 4, 9, 0, 0)
        ended = datetime(2026, 10, 4, 12, 0, 0)
        activity = start_activity(db, actor=team["prod"], role="employee",
                                  work_package_item_id=item.id, stage="production", started_at=started)
        stop_activity(db, actor=team["prod"], activity_id=activity.id, status="completed",
                      quantity_completed=Decimal("4"), unit="km", files_completed=6,
                      delay_category="System Malfunction", system_malfunction=False,
                      delay_remarks="System malfunction affected production speed today.",
                      ended_at=ended)
        rows = employee_productivity_rows(db, [ctx["package"].id])
        assert len(rows) == 1
        row = rows[0]
        assert row["employee_user_id"] == team["prod"].id
        assert row["files_completed"] == 1  # automatic (one per completed file)
        assert row["quantity_completed"] == 4.0
        assert row["unit"] == "km"
        assert row["production_seconds"] == 10800
        assert row["total_seconds"] == row["production_seconds"]
        assert "System Malfunction" in row["delay_category"]
        assert row["system_malfunction_count"] == 1


# ===========================================================================================
# buffer / overdue / delay
# ===========================================================================================

def test_target_date_retained_and_buffer_default_one_day():
    with SessionLocal() as db:
        ctx = make_area(db, code="BUF")
        package = ctx["package"]
        assert package.target_date == date(2026, 10, 15)
        assert buffer_days_for(package) == 1
        # production target is a SEPARATE additive field
        package.production_target_date = date(2026, 10, 20)
        db.flush()
        assert package.target_date == date(2026, 10, 15)  # never rewritten
        assert deadline_status(package, today=date(2026, 10, 21))["status"] == "buffer_day"
        # per-package override: target 20-Oct + 3 buffer days = buffer until 23-Oct
        package.production_buffer_days = 3
        assert deadline_status(package, today=date(2026, 10, 23))["status"] == "buffer_day"
        overdue = deadline_status(package, today=date(2026, 10, 24))
        assert overdue["status"] == "overdue" and overdue["days_overdue"] == 1


def test_deadline_states_on_target_buffer_overdue():
    with SessionLocal() as db:
        ctx = make_area(db, code="DL")
        package = ctx["package"]  # target 15-Oct, buffer until 16-Oct
        assert deadline_status(package, today=date(2026, 10, 14))["status"] == "on_track"
        assert deadline_status(package, today=date(2026, 10, 15))["status"] == "due_today"
        assert deadline_status(package, today=date(2026, 10, 16))["status"] == "buffer_day"
        late = deadline_status(package, today=date(2026, 10, 18))
        assert late["status"] == "overdue" and late["days_overdue"] == 2


def test_completion_on_target_in_buffer_and_late():
    with SessionLocal() as db:
        ctx = make_area(db, code="COMP")
        package = ctx["package"]
        assert deadline_status(package, completed_at=date(2026, 10, 14))["status"] == "completed_on_time"
        assert deadline_status(package, completed_at=date(2026, 10, 15))["status"] == "completed_on_time"
        in_buffer = deadline_status(package, completed_at=date(2026, 10, 16))
        assert in_buffer["status"] == "completed_in_buffer"
        late = deadline_status(package, completed_at=datetime(2026, 10, 18, 12, 0, 0))
        assert late["status"] == "completed_late" and late["days_late"] == 2


def test_delay_category_system_malfunction_and_affected_file():
    with SessionLocal() as db:
        ctx = make_area(db, code="DELAY")
        team = ctx["team"]
        created = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id, entries=[
            {"item_number": "BUILDING_045", "production_user_id": team["prod"].id},
            {"item_number": "OTHER_1", "production_user_id": team["prod"].id},
        ])
        db.flush()
        target = next(i for i in created if i.item_number == "BUILDING_045")
        activity = start_activity(db, actor=team["prod"], role="employee",
                                  work_package_item_id=target.id, stage="production")
        done = stop_activity(db, actor=team["prod"], activity_id=activity.id, status="completed",
                             quantity_completed=Decimal("1"), files_completed=1,
                             delay_category="Large / Complex Building Data",
                             affected_item_id=created[1].id,
                             delay_reason="High-density building data with complex roof geometry required additional processing.",
                             system_malfunction=False,
                             delay_remarks="Slower than usual but on schedule.")
        assert done.delay_category == "Large / Complex Building Data"
        assert done.affected_item_id == created[1].id
        assert done.system_malfunction is False
        # System Malfunction category forces the flag (recorded on the second file: a
        # finalized file cannot be re-opened, which is asserted separately)
        activity2 = start_activity(db, actor=team["prod"], role="employee",
                                   work_package_item_id=created[1].id, stage="production")
        done2 = stop_activity(db, actor=team["prod"], activity_id=activity2.id, status="completed",
                              quantity_completed=Decimal("1"), files_completed=1,
                              delay_category="System Malfunction", system_malfunction=False,
                              delay_remarks="System malfunction affected production speed today.")
        assert done2.system_malfunction is True
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        # the second file's production activity carries the System Malfunction flag
        other = next(i for i in row["items"] if i["item_number"] == "OTHER_1")
        assert other["system_malfunction"] is True


# ===========================================================================================
# QC / QA / Delivery
# ===========================================================================================

def _ready_for_review(db, ctx, name: str, *, prepare: str | None = None):
    """Create a file assigned to Production/QC/QA.

    ``prepare`` advances the V8.3 workflow gates so the requested stage can start:
    "qc" = production completed, "qa" = production completed + QC passed.
    """
    team = ctx["team"]
    item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                     entries=[{"item_number": f"R-{name}",
                               "production_user_id": team["prod"].id,
                               "qc_user_id": team["qc"].id,
                               "qa_user_id": team["qa"].id}])[0]
    db.flush()
    if prepare in {"qc", "qa"}:
        production = start_activity(db, actor=team["prod"], role="employee",
                                    work_package_item_id=item.id, stage="production")
        stop_activity(db, actor=team["prod"], activity_id=production.id, status="completed",
                      quantity_completed=Decimal("1"), unit=item.planned_unit)
    if prepare == "qa":
        qc = start_activity(db, actor=team["qc"], role="employee",
                            work_package_item_id=item.id, stage="qc")
        stop_activity(db, actor=team["qc"], activity_id=qc.id, status="passed")
    return team, item


def test_qc_start_end_duration_pass():
    with SessionLocal() as db:
        ctx = make_area(db, code="QCP")
        team, item = _ready_for_review(db, ctx, "qcp", prepare="qc")
        started = datetime(2026, 10, 2, 9, 0, 0)
        activity = start_activity(db, actor=team["qc"], role="employee",
                                  work_package_item_id=item.id, stage="qc", started_at=started)
        assert activity.started_at == started and activity.performed_role == "qc"
        ended = datetime(2026, 10, 2, 9, 45, 0)
        done = stop_activity(db, actor=team["qc"], activity_id=activity.id, status="passed",
                             remarks="Checked", ended_at=ended)
        assert done.duration_seconds == 2700
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)["items"][0]
        assert row["qc_status"] == "passed" and row["qc_duration_seconds"] == 2700
        assert row["status"] == "qc_passed"


def test_qc_reject_preserves_history_then_pass():
    with SessionLocal() as db:
        ctx = make_area(db, code="QCR")
        team, item = _ready_for_review(db, ctx, "qcr", prepare="qc")
        first = start_activity(db, actor=team["qc"], role="employee", work_package_item_id=item.id, stage="qc")
        stop_activity(db, actor=team["qc"], activity_id=first.id, status="rejected",
                      remarks="Misaligned tiles")
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)["items"][0]
        assert row["qc_status"] == "rejected" and row["status"] == "qc_rejected"
        second = start_activity(db, actor=team["qc"], role="employee", work_package_item_id=item.id, stage="qc")
        stop_activity(db, actor=team["qc"], activity_id=second.id, status="passed", remarks="Fixed")
        history = item_history(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id)
        qc_rows = [h for h in history if h["stage"] == "qc"]
        assert [h["status"] for h in qc_rows] == ["rejected", "passed"]  # old attempt never overwritten


def test_qa_start_end_duration_and_reject_rework():
    with SessionLocal() as db:
        ctx = make_area(db, code="QAR")
        team, item = _ready_for_review(db, ctx, "qar", prepare="qa")
        started = datetime(2026, 10, 3, 14, 0, 0)
        activity = start_activity(db, actor=team["qa"], role="employee",
                                  work_package_item_id=item.id, stage="qa", started_at=started)
        assert activity.started_at == started
        ended = datetime(2026, 10, 3, 15, 15, 0)
        done = stop_activity(db, actor=team["qa"], activity_id=activity.id, status="rework",
                             remarks="Attributes need correction", ended_at=ended)
        assert done.duration_seconds == 4500
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)["items"][0]
        assert row["qa_status"] == "rejected" or row["status"] == "qa_rejected"
        history = item_history(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id)
        qa_rows = [h for h in history if h["stage"] == "qa"]
        assert [h["status"] for h in qa_rows] == ["rework"]  # history preserved, nothing overwritten
        assert row["status"] == "qa_rejected"
        # QA rejection requires remarks
        second = start_activity(db, actor=team["qa"], role="employee", work_package_item_id=item.id, stage="qa")
        with pytest.raises(ValueError, match="status"):
            stop_activity(db, actor=team["qa"], activity_id=second.id)


def test_delivery_after_qa_pass():
    with SessionLocal() as db:
        ctx = make_area(db, code="DEL")
        team, item = _ready_for_review(db, ctx, "del", prepare="qa")
        # QA must pass before delivery
        with pytest.raises(ValueError, match="QA must pass"):
            deliver_item(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id)
        qa_activity = start_activity(db, actor=team["qa"], role="employee", work_package_item_id=item.id, stage="qa")
        stop_activity(db, actor=team["qa"], activity_id=qa_activity.id, status="passed")
        activity = deliver_item(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id,
                                remarks="Sent to client", reference="DLV-001")
        assert activity.stage == "delivery" and activity.status == "delivered"
        assert activity.ended_at is not None
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)["items"][0]
        assert row["delivery_status"] == "delivered" and row["delivery_at"] is not None
        # non-authorized employee cannot deliver
        outsider = make_user(db, "nodelivery.ft@nakshatech.com", "employee", "LiDAR")
        item2 = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                          entries=[{"item_number": "D2", "qa_user_id": team["qa"].id}])[0]
        db.flush()
        with pytest.raises(PermissionError, match="Team Lead or Project Manager"):
            deliver_item(db, actor=outsider, role="employee", work_package_item_id=item2.id)


def test_full_chain_rollups():
    """One file through Production -> QC -> QA -> Delivery drives every rollup."""
    with SessionLocal() as db:
        ctx = make_area(db, code="CHAIN")
        team = ctx["team"]
        item = add_items(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id,
                         entries=[{"item_number": "C1", "production_user_id": team["prod"].id,
                                   "qc_user_id": team["qc"].id, "qa_user_id": team["qa"].id}])[0]
        db.flush()
        p = start_activity(db, actor=team["prod"], role="employee", work_package_item_id=item.id, stage="production")
        stop_activity(db, actor=team["prod"], activity_id=p.id, status="completed",
                      quantity_completed=Decimal("10"), unit="km", files_completed=1)
        q = start_activity(db, actor=team["qc"], role="employee", work_package_item_id=item.id, stage="qc")
        stop_activity(db, actor=team["qc"], activity_id=q.id, status="passed")
        a = start_activity(db, actor=team["qa"], role="employee", work_package_item_id=item.id, stage="qa")
        stop_activity(db, actor=team["qa"], activity_id=a.id, status="passed")
        deliver_item(db, actor=team["tl"], role=TL_ROLE, work_package_item_id=item.id)
        agg = file_aggregates_for_packages(db, [ctx["package"].id])[ctx["package"].id]
        assert agg["files_expected"] == 1
        assert agg["files_production_done"] == 1
        assert agg["files_qc_passed"] == 1
        assert agg["files_qa_passed"] == 1
        assert agg["files_delivered"] == 1
        assert agg["qc_item_percent"] == agg["delivery_item_percent"] == 100.0
        # package completion feeds the deadline (completed on time before 15-Oct)
        row = item_list(db, actor=team["tl"], role=TL_ROLE, work_package_id=ctx["package"].id)
        assert row["deadline"]["target_date"] == "2026-10-15"


# ===========================================================================================
# project Excel workbook
# ===========================================================================================

def _workbook_for(db, actor, role, project_id):
    content, filename = build_production_workbook(
        db, report_type="project_workbook", actor=actor, role=role, project_id=project_id)
    from openpyxl import load_workbook
    return load_workbook(BytesIO(content), data_only=True), filename


def test_workbook_exact_project_and_sheet_names():
    with SessionLocal() as db:
        ctx_a = make_area(db, code="WBA")
        item = add_items(db, actor=ctx_a["team"]["tl"], role=TL_ROLE, work_package_id=ctx_a["package"].id,
                         entries=[{"item_number": "WA_001", "production_user_id": ctx_a["team"]["prod"].id,
                                   "qc_user_id": ctx_a["team"]["qc"].id, "qa_user_id": ctx_a["team"]["qa"].id}])[0]
        db.flush()
        act = start_activity(db, actor=ctx_a["team"]["prod"], role="employee",
                             work_package_item_id=item.id, stage="production")
        stop_activity(db, actor=ctx_a["team"]["prod"], activity_id=act.id, status="completed",
                      quantity_completed=Decimal("10"), unit="km", files_completed=3)
        # second project that must NOT appear in project A's workbook
        ctx_b = make_area(db, code="WBB")
        db.flush()

        management = make_user(db, "wb.mgmt@nakshatech.com", "management")
        workbook, filename = _workbook_for(db, management, "management", ctx_a["project"].id)
        assert workbook.sheetnames == [
            "AREA MASTER", "FILE ACTIVITY", "EMPLOYEE PRODUCTIVITY",
            "ACTIVITY HISTORY", "LEGACY TILE ACTIVITY",
        ]
        assert f"FT-WBA" in filename

        area = workbook["AREA MASTER"]
        headers = [cell.value for cell in area[1]]
        assert headers == AREA_MASTER_HEADERS
        assert len(headers) == 26
        codes = [row[1] for row in area.iter_rows(min_row=2, values_only=True)]
        assert "AR-WBA" in codes
        assert "AR-WBB" not in codes  # only the selected project

        file_sheet = workbook["FILE ACTIVITY"]
        file_headers = [cell.value for cell in file_sheet[1]]
        assert file_headers == FILE_ACTIVITY_HEADERS
        file_numbers = [row[4] for row in file_sheet.iter_rows(min_row=2, values_only=True)]
        assert "WA_001" in file_numbers

        prod_sheet = workbook["EMPLOYEE PRODUCTIVITY"]
        prod_headers = [cell.value for cell in prod_sheet[1]]
        assert prod_headers == EMPLOYEE_PRODUCTIVITY_HEADERS
        employees = [row[0] for row in prod_sheet.iter_rows(min_row=2, values_only=True)]
        assert any(name and "prod" in str(name) for name in employees)
        # worker rows carry the automatically counted completed files (COMPLETED FILES column)
        completed = [row[8] for row in prod_sheet.iter_rows(min_row=2, values_only=True)]
        assert any(value == 1 for value in completed)


def test_workbook_requires_visible_project():
    with SessionLocal() as db:
        management = make_user(db, "wb2.mgmt@nakshatech.com", "management")
        with pytest.raises(ValueError, match="Select a project"):
            build_production_workbook(db, report_type="project_workbook",
                                      actor=management, role="management", project_id=None)
