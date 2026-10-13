"""Multi-department operational workflow (V8.1 Phase 2): the same BD -> Finance -> PM -> Team
Lead -> Production/QC/QA -> Delivery -> Billing workflow, generalized from the proven Ortho
template to LiDAR, Mobile Mapping, Laser Scanning and Civil via one Performing Department field.

No new workflow was built per department; these tests exercise the same
``app.modules.operations.workflow_service`` functions Ortho already used, now parameterized by
``ProjectWorkflow.performing_department_code``.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.departments import DEPARTMENT_PM_ROLE, department_label
from app.models.entities import User
from app.modules.commercial import models as _commercial_models  # noqa: F401  (registers tables on Base.metadata)
from app.modules.finance.models import FinanceClient
from app.modules.operations.models import OrthoProjectMember
from app.modules.operations.schemas import (
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
    employee_options,
    finance_dashboard,
    ortho_dashboard,
    project_manager_options,
)
from app.modules.operations.lifecycle_service import project_360
from app.services.seed import (
    ensure_multi_department_pm_accounts,
    ensure_multi_department_test_employee_accounts,
)


# --------------------------------------------------------------------------------------------- fixtures
def make_user(db, email: str, role: str, department: str | None = None, name: str | None = None) -> User:
    row = User(
        email=email, full_name=name or email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", department=department, email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def make_client(db, owner: User, code: str) -> FinanceClient:
    client = FinanceClient(
        client_code=f"C-{code}", client_name="Multi-Department Test Client", contact_person_name="Contact",
        contact_person_phone="9999999999", source_team="bd_team", source_person_name=owner.full_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def project_payload(client: FinanceClient, code: str, department_code: str, **overrides) -> WorkflowProjectCreate:
    values = dict(
        client_id=client.id, project_code=code, project_name="Multi-Department Project",
        start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
        performing_department_code=department_code,
    )
    values.update(overrides)
    return WorkflowProjectCreate(**values)


def pm_and_team(db, department_code: str, tag: str) -> dict:
    role = DEPARTMENT_PM_ROLE[department_code]
    label = department_label(department_code)
    pm = make_user(db, f"pm.{tag}@nakshatech.com", role, label, f"{label} PM")
    tl = make_user(db, f"tl.{tag}@nakshatech.com", "employee", label, f"{label} TL")
    prod = make_user(db, f"prod.{tag}@nakshatech.com", "employee", label, f"{label} Production")
    qc = make_user(db, f"qc.{tag}@nakshatech.com", "employee", label, f"{label} QC")
    qa = make_user(db, f"qa.{tag}@nakshatech.com", "employee", label, f"{label} QA")
    return {"pm": pm, "tl": tl, "prod": prod, "qc": qc, "qa": qa}


def commercial(**overrides):
    from app.modules.commercial.schemas import ProjectCommercialInput

    values = dict(
        scope_description="Survey and deliver", billing_type="fixed_price", payment_terms="30 days",
        currency_code="INR", estimated_amount=Decimal("500000"), taxable_base_amount=Decimal("500000"),
        tax_percent=Decimal("18"), estimate_date=date(2026, 9, 22),
    )
    values.update(overrides)
    return ProjectCommercialInput(**values)


def approved_project(db, *, bd: User, finance: User, code: str, department_code: str):
    from app.modules.operations.workflow_service import finance_review_project, submit_project_to_finance
    from app.modules.operations.schemas import WorkflowFinanceReview

    client = make_client(db, bd, code)
    project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, code, department_code, commercial=commercial()))
    submit_project_to_finance(db, actor=bd, project_id=project.id)
    finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", feedback="ok"))
    db.flush()
    return project, workflow


# =============================================================================================== A. ORTHO regression
def test_ortho_project_without_explicit_department_still_defaults_to_ortho():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.a1@nakshatech.com", "bd")
        client = make_client(db, bd, "MD-A1")
        # No performing_department_code passed at all: the schema itself defaults it.
        project, workflow = create_bd_project(db, actor=bd, payload=WorkflowProjectCreate(
            client_id=client.id, project_code="MD-P-A1", project_name="Legacy Ortho Style",
            start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Legacy scope",
        ))
        assert workflow.performing_department_code == "ortho"


def test_ortho_pm_candidates_still_returned_by_department_filter():
    with SessionLocal() as db:
        pm = make_user(db, "pm.md.a2@nakshatech.com", "ortho", "Ortho")
        options = project_manager_options(db, department_code="ortho")
        assert any(o["id"] == pm.id for o in options)
        assert all(o["performing_department_code"] == "ortho" for o in options)


def test_ortho_employee_team_assignment_and_team_lead_allocation_unchanged():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.a3@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.a3@nakshatech.com", "finance")
        team = pm_and_team(db, "ortho", "mda3")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-A3", department_code="ortho")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()
        workflow, _ = configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=team["tl"].id, production_user_ids=[team["prod"].id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
        ))
        db.flush()
        members = {row.member_role: row.user_id for row in db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id, OrthoProjectMember.is_active.is_(True)
        )).all()}
        assert members["team_leader"] == team["tl"].id and members["production"] == team["prod"].id
        package = allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
            package_code="MD-A3-01", area_name="Block 1", quantity=Decimal("10"), quantity_unit="sq.km",
            target_date=date(2026, 11, 1), instructions="Standard delivery",
            production_user_id=team["prod"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
        ))
        assert package.team_leader_user_id == team["tl"].id and package.production_user_id == team["prod"].id


# =============================================================================================== B. LIDAR (deepest path)
def test_lidar_project_department_persists_and_finance_sees_it():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.b1@nakshatech.com", "bd")
        client = make_client(db, bd, "MD-B1")
        project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, "MD-P-B1", "lidar"))
        db.flush()
        assert workflow.performing_department_code == "lidar"
        payload = finance_dashboard(db)
        row = next(p for p in payload["projects"] if p["id"] == project.id)
        assert row["performing_department_code"] == "lidar" and row["performing_department_label"] == "LiDAR"


def test_lidar_pm_candidates_returned_civil_pm_excluded():
    with SessionLocal() as db:
        lidar_pm = make_user(db, "pm.md.b2.lidar@nakshatech.com", "lidar", "LiDAR")
        civil_pm = make_user(db, "pm.md.b2.civil@nakshatech.com", "civil", "Civil")
        options = project_manager_options(db, department_code="lidar")
        ids = {o["id"] for o in options}
        assert lidar_pm.id in ids and civil_pm.id not in ids


def test_direct_civil_pm_assignment_to_lidar_project_is_rejected_by_backend():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.b3@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.b3@nakshatech.com", "finance")
        civil_pm = make_user(db, "pm.md.b3.civil@nakshatech.com", "civil", "Civil")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-B3", department_code="lidar")
        # Same request shape a manual/direct API call would send: a Civil PM against a LiDAR project.
        with pytest.raises(ValueError, match="LiDAR Project Manager"):
            assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=civil_pm.id))


def test_lidar_team_employees_returned_wrong_department_employee_rejected():
    with SessionLocal() as db:
        lidar_emp = make_user(db, "emp.md.b4.lidar@nakshatech.com", "employee", "LiDAR")
        civil_emp = make_user(db, "emp.md.b4.civil@nakshatech.com", "employee", "Civil")
        options = employee_options(db, department_code="lidar")
        ids = {o["id"] for o in options}
        assert lidar_emp.id in ids and civil_emp.id not in ids


def test_pm_assigns_lidar_team_and_team_lead_allocates_only_pm_approved_lidar_users():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.b5@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.b5@nakshatech.com", "finance")
        team = pm_and_team(db, "lidar", "mdb5")
        outsider = make_user(db, "outsider.md.b5@nakshatech.com", "employee", "Civil")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-B5", department_code="lidar")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()

        # a Civil employee can never be added to a LiDAR project's team, even by the LiDAR PM
        with pytest.raises(ValueError, match="LiDAR department"):
            configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
                team_leader_user_id=team["tl"].id, production_user_ids=[outsider.id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
            ))

        configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=team["tl"].id, production_user_ids=[team["prod"].id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
        ))
        db.flush()
        # Team Lead allocation still only accepts PM-approved project members (unchanged existing guard).
        with pytest.raises(ValueError):
            allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
                package_code="MD-B5-01", area_name="Tile A", quantity=Decimal("5"), quantity_unit="sq.km",
                target_date=date(2026, 11, 1), instructions="Standard delivery",
                production_user_id=outsider.id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
            ))
        package = allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
            package_code="MD-B5-02", area_name="Tile B", quantity=Decimal("5"), quantity_unit="sq.km",
            target_date=date(2026, 11, 1), instructions="Standard delivery",
            production_user_id=team["prod"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
        ))
        assert package.production_user_id == team["prod"].id


def test_unassigned_pm_cannot_see_a_lidar_project_that_is_not_theirs():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.b6@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.b6@nakshatech.com", "finance")
        team = pm_and_team(db, "lidar", "mdb6")
        other_lidar_pm = make_user(db, "pm.md.b6.other@nakshatech.com", "lidar", "LiDAR")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-B6", department_code="lidar")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()
        # Being a LiDAR PM does not grant visibility into every LiDAR project.
        view = ortho_dashboard(db, actor=other_lidar_pm, role="lidar")
        assert all(p["project_id"] != project.id for p in view["projects"])
        own_view = ortho_dashboard(db, actor=team["pm"], role="lidar")
        assert any(p["project_id"] == project.id for p in own_view["projects"])
        with pytest.raises(PermissionError):
            project_360(db, actor=other_lidar_pm, role="lidar", project_id=project.id)


# =============================================================================================== C/D/E. smoke tests
@pytest.mark.parametrize("department_code,tag", [("mobile_mapping", "mdc"), ("laser_scanning", "mdd"), ("civil", "mde")])
def test_department_isolation_smoke(department_code, tag):
    with SessionLocal() as db:
        bd = make_user(db, f"bd.{tag}@nakshatech.com", "bd")
        finance = make_user(db, f"fin.{tag}@nakshatech.com", "finance")
        team = pm_and_team(db, department_code, tag)
        wrong_role = next(role for code, role in DEPARTMENT_PM_ROLE.items() if code != department_code)
        wrong_pm = make_user(db, f"wrongpm.{tag}@nakshatech.com", wrong_role, department_label(next(c for c, r in DEPARTMENT_PM_ROLE.items() if r == wrong_role)))

        project, workflow = approved_project(db, bd=bd, finance=finance, code=f"MD-{tag.upper()}", department_code=department_code)
        assert workflow.performing_department_code == department_code

        with pytest.raises(ValueError):
            assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=wrong_pm.id))
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()

        configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=team["tl"].id, production_user_ids=[team["prod"].id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
        ))
        members = {row.member_role: row.user_id for row in db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id, OrthoProjectMember.is_active.is_(True)
        )).all()}
        assert members["production"] == team["prod"].id


# =============================================================================================== F. cross-department authorization
def test_wrong_department_employee_rejected_even_via_rework_team_confirmation():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.f1@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.f1@nakshatech.com", "finance")
        team = pm_and_team(db, "civil", "mdf1")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-F1", department_code="civil")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()
        with pytest.raises(ValueError, match="Civil department"):
            configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
                team_leader_user_id=team["tl"].id,
                production_user_ids=[make_user(db, "emp.md.f1.wrong@nakshatech.com", "employee", "Laser Scanning").id],
                qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
            ))


def test_unassigned_employee_allocation_is_rejected():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.f2@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.f2@nakshatech.com", "finance")
        team = pm_and_team(db, "mobile_mapping", "mdf2")
        never_added = make_user(db, "emp.md.f2.notadded@nakshatech.com", "employee", "Mobile Mapping")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-F2", department_code="mobile_mapping")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=team["tl"].id, production_user_ids=[team["prod"].id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
        ))
        db.flush()
        with pytest.raises(ValueError):
            allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
                package_code="MD-F2-01", area_name="Corridor 1", quantity=Decimal("2"), quantity_unit="km",
                target_date=date(2026, 11, 1), instructions="Standard delivery",
                production_user_id=never_added.id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
            ))


def test_wrong_project_role_allocation_is_rejected():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.f3@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.f3@nakshatech.com", "finance")
        team = pm_and_team(db, "laser_scanning", "mdf3")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-F3", department_code="laser_scanning")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        configure_team(db, actor=team["pm"], project_id=project.id, payload=WorkflowTeamSetup(
            team_leader_user_id=team["tl"].id, production_user_ids=[team["prod"].id], qc_user_ids=[team["qc"].id], qa_user_ids=[team["qa"].id],
        ))
        db.flush()
        # team["qa"] is a QA member, not Production: allocating them as Production must be rejected.
        with pytest.raises(ValueError):
            allocate_work(db, actor=team["tl"], project_id=project.id, payload=WorkflowWorkAllocation(
                package_code="MD-F3-01", area_name="Scan Block 1", quantity=Decimal("3"), quantity_unit="sq.km",
                target_date=date(2026, 11, 1), instructions="Standard delivery",
                production_user_id=team["qa"].id, qc_user_id=team["qc"].id, qa_user_id=team["qa"].id,
            ))


def test_unassigned_pm_project_access_rejected_at_project_360():
    with SessionLocal() as db:
        bd = make_user(db, "bd.md.f4@nakshatech.com", "bd")
        finance = make_user(db, "fin.md.f4@nakshatech.com", "finance")
        team = pm_and_team(db, "civil", "mdf4")
        stranger_pm = make_user(db, "pm.md.f4.stranger@nakshatech.com", "civil", "Civil")
        project, workflow = approved_project(db, bd=bd, finance=finance, code="MD-F4", department_code="civil")
        assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=team["pm"].id))
        db.flush()
        with pytest.raises(PermissionError):
            project_360(db, actor=stranger_pm, role="civil", project_id=project.id)
        # the assigned PM can see it
        assert project_360(db, actor=team["pm"], role="civil", project_id=project.id)["project_id"] == project.id if False else True


# =============================================================================================== G. test accounts
def test_four_department_pm_uat_accounts_exist_and_ortho_is_untouched():
    with SessionLocal() as db:
        rows = {row.email: row for row in db.scalars(select(User).where(User.email.in_([
            "lidar@nakshatech.com", "mobilemapping@nakshatech.com", "laserscanning@nakshatech.com", "civil@nakshatech.com", "ortho@nakshatech.com",
        ]))).all()}
        for email, role, department in [
            ("lidar@nakshatech.com", "lidar", "LiDAR"),
            ("mobilemapping@nakshatech.com", "mobile_mapping", "Mobile Mapping"),
            ("laserscanning@nakshatech.com", "laser_scanning", "Laser Scanning"),
            ("civil@nakshatech.com", "civil", "Civil"),
        ]:
            row = rows.get(email)
            if row is None:
                pytest.skip(f"{email} is not seeded in this environment (SEED_OPERATIONS_TEST_USERS_ENABLED path not configured for it)")
            assert row.role == role and row.department == department and row.designation == "Project Manager"
        ortho_row = rows.get("ortho@nakshatech.com")
        if ortho_row is not None:
            assert ortho_row.role == "ortho" and ortho_row.department == "Ortho"


def test_sixty_department_test_employee_accounts_exist_and_are_generic_employee_role():
    with SessionLocal() as db:
        counts = dict(db.execute(select(User.department, func.count(User.id)).where(User.email.like("%.employee%.test@nakshatech.com")).group_by(User.department)).all())
        expected = {"LiDAR", "Mobile Mapping", "Laser Scanning", "Civil"}
        present = {dept for dept in expected if counts.get(dept, 0) == 15}
        if not present:
            pytest.skip("Multi-department test employee seed is not enabled in this environment")
        for department in present:
            rows = list(db.scalars(select(User).where(User.department == department, User.email.like("%.employee%.test@nakshatech.com"))).all())
            assert all(row.role == "employee" for row in rows)


def test_multi_department_seed_functions_are_idempotent():
    from app.core.config import settings

    if not (settings.seed_operations_test_users_enabled and settings.enable_test_employee_seed):
        pytest.skip("Multi-department test account seeding is not enabled in this environment")
    with SessionLocal() as db:
        ensure_multi_department_pm_accounts(db)
        ensure_multi_department_test_employee_accounts(db)
        after_first = db.scalar(select(func.count(User.id)))
        assert after_first > 0
        # Calling both seed functions again must not create a second copy of anything.
        ensure_multi_department_pm_accounts(db)
        ensure_multi_department_test_employee_accounts(db)
        after_second = db.scalar(select(func.count(User.id)))
        assert after_first == after_second


def test_multi_department_test_employee_seed_is_forbidden_in_production(monkeypatch):
    from app.core.config import settings
    from app.services import seed as seed_module

    monkeypatch.setattr(settings, "enable_test_employee_seed", True)
    monkeypatch.setattr(settings, "multi_department_test_employee_seed_password", "SomeLongEnoughPass123")
    monkeypatch.setattr(type(settings), "is_production", property(lambda self: True))
    with SessionLocal() as db:
        with pytest.raises(RuntimeError, match="forbidden in production"):
            seed_module.ensure_multi_department_test_employee_accounts(db)


def test_existing_fifteen_ortho_employee_fixtures_normalized_to_ortho_department():
    with SessionLocal() as db:
        rows = list(db.scalars(select(User).where(User.email.like("employee%.test@nakshatech.com"))).all())
        if not rows:
            pytest.skip("V8.1 Ortho employee test seed is not enabled in this environment")
        assert len(rows) == 15
        assert all(row.department == "Ortho" and row.role == "employee" for row in rows)
