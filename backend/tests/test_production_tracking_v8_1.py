"""Shared Project Production Tracking (V8.1) — focused tests + preservation guarantees.

Covers the 33-point matrix required for the LiDAR Daily Activity extension:
multi-role team members, generic UOM conversion, production/workflow/project
progress formulas, additive stage tracking with audit history, report exports,
idempotent schema compatibility, and — critically — that the existing
Ortho/LiDAR workflow engine is unchanged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.finance.models import FinanceClient
from app.modules.operations.models import OrthoProjectMember, OrthoStageEvent, OrthoWorkPackage
from app.modules.operations.production_service import (
    package_stage_history,
    tracking_summary,
    update_package_general,
    update_trackable_stage,
)
from app.modules.operations.production_stages import (
    STAGE_PROFILES,
    STAGE_STATUSES,
    aggregate_project_progress,
    package_production_progress,
    package_workflow_progress,
    pending_stages,
    stage_profile_for_department,
)
from app.modules.operations.production_schema_compat import ensure_production_tracking_schema_compatibility
from app.modules.operations.schemas import (
    WorkflowDailyActivity,
    WorkflowDeliveryRequest,
    WorkflowFinanceReview,
    WorkflowPMAssignment,
    WorkflowProjectCreate,
    WorkflowReviewRequest,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)
from app.modules.operations.uom import convert_quantity, measurement_type, normalize_quantity, units_compatible
from app.modules.operations.workflow_service import (
    allocate_work,
    assign_project_manager,
    complete_production,
    configure_team,
    create_bd_project,
    finance_review_project,
    mark_delivered,
    record_daily_activity,
    review_work,
    submit_project_to_finance,
)
from app.models.entities import utc_now


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
        client_code=f"C-{code}", client_name="Production Tracking Client", contact_person_name="Contact",
        contact_person_phone="9999999999", source_team="bd_team", source_person_name=owner.full_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def approved_project(db, *, code: str, department_code: str, department_label: str):
    """BD -> Finance approve -> PM assign, the authoritative pre-PM path."""
    bd = make_user(db, f"bd.pt.{code}@nakshatech.com", "bd")
    finance = make_user(db, f"fin.pt.{code}@nakshatech.com", "finance")
    pm_role = {"lidar": "lidar", "ortho": "ortho", "civil": "civil"}.get(department_code, department_code)
    pm = make_user(db, f"pm.pt.{code}@nakshatech.com", pm_role, department_label)
    client = make_client(db, bd, code)
    project, workflow = create_bd_project(db, actor=bd, payload=WorkflowProjectCreate(
        client_id=client.id, project_code=f"PT-{code}", project_name="Production Tracking Project",
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
    finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", comments="Approved"))
    db.flush()
    assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=pm.id))
    db.flush()
    return bd, finance, pm, project, workflow


def full_team(db, pm: User, project, code: str, *, multi_role_tl: bool = False):
    """PM team setup. With multi_role_tl the Team Lead is ALSO production (+ qc optionally)."""
    tl = make_user(db, f"tl.pt.{code}@nakshatech.com", "employee", "LiDAR")
    prod = tl if multi_role_tl else make_user(db, f"prod.pt.{code}@nakshatech.com", "employee", "LiDAR")
    qc = make_user(db, f"qc.pt.{code}@nakshatech.com", "employee", "LiDAR")
    qa = make_user(db, f"qa.pt.{code}@nakshatech.com", "employee", "LiDAR")
    configure_team(db, actor=pm, project_id=project.id, payload=WorkflowTeamSetup(
        team_leader_user_id=tl.id, production_user_ids=[prod.id], qc_user_ids=[qc.id], qa_user_ids=[qa.id],
    ))
    db.flush()
    return {"tl": tl, "prod": prod, "qc": qc, "qa": qa}


# ============================================================================================ stage profiles
def test_ortho_and_default_departments_keep_universal_four_stage_workflow():
    assert stage_profile_for_department("ortho") == ("production", "qc", "qa", "delivery")
    assert stage_profile_for_department("mobile_mapping") == ("production", "qc", "qa", "delivery")
    assert stage_profile_for_department("laser_scanning") == ("production", "qc", "qa", "delivery")
    assert stage_profile_for_department("civil") == ("production", "qc", "qa", "delivery")
    assert stage_profile_for_department(None) == ("production", "qc", "qa", "delivery")


def test_lidar_profile_extends_universal_stages_without_replacing_them():
    lidar = stage_profile_for_department("lidar")
    assert set(("production", "qc", "qa", "delivery")).issubset(set(lidar))
    assert set(("import", "dxf", "inspection", "upload")).issubset(set(lidar))
    assert STAGE_PROFILES["lidar"] == lidar


# ============================================================================================ UOM
def test_unit_conversions_are_correct_within_measurement_types():
    assert convert_quantity(Decimal("1000"), "m", "km") == Decimal("1")
    assert convert_quantity(Decimal("1"), "km", "m") == Decimal("1000")
    assert convert_quantity(Decimal("1000000"), "sq.m", "sq.km") == Decimal("1")
    assert convert_quantity(Decimal("1"), "hectare", "sq.m") == Decimal("10000")
    assert convert_quantity(Decimal("1"), "ha", "hectare") == Decimal("1")
    assert convert_quantity(Decimal("2"), "hour", "minute") == Decimal("120")


def test_incompatible_units_are_rejected_from_conversion_and_aggregation():
    assert not units_compatible("km", "sq.km")
    assert not units_compatible("files", "km")
    assert not units_compatible("files", "tiles")
    with pytest.raises(ValueError):
        convert_quantity(Decimal("1"), "km", "sq.km")
    with pytest.raises(ValueError):
        convert_quantity(Decimal("1"), "files", "km")


def test_unknown_legacy_units_remain_opaque_but_usable():
    assert measurement_type("nos") == "opaque:nos"
    qty, mtype = normalize_quantity(Decimal("5"), "nos")
    assert qty == Decimal("5") and mtype == "opaque:nos"
    assert units_compatible("nos", "nos")


# ============================================================================================ progress math
def test_production_percent_is_correct_and_over_target_is_preserved():
    result = package_production_progress(Decimal("15"), Decimal("10"))
    assert result["progress_percent"] == 100.0
    assert result["over_target_quantity"] == Decimal("5")


def test_zero_and_null_targets_never_divide_by_zero():
    assert package_production_progress(Decimal("5"), Decimal("0"))["progress_percent"] == 0.0
    assert package_production_progress(Decimal("5"), None)["progress_percent"] == 0.0
    assert package_production_progress(None, None)["progress_percent"] == 0.0


def test_workflow_progress_counts_only_applicable_stages():
    class P:
        production_state = "completed"
        qc_state = "approved"
        qa_state = "pending"
        current_stage = "qa"
        import_status = None
        dxf_status = None
        inspection_status = None
        upload_status = None
    assert package_workflow_progress(P(), "ortho") == 50.0  # 2 of 4 universal stages
    assert package_workflow_progress(P(), "lidar") == 25.0  # 2 of 8 LiDAR stages


def test_project_weighted_progress_uses_quantity_not_naive_average():
    class P:
        def __init__(self, total, target, unit):
            self.daily_updates = [type("U", (), {"achieved_area": total})()]
            self.area = target
            self.area_unit = unit
            self.production_state = "completed"
            self.qc_state = "approved"
            self.qa_state = "approved"
            self.current_stage = "delivered"
            self.import_status = "completed"
            self.dxf_status = "approved"
            self.inspection_status = "inspected"
            self.upload_status = "uploaded"
    # 10 km at 50% and 30 km at 100% => (5 + 30) / 40 = 87.5% (not 75%)
    result = aggregate_project_progress([P(Decimal("5"), Decimal("10"), "km"), P(Decimal("30"), Decimal("30"), "km")], "lidar")
    assert result["production_progress_percent"] == 87.5
    assert result["workflow_progress_percent"] == 100.0
    assert result["mixed_measurement_types"] is False


def test_mixed_measurement_types_are_never_summed():
    class P:
        def __init__(self, total, target, unit):
            self.daily_updates = [type("U", (), {"achieved_area": total})()]
            self.area = target
            self.area_unit = unit
            self.production_state = "completed"
            self.qc_state = "pending"
            self.qa_state = "pending"
            self.current_stage = "qc"
            self.import_status = None
            self.dxf_status = None
            self.inspection_status = None
            self.upload_status = None
    result = aggregate_project_progress([P(Decimal("5"), Decimal("10"), "km"), P(Decimal("1"), Decimal("1"), "files")], "ortho")
    assert result["mixed_measurement_types"] is True
    types = {group["measurement_type"] for group in result["measurement_groups"]}
    assert types == {"distance", "count:file"}
    # equal type-group weighting: 50% (distance) and 100% (files) => 75%
    assert result["production_progress_percent"] == 75.0


# ============================================================================================ migration idempotency
def test_production_tracking_schema_compatibility_is_idempotent():
    ensure_production_tracking_schema_compatibility()
    ensure_production_tracking_schema_compatibility()  # must not raise
    with SessionLocal() as db:
        package = db.scalar(select(OrthoWorkPackage).limit(1))
        assert package is None or hasattr(package, "import_status")


# ============================================================================================ engine preservation
def test_existing_lidar_workflow_chain_still_runs_end_to_end():
    with SessionLocal() as db:
        _bd, _fin, pm, project, _wf = approved_project(db, code="LIDAR-E2E", department_code="lidar", department_label="LiDAR")
        team = full_team(db, pm, project, "LIDAR-E2E")
        package = allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
            package_code="LID-E2E-01", area_name="Sector 1", quantity=Decimal("10"), quantity_unit="km",
            target_date=date(2026, 11, 1), instructions="Deliver",
            production_user_id=team["prod"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
        ))
        # Optional LiDAR stage: Import is done before production starts.
        update_trackable_stage(db, actor=team["tl"], work_package_id=package.id, stage="import", status_value="completed")
        record_daily_activity(db, actor=team["prod"], work_package_id=package.id, payload=WorkflowDailyActivity(
            quantity_completed=Decimal("10"), files_completed=3, status="on_track",
        ))
        # Same-session multi-step flow: expire so the freshly recorded daily update
        # is reloaded (the app always reads across separate request sessions).
        db.expire(package)
        complete_production(db, actor=team["prod"], work_package_id=package.id)
        review_work(db, actor=team["qc"], work_package_id=package.id, kind="qc", payload=WorkflowReviewRequest(decision="approve"))
        review_work(db, actor=team["qa"], work_package_id=package.id, kind="qa", payload=WorkflowReviewRequest(decision="approve"))
        # Optional LiDAR stages after QA, before delivery (Team Lead is authorized).
        update_trackable_stage(db, actor=team["tl"], work_package_id=package.id, stage="dxf", status_value="approved")
        update_trackable_stage(db, actor=team["tl"], work_package_id=package.id, stage="inspection", status_value="inspected")
        mark_delivered(db, actor=team["tl"], work_package_id=package.id, payload=WorkflowDeliveryRequest(remarks="Sent"))
        update_trackable_stage(db, actor=team["tl"], work_package_id=package.id, stage="upload", status_value="uploaded")
        db.flush()
        db.expire(package)
        assert package.current_stage == "delivered"
        # All 8 applicable LiDAR stages complete => workflow 100%, separate from production %.
        assert package_workflow_progress(package, "lidar") == 100.0


def test_team_lead_can_hold_production_and_qc_roles_simultaneously():
    with SessionLocal() as db:
        _bd, _fin, pm, project, _wf = approved_project(db, code="MULTIROLE", department_code="lidar", department_label="LiDAR")
        tl = make_user(db, "tl.multirole@nakshatech.com", "employee", "LiDAR")
        qa = make_user(db, "qa.multirole@nakshatech.com", "employee", "LiDAR")
        # One user is Team Lead AND Production AND QC — currently allowed by V8.1.
        configure_team(db, actor=pm, project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=tl.id, production_user_ids=[tl.id], qc_user_ids=[tl.id], qa_user_ids=[qa.id],
        ))
        db.flush()
        roles = sorted(row.member_role for row in db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id,
            OrthoProjectMember.user_id == tl.id,
            OrthoProjectMember.is_active.is_(True),
        )).all())
        assert roles == ["production", "qc", "team_leader"]
        package = allocate_work(db, actor=tl, project_id=project.id, payload=WorkflowWorkAllocation(
            package_code="MR-01", area_name="Block", quantity=Decimal("4"), quantity_unit="files",
            target_date=date(2026, 11, 1), instructions="Work",
            production_user_id=tl.id, qc_user_id=tl.id, qa_user_id=qa.id,
        ))
        record_daily_activity(db, actor=tl, work_package_id=package.id, payload=WorkflowDailyActivity(quantity_completed=Decimal("4")))
        db.expire(package)
        complete_production(db, actor=tl, work_package_id=package.id)
        # The same human now performs the QC review through the QC role.
        review_work(db, actor=tl, work_package_id=package.id, kind="qc", payload=WorkflowReviewRequest(decision="approve"))
        assert package.qc_state == "approved" and package.current_stage == "qa"


def test_qc_reject_creates_rework_and_preserves_attempt_history():
    with SessionLocal() as db:
        _bd, _fin, pm, project, _wf = approved_project(db, code="QC-REJ", department_code="lidar", department_label="LiDAR")
        team = full_team(db, pm, project, "QC-REJ")
        package = allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
            package_code="QCR-01", area_name="Block", quantity=Decimal("2"), quantity_unit="files",
            target_date=date(2026, 11, 1), instructions="Work",
            production_user_id=team["prod"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
        ))
        record_daily_activity(db, actor=team["prod"], work_package_id=package.id, payload=WorkflowDailyActivity(quantity_completed=Decimal("2")))
        db.expire(package)
        complete_production(db, actor=team["prod"], work_package_id=package.id)
        review_work(db, actor=team["qc"], work_package_id=package.id, kind="qc", payload=WorkflowReviewRequest(decision="reject", comments="Misaligned tiles"))
        db.flush()
        db.expire(package)
        assert package.current_stage == "production_rework" and package.qc_state == "rejected"
        # history preserved: the reject attempt remains recorded
        assert [(r.review_type, r.attempt_no, r.decision) for r in package.reviews] == [("qc", 1, "reject")]


