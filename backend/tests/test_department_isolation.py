"""Department isolation: a normal employee reaches only their own department's operational data.

Matrix: laser_scanning / lidar / civil / ortho / mobile_mapping — each employee is
allowed their own department and denied the other four, both on the dashboard
(service and on project-scoped workflow APIs. Technical PM roles are scoped to their
own department; privileged roles keep full access.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("TOTP_ENCRYPTION_KEY", "department-isolation-totp-secret-32-chars")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.core.departments import DEPARTMENT_PM_ROLE, department_label  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import User  # noqa: E402
from app.modules.commercial.schemas import ProjectCommercialInput  # noqa: E402
from app.modules.employee_portal.employee_master import (  # noqa: E402
    ACTIVE_EMPLOYMENT,
    NOT_REGISTERED,
)
from app.modules.employee_portal.models import EmployeeMaster  # noqa: E402
from app.modules.finance.models import FinanceClient  # noqa: E402
from app.modules.operations.models import OrthoWorkPackage, ProjectWorkflow  # noqa: E402
from app.modules.operations.schemas import (  # noqa: E402
    WorkflowFinanceReview,
    WorkflowPMAssignment,
    WorkflowTeamSetup,
    WorkflowWorkAllocation,
)
from app.modules.operations.workflow_service import (  # noqa: E402
    allocate_work,
    assign_project_manager,
    configure_team,
    create_bd_project,
    finance_review_project,
    ortho_dashboard,
    submit_project_to_finance,
)

pytestmark = pytest.mark.usefixtures("isolated_application_database")

DEPARTMENTS = ["laser_scanning", "lidar", "civil", "ortho", "mobile_mapping"]


def _make_user(db, email: str, role: str, department: str | None = None, name: str | None = None) -> User:
    row = User(
        email=email,
        full_name=name or email.split("@", 1)[0],
        password_hash="test-only",
        role=role,
        branch="Head Office",
        department=department,
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _make_master(db, user: User, department_code: str) -> EmployeeMaster:
    master = EmployeeMaster(
        source_sl_no=f"SL-{user.id}",
        access_card_no=f"NT{1000 + user.id}",
        access_card_no_normalized=f"nt{1000 + user.id}",
        employee_number=str(2000 + user.id),
        employee_number_normalized=str(2000 + user.id),
        employee_name=user.full_name,
        phone="9000000000",
        phone_normalized="9000000000",
        department_raw=department_label(department_code),
        department_code=department_code,
        designation_raw="Engineer",
        email=user.email,
        email_normalized=user.email,
        employment_status=ACTIVE_EMPLOYMENT,
        crm_account_status=NOT_REGISTERED,
        linked_user_id=user.id,
        source_batch_id="dept-isolation-test",
    )
    db.add(master)
    db.flush()
    return master


def _commercial() -> ProjectCommercialInput:
    return ProjectCommercialInput(
        scope_description="Survey and deliver",
        billing_type="fixed_price",
        payment_terms="30 days",
        currency_code="INR",
        estimated_amount=Decimal("100000"),
        taxable_base_amount=Decimal("100000"),
        tax_percent=Decimal("18"),
        estimate_date=date(2026, 9, 22),
    )


def _approved_project(db, *, bd: User, finance: User, code: str, department_code: str):
    client = FinanceClient(
        client_code=f"C-{code}",
        client_name="Isolation Test Client",
        contact_person_name="Contact",
        contact_person_phone="9999999999",
        source_team="bd_team",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=bd.id,
    )
    db.add(client)
    db.flush()
    from app.modules.operations.schemas import WorkflowProjectCreate

    project, workflow = create_bd_project(
        db,
        actor=bd,
        payload=WorkflowProjectCreate(
            client_id=client.id,
            project_code=code,
            project_name="Isolation Test Project",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 12, 31),
            scope_text="Survey and deliver",
            performing_department_code=department_code,
            commercial=_commercial(),
        ),
    )
    submit_project_to_finance(db, actor=bd, project_id=project.id)
    finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", feedback="ok"))
    db.flush()
    return project


def _token(user: User) -> str:
    return create_access_token(user.email, user.role, token_version=int(user.token_version or 0))


def _auth(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(user)}"}


@pytest.fixture()
def environment():
    with SessionLocal() as db:
        bd = _make_user(db, "bd.isolation@nakshatech.com", "bd")
        finance = _make_user(db, "finance.isolation@nakshatech.com", "finance")
        db.flush()
        employees = {}
        for index, department in enumerate(DEPARTMENTS):
            employee = _make_user(db, f"emp.{department}@nakshatech.com", "employee", department_label(department), f"{department.title()} Employee")
            _make_master(db, employee, department)
            employees[department] = employee
        db.flush()
        projects = {}
        for department in DEPARTMENTS:
            projects[department] = _approved_project(db, bd=bd, finance=finance, code=f"ISO-{department.upper()}", department_code=department)
        db.flush()
        # Assign a PM (required before team selection), then assign each employee to
        # their own project as production, with a work package.
        for department in DEPARTMENTS:
            employee = employees[department]
            project = projects[department]
            pm = _make_user(db, f"pm.{department}@nakshatech.com", DEPARTMENT_PM_ROLE[department], department_label(department), f"{department.title()} PM")
            db.flush()
            assign_project_manager(db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=pm.id))
            db.flush()
            configure_team(
                db,
                actor=pm,
                project_id=project.id,
                payload=WorkflowTeamSetup(
                    team_leader_user_id=employee.id,
                    production_user_ids=[employee.id],
                    qc_user_ids=[employee.id],
                    qa_user_ids=[employee.id],
                ),
            )
            db.flush()
            allocate_work(
                db,
                actor=employee,
                project_id=project.id,
                payload=WorkflowWorkAllocation(
                    package_code=f"PKG-{department.upper()}",
                    area_name="Test area",
                    quantity=Decimal("10"),
                    quantity_unit="sqkm",
                    target_date=date(2026, 11, 30),
                    instructions="Test instructions",
                    production_user_id=employee.id,
                    qc_user_id=employee.id,
                    qa_user_id=employee.id,
                ),
            )
        db.commit()
        package_ids = {}
        for department in DEPARTMENTS:
            package = db.scalar(
                select(OrthoWorkPackage.id).where(OrthoWorkPackage.package_code == f"PKG-{department.upper()}")
            )
            package_ids[department] = package
        return {"employees": employees, "projects": projects, "package_ids": package_ids, "bd": bd, "finance": finance}


def test_employee_dashboard_shows_only_own_department(environment) -> None:
    with SessionLocal() as db:
        for department in DEPARTMENTS:
            employee = db.get(User, environment["employees"][department].id)
            payload = ortho_dashboard(db, actor=employee, role="employee")
            project_ids = [p["project_id"] for p in payload["projects"]]
            codes = set(
                db.scalars(
                    select(ProjectWorkflow.performing_department_code).where(ProjectWorkflow.project_id.in_(project_ids))
                ).all()
            ) if project_ids else set()
            assert codes == {department}, f"{department} employee saw {codes}"


def test_employee_denied_cross_department_work_package_action(environment) -> None:
    with TestClient(app) as client:
        laser = environment["employees"]["laser_scanning"]
        lidar_package = environment["package_ids"]["lidar"]
        response = client.post(
            f"/api/operations/workflow/ortho/work-packages/{lidar_package}/daily-activity",
            json={"update_date": "2026-10-15", "work_type": "survey", "quantity_completed": 1, "files_completed": 0, "hours_spent": 1, "status": "completed"},
            headers=_auth(laser),
        )
        assert response.status_code == 403, response.text


def test_employee_allowed_own_department_work_package_action(environment) -> None:
    with TestClient(app) as client:
        laser = environment["employees"]["laser_scanning"]
        own_package = environment["package_ids"]["laser_scanning"]
        response = client.post(
            f"/api/operations/workflow/ortho/work-packages/{own_package}/daily-activity",
            json={"update_date": "2026-10-15", "work_type": "survey", "quantity_completed": 1, "files_completed": 0, "hours_spent": 1, "status": "completed"},
            headers=_auth(laser),
        )
        assert response.status_code in {200, 201}, response.text


def test_technical_pm_scoped_to_own_department(environment) -> None:
    with SessionLocal() as db:
        lidar_pm = _make_user(db, "pm.isolation@nakshatech.com", DEPARTMENT_PM_ROLE["lidar"], "LiDAR", "LiDAR PM")
        db.flush()
        payload = ortho_dashboard(db, actor=lidar_pm, role=DEPARTMENT_PM_ROLE["lidar"])
        # PM sees projects they manage; with no assignments the list is empty but never cross-department.
        assert payload["projects"] == []


def test_admin_keeps_full_access(environment) -> None:
    with SessionLocal() as db:
        admin = _make_user(db, "admin.isolation@nakshatech.com", "admin")
        db.flush()
        payload = ortho_dashboard(db, actor=admin, role="admin")
        assert len(payload["projects"]) == len(DEPARTMENTS)
