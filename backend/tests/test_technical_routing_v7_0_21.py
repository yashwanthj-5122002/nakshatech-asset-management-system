from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.completion_schemas import DepartmentCompletionRequest
from app.modules.operations.completion_service import complete_department_workstream
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.handover_service import _assert_sender, _handover_recipients
from app.modules.operations.models import BDOpportunity, ProjectWorkstream
from app.modules.operations.monitoring_schemas import ProjectWorkstreamProgressUpdate
from app.modules.operations.monitoring_service import update_workstream_progress
from app.modules.operations.sample_schemas import TechnicalSampleRequestCreate
from app.modules.operations.sample_service import create_sample_request, create_sample_team_notifications, start_sample_department
from app.modules.operations.service import technical_project_manager_options
from app.modules.operations.technical_directory_models import TechnicalDepartmentMember
from app.modules.operations.technical_directory_schemas import TechnicalDirectoryMemberCreate, TechnicalDirectoryMemberUpdate
from app.modules.operations.technical_directory_service import add_directory_member, update_directory_member
from app.modules.operations.technical_routing_models import TechnicalRoutingControl
from app.modules.operations.technical_routing_service import (
    ACTIVATION_CONFIRMATION,
    ROUTING_MODE_DEMO,
    ROUTING_MODE_LIVE,
    activate_live_routing,
    live_routing_enabled,
    routing_status_payload,
)

DEPARTMENTS = {
    "ortho": "ortho",
    "lidar": "lidar",
    "civil": "civil",
    "laser_scanning": "laser_scanning",
    "bim": "bim",
    "mobile_mapping": "mobile_mapping",
}


def _user(db, *, email: str, role: str, employee_id: str, name: str | None = None) -> User:
    row = User(
        email=email,
        full_name=name or email.split("@", 1)[0],
        password_hash="phase7-test-only",
        role=role,
        branch="Head Office",
        department=role,
        designation="Project Manager",
        employee_id=employee_id,
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _prepare_six(db):
    admin = _user(db, email="admin.v721@nakshatech.com", role="admin", employee_id="ADM-V721", name="Admin V721")
    users: dict[str, User] = {}
    members: dict[str, TechnicalDepartmentMember] = {}
    for idx, (code, role) in enumerate(DEPARTMENTS.items(), start=1):
        user = _user(
            db,
            email=f"real.{code}.v721@nakshatech.com",
            role=role,
            employee_id=f"REAL-V721-{idx}",
            name=f"Real {code} PM",
        )
        member = add_directory_member(
            db,
            department_code=code,
            actor=admin,
            payload=TechnicalDirectoryMemberCreate(user_id=user.id),
        )
        users[code] = user
        members[code] = member
    db.flush()
    return admin, users, members


def _project(db, creator: User, *, suffix: str = "A") -> FinanceProject:
    client = FinanceClient(
        client_code=f"V721-C-{suffix}",
        client_name=f"Phase 7 Client {suffix}",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="Phase 7",
        is_active=True,
        created_by_id=creator.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code=f"V721-P-{suffix}",
        project_name=f"Phase 7 Project {suffix}",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date(2026, 9, 11),
        end_date=date(2026, 12, 31),
        is_active=True,
        created_by_id=creator.id,
    )
    db.add(project)
    db.flush()
    return project


def _workstream(db, *, project: FinanceProject, pm: User, code: str, creator: User, status: str = "planned") -> ProjectWorkstream:
    row = ProjectWorkstream(
        project_id=project.id,
        department_code=code,
        project_manager_user_id=pm.id,
        sequence_order=1,
        status=status,
        is_active=True,
        created_by_id=creator.id,
        updated_by_id=creator.id,
    )
    db.add(row)
    db.flush()
    return row


def test_phase7_install_default_is_safe_demo_locked_and_activation_requires_all_six_departments():
    with SessionLocal() as db:
        admin = _user(db, email="admin.default.v721@nakshatech.com", role="admin", employee_id="ADM-V721-D")
        status = routing_status_payload(db)
        assert status["routing_mode"] == ROUTING_MODE_DEMO
        assert status["live_technical_routing_enabled"] is False
        assert status["can_activate"] is False
        with pytest.raises(ValueError, match="All six technical directories"):
            activate_live_routing(db, actor=admin, confirmation=ACTIVATION_CONFIRMATION, note=None)
        assert db.get(TechnicalRoutingControl, 1) is None


def test_phase7_admin_can_activate_only_after_clean_live_ready_boundary_and_real_pm_directory_replaces_demo_selector():
    with SessionLocal() as db:
        admin, users, _ = _prepare_six(db)
        before = routing_status_payload(db)
        assert before["all_departments_ready"] is True
        assert before["can_activate"] is True

        control = activate_live_routing(
            db,
            actor=admin,
            confirmation=ACTIVATION_CONFIRMATION,
            note="Phase 7 automated cutover test",
        )
        db.commit()
        assert control.routing_mode == ROUTING_MODE_LIVE
        assert live_routing_enabled(db) is True
        after = routing_status_payload(db)
        assert after["live_technical_routing_enabled"] is True
        assert after["can_activate"] is False

        options = technical_project_manager_options(db)
        assert {item["id"] for item in options} == {user.id for user in users.values()}
        assert all(".demo@nakshatech.com" not in item["email"] for item in options)


def test_phase7_clean_boundary_blocks_activation_while_any_technical_workstream_is_unfinished():
    with SessionLocal() as db:
        admin, users, _ = _prepare_six(db)
        project = _project(db, admin, suffix="BLOCK")
        _workstream(db, project=project, pm=users["ortho"], code="ortho", creator=admin, status="planned")
        db.flush()
        status = routing_status_payload(db)
        assert status["blockers"]["open_technical_workstreams"] == 1
        assert status["can_activate"] is False
        with pytest.raises(ValueError, match="Clean-boundary cutover is blocked"):
            activate_live_routing(db, actor=admin, confirmation=ACTIVATION_CONFIRMATION, note=None)


def test_phase7_sample_actions_and_notifications_use_real_directory_members_after_activation():
    with SessionLocal() as db:
        admin, users, _ = _prepare_six(db)
        activate_live_routing(db, actor=admin, confirmation=ACTIVATION_CONFIRMATION, note=None)
        bd = _user(db, email="bd.v721@nakshatech.com", role="bd", employee_id="BD-V721")
        opportunity = BDOpportunity(
            opportunity_code="BD-V721-SAMPLE",
            title="Phase 7 Live Sample",
            client_name_snapshot="Live Sample Client",
            requirement="Create a real-routed technical sample",
            service_type="multi_department",
            priority="medium",
            stage="opportunity",
            owner_user_id=bd.id,
        )
        db.add(opportunity)
        db.flush()
        sample = create_sample_request(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=TechnicalSampleRequestCreate(
                title="Live Ortho Sample",
                instructions="Prepare live-routed Ortho sample",
                department_codes=["ortho"],
            ),
        )
        db.commit()
        created = create_sample_team_notifications(db, sample_request_id=sample.id)
        db.commit()
        assert created == 1
        recipient_ids = set(db.scalars(select(GlobalNotification.recipient_user_id).where(
            GlobalNotification.event_type == "technical.sample.requested"
        )).all())
        assert recipient_ids == {users["ortho"].id}

        start_sample_department(db, sample_request=sample, actor=users["ortho"], effective_role="ortho")
        with pytest.raises(PermissionError):
            start_sample_department(db, sample_request=sample, actor=users["lidar"], effective_role="lidar")


def test_phase7_real_pm_owns_handover_progress_and_completion_after_activation():
    with SessionLocal() as db:
        admin, users, _ = _prepare_six(db)
        activate_live_routing(db, actor=admin, confirmation=ACTIVATION_CONFIRMATION, note=None)
        project = _project(db, admin, suffix="LIVE")
        ortho_ws = _workstream(db, project=project, pm=users["ortho"], code="ortho", creator=admin, status="in_progress")
        lidar_ws = _workstream(db, project=project, pm=users["lidar"], code="lidar", creator=admin, status="planned")

        progress = update_workstream_progress(
            db,
            workstream=ortho_ws,
            actor=users["ortho"],
            effective_role="ortho",
            payload=ProjectWorkstreamProgressUpdate(progress_percent=70, note="Live routing progress"),
        )
        assert progress.progress_percent == 70
        with pytest.raises(PermissionError):
            update_workstream_progress(
                db,
                workstream=ortho_ws,
                actor=users["lidar"],
                effective_role="lidar",
                payload=ProjectWorkstreamProgressUpdate(progress_percent=80),
            )

        handover = ProjectDataHandover(
            handover_code="HDO-V721-0001",
            project_id=project.id,
            from_workstream_id=ortho_ws.id,
            to_workstream_id=lidar_ws.id,
            title="Ortho to LiDAR",
            expected_output="Live handover data",
            status="waiting_for_source",
            current_attempt_no=0,
            is_active=True,
            created_by_id=admin.id,
        )
        db.add(handover)
        db.flush()
        assert _assert_sender(db, handover=handover, actor=users["ortho"], effective_role="ortho").id == ortho_ws.id
        assert {user.id for user in _handover_recipients(db, lidar_ws)} == {users["lidar"].id}

        # Remove the handover from this completion check; Phase 5/7 correctly blocks
        # completion while an outgoing dependency is unresolved.
        handover.is_active = False
        db.flush()
        completed = complete_department_workstream(
            db,
            workstream=ortho_ws,
            actor=users["ortho"],
            effective_role="ortho",
            payload=DepartmentCompletionRequest(note="Live Ortho complete"),
        )
        assert completed.status == "completed"
        assert completed.completed_at is not None


def test_phase7_cannot_remove_pm_eligibility_from_member_owning_active_production_workstream():
    with SessionLocal() as db:
        admin, users, members = _prepare_six(db)
        second_ortho = _user(
            db,
            email="real.ortho.backup.v721@nakshatech.com",
            role="ortho",
            employee_id="REAL-V721-ORTHO-2",
            name="Backup Ortho PM",
        )
        add_directory_member(
            db,
            department_code="ortho",
            actor=admin,
            payload=TechnicalDirectoryMemberCreate(user_id=second_ortho.id),
        )
        activate_live_routing(db, actor=admin, confirmation=ACTIVATION_CONFIRMATION, note=None)
        project = _project(db, admin, suffix="GUARD")
        _workstream(db, project=project, pm=users["ortho"], code="ortho", creator=admin, status="in_progress")
        db.flush()

        with pytest.raises(ValueError, match="active Project Workstream"):
            update_directory_member(
                db,
                row=members["ortho"],
                actor=admin,
                payload=TechnicalDirectoryMemberUpdate(pm_eligible=False),
            )
