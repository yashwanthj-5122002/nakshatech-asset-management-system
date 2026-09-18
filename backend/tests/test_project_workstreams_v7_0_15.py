from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import BDOpportunity, OrthoProjectProfile, ProjectWorkstream
from app.modules.operations.schemas import (
    BDOpportunityCreate,
    BDProjectLink,
    BDStageUpdate,
    ProjectWorkstreamConfig,
    ProjectWorkstreamInput,
    ProjectWorkstreamStatusUpdate,
)
from app.modules.operations.service import (
    configure_project_workstreams,
    create_bd_opportunity,
    link_bd_project,
    project_workstreams_dashboard_payload,
    update_bd_stage,
    update_project_workstream_status,
)


def user(db, email: str, name: str, role: str, department: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-only",
        role=role,
        branch="Head Office",
        department=department,
        designation="Project Manager",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def fixture(db):
    finance = user(db, "finance.v715@nakshatech.com", "Finance V715", "finance", "Finance")
    bd = user(db, "bd.v715@nakshatech.com", "BD V715", "bd", "Business Development")
    mobile = user(db, "mobile.v715@nakshatech.com", "Mobile Mapping PM", "mobile_mapping", "Mobile Mapping")
    ortho = user(db, "ortho.v715@nakshatech.com", "Ortho PM", "ortho", "Ortho")
    lidar = user(db, "lidar.v715@nakshatech.com", "LiDAR PM", "lidar", "LiDAR")
    bim = user(db, "bim.v715@nakshatech.com", "BIM PM", "bim", "BIM")
    civil = user(db, "civil.v715@nakshatech.com", "Civil PM", "civil", "Civil")
    client = FinanceClient(
        client_code="V715-C01",
        client_name="V715 Multi Team Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="BD V715",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client); db.flush()
    project = FinanceProject(
        project_code="V715-P01",
        project_name="Mobile Mapping + LiDAR + BIM",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date(2026, 9, 10),
        end_date=date(2026, 12, 31),
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(project); db.flush()
    opportunity = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
        title="V715 multi department project",
        client_id=client.id,
        requirement="Mobile mapping acquisition, LiDAR processing and BIM modelling",
        priority="high",
    ))
    update_bd_stage(db, opportunity=opportunity, actor=bd, payload=BDStageUpdate(stage="accepted"))
    opportunity, profile = link_bd_project(db, opportunity=opportunity, actor=bd, payload=BDProjectLink(project_id=project.id))
    db.flush()
    return finance, bd, mobile, ortho, lidar, bim, civil, client, project, opportunity, profile


def test_finance_project_can_link_without_ortho_pm_then_bd_configures_multiple_workstreams():
    with SessionLocal() as db:
        _, bd, mobile, ortho, lidar, bim, _, _, project, opportunity, profile = fixture(db)
        assert profile is None
        assert opportunity.linked_project_id == project.id

        rows = configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=lidar.id, sequence_order=2),
                ProjectWorkstreamInput(department_code="ortho", project_manager_user_id=ortho.id, sequence_order=3),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=4),
            ]),
        )
        db.flush()
        assert [(row.department_code, row.sequence_order) for row in rows] == [
            ("mobile_mapping", 1), ("lidar", 2), ("ortho", 3), ("bim", 4)
        ]
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == ortho.id
        assert db.get(OrthoProjectProfile, project.id).project_manager_user_id == ortho.id
        notifications = list(db.scalars(select(GlobalNotification).where(GlobalNotification.event_type == "project.workstream.assigned")).all())
        assert {row.recipient_user_id for row in notifications} == {mobile.id, lidar.id, ortho.id, bim.id}


def test_department_dashboard_is_scoped_to_assigned_department_pm_and_status_is_pm_owned():
    with SessionLocal() as db:
        _, bd, mobile, ortho, lidar, bim, civil, _, _, opportunity, _ = fixture(db)
        rows = configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=2),
            ]),
        )
        mobile_row = next(row for row in rows if row.department_code == "mobile_mapping")
        dashboard = project_workstreams_dashboard_payload(db, actor=mobile, effective_role="mobile_mapping")
        assert dashboard["viewer_mode"] == "department"
        assert len(dashboard["projects"]) == 1
        assert [item["department_code"] for item in dashboard["projects"][0]["workstreams"]] == ["mobile_mapping"]

        update_project_workstream_status(
            db,
            row=mobile_row,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        assert mobile_row.status == "in_progress"
        with pytest.raises(PermissionError, match="assigned department Project Manager"):
            update_project_workstream_status(
                db,
                row=mobile_row,
                actor=civil,
                effective_role="civil",
                payload=ProjectWorkstreamStatusUpdate(status="completed"),
            )


def test_removing_ortho_workstream_clears_legacy_primary_pm_but_preserves_other_departments():
    with SessionLocal() as db:
        _, bd, mobile, ortho, lidar, bim, _, _, project, opportunity, _ = fixture(db)
        configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="ortho", project_manager_user_id=ortho.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=lidar.id, sequence_order=2),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=3),
            ]),
        )
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == ortho.id
        configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=lidar.id, sequence_order=2),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=3),
            ]),
        )
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id is None
        active = list(db.scalars(select(ProjectWorkstream).where(ProjectWorkstream.project_id == project.id, ProjectWorkstream.is_active.is_(True))).all())
        assert {row.department_code for row in active} == {"mobile_mapping", "lidar", "bim"}


def test_all_six_technical_departments_can_coexist_under_one_master_project():
    with SessionLocal() as db:
        _, bd, mobile, ortho, lidar, bim, civil, _, project, opportunity, _ = fixture(db)
        laser = user(db, "laser.v715@nakshatech.com", "Laser Scanning PM", "laser_scanning", "Laser Scanning")
        rows = configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=lidar.id, sequence_order=2),
                ProjectWorkstreamInput(department_code="ortho", project_manager_user_id=ortho.id, sequence_order=3),
                ProjectWorkstreamInput(department_code="civil", project_manager_user_id=civil.id, sequence_order=4),
                ProjectWorkstreamInput(department_code="laser_scanning", project_manager_user_id=laser.id, sequence_order=5),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=6),
            ]),
        )
        assert len(rows) == 6
        assert {row.department_code for row in rows} == {
            "ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"
        }
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == ortho.id
