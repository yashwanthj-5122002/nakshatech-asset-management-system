from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.handover_models import ProjectDataHandover
from app.modules.operations.models import ProjectWorkstream
from app.modules.operations.handover_schemas import (
    ProjectDataHandoverCreate,
    ProjectDataHandoverDecision,
    ProjectDataHandoverSubmit,
)
from app.modules.operations.handover_service import (
    create_project_handover,
    create_receiver_handover_notification,
    decide_project_handover,
    submit_project_handover,
)
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
    update_bd_stage,
    update_project_workstream_status,
)


def user(db, email: str, name: str, role: str, department: str, employee_id: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-only",
        role=role,
        branch="Head Office",
        employee_id=employee_id,
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
    finance = user(db, "finance.v717@nakshatech.com", "Finance V717", "finance", "Finance", "V717-FIN")
    bd = user(db, "bd.v717@nakshatech.com", "BD V717", "bd", "Business Development", "V717-BD")
    mobile = user(db, "mobile.mapping.demo@nakshatech.com", "Mobile Mapping Demo PM", "mobile_mapping", "Mobile Mapping", "DEMO-V715-MOBILE-PM")
    lidar = user(db, "lidar.demo@nakshatech.com", "LiDAR Demo PM", "lidar", "LiDAR", "DEMO-V715-LIDAR-PM")
    bim = user(db, "bim.demo@nakshatech.com", "BIM Demo PM", "bim", "BIM", "DEMO-V715-BIM-PM")
    civil = user(db, "civil.demo@nakshatech.com", "Civil Demo PM", "civil", "Civil", "DEMO-V715-CIVIL-PM")

    client = FinanceClient(
        client_code="V717-C01",
        client_name="Connected Workflow Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="BD V717",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code="V717-P01",
        project_name="Mobile to LiDAR to BIM",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date(2026, 9, 10),
        end_date=date(2026, 12, 31),
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(project)
    db.flush()

    opportunity = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
        title="Connected technical project",
        client_id=client.id,
        requirement="Mobile mapping data feeds LiDAR, LiDAR feeds BIM",
        priority="high",
    ))
    update_bd_stage(db, opportunity=opportunity, actor=bd, payload=BDStageUpdate(stage="accepted"))
    opportunity, _profile = link_bd_project(db, opportunity=opportunity, actor=bd, payload=BDProjectLink(project_id=project.id))
    rows = configure_project_workstreams(
        db,
        opportunity=opportunity,
        actor=bd,
        payload=ProjectWorkstreamConfig(workstreams=[
            ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
            ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=lidar.id, sequence_order=2),
            ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=3),
            ProjectWorkstreamInput(department_code="civil", project_manager_user_id=civil.id, sequence_order=4),
        ]),
    )
    db.flush()
    by_code = {row.department_code: row for row in rows}
    return finance, bd, mobile, lidar, bim, civil, project, opportunity, by_code


def test_bd_builds_non_circular_connected_workstream_chain():
    with SessionLocal() as db:
        _, bd, _, _, _, _, project, _, ws = fixture(db)
        first = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
            project_id=project.id,
            from_workstream_id=ws["mobile_mapping"].id,
            to_workstream_id=ws["lidar"].id,
            title="Registered mobile mapping point cloud",
            expected_output="Registered point cloud, trajectory and control summary",
        ))
        second = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
            project_id=project.id,
            from_workstream_id=ws["lidar"].id,
            to_workstream_id=ws["bim"].id,
            title="Classified LiDAR output",
            expected_output="Classified LAS/LAZ and agreed surfaces for BIM modelling",
        ))
        assert first.project_id == second.project_id == project.id
        assert first.status == second.status == "waiting_for_source"
        with pytest.raises(ValueError, match="circular"):
            create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
                project_id=project.id,
                from_workstream_id=ws["bim"].id,
                to_workstream_id=ws["mobile_mapping"].id,
                title="Invalid cycle",
                expected_output="Must be rejected",
            ))


def test_upstream_handover_blocks_downstream_until_receiver_accepts():
    with SessionLocal() as db:
        _, bd, mobile, lidar, _, _, project, _, ws = fixture(db)
        handover = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
            project_id=project.id,
            from_workstream_id=ws["mobile_mapping"].id,
            to_workstream_id=ws["lidar"].id,
            title="Mobile data to LiDAR",
            expected_output="Registered point cloud and trajectory",
        ))
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        with pytest.raises(ValueError, match="upstream data handover"):
            update_project_workstream_status(
                db,
                row=ws["lidar"],
                actor=lidar,
                effective_role="lidar",
                payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
            )

        attempt = submit_project_handover(
            db,
            handover=handover,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://V717/mobile/final", notes="Registered and checked"),
        )
        assert attempt.attempt_no == 1
        assert handover.status == "pending_receipt"
        created = create_receiver_handover_notification(db, handover_id=handover.id)
        assert created == 1
        notification = db.scalar(select(GlobalNotification).where(
            GlobalNotification.event_type == "project.handover.pending_receipt"
        ))
        assert notification is not None
        assert notification.recipient_user_id == lidar.id

        decide_project_handover(
            db,
            handover=handover,
            actor=lidar,
            effective_role="lidar",
            payload=ProjectDataHandoverDecision(decision="accepted"),
        )
        assert handover.status == "accepted"
        assert ws["lidar"].status == "ready"
        update_project_workstream_status(
            db,
            row=ws["lidar"],
            actor=lidar,
            effective_role="lidar",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        assert ws["lidar"].status == "in_progress"


def test_receiver_can_request_correction_and_sender_resubmits_new_attempt():
    with SessionLocal() as db:
        _, bd, mobile, lidar, _, _, project, _, ws = fixture(db)
        handover = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
            project_id=project.id,
            from_workstream_id=ws["mobile_mapping"].id,
            to_workstream_id=ws["lidar"].id,
            title="Mobile point cloud",
            expected_output="Point cloud with trajectory",
        ))
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        submit_project_handover(
            db,
            handover=handover,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://attempt-1"),
        )
        decide_project_handover(
            db,
            handover=handover,
            actor=lidar,
            effective_role="lidar",
            payload=ProjectDataHandoverDecision(decision="revision_requested", feedback="Missing trajectory file"),
        )
        assert handover.status == "revision_requested"
        assert handover.revision_feedback == "Missing trajectory file"
        second = submit_project_handover(
            db,
            handover=handover,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://attempt-2", notes="Trajectory added"),
        )
        assert second.attempt_no == 2
        assert handover.current_attempt_no == 2
        assert handover.status == "pending_receipt"


def test_handover_actions_are_department_pm_scoped_and_demo_only():
    with SessionLocal() as db:
        _, bd, mobile, lidar, bim, civil, project, opportunity, ws = fixture(db)
        handover = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
            project_id=project.id,
            from_workstream_id=ws["mobile_mapping"].id,
            to_workstream_id=ws["lidar"].id,
            title="Permission check",
            expected_output="Mobile dataset",
        ))
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        with pytest.raises(PermissionError, match="sending department"):
            submit_project_handover(
                db,
                handover=handover,
                actor=bim,
                effective_role="bim",
                payload=ProjectDataHandoverSubmit(output_reference="shared://wrong-user"),
            )
        submit_project_handover(
            db,
            handover=handover,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://correct-user"),
        )
        with pytest.raises(PermissionError, match="receiving department"):
            decide_project_handover(
                db,
                handover=handover,
                actor=civil,
                effective_role="civil",
                payload=ProjectDataHandoverDecision(decision="accepted"),
            )

        real_lidar = user(db, "real.lidar.v717@nakshatech.com", "Real LiDAR PM", "lidar", "LiDAR", "REAL-LIDAR-V717")
        configure_project_workstreams(
            db,
            opportunity=opportunity,
            actor=bd,
            payload=ProjectWorkstreamConfig(workstreams=[
                ProjectWorkstreamInput(department_code="mobile_mapping", project_manager_user_id=mobile.id, sequence_order=1),
                ProjectWorkstreamInput(department_code="lidar", project_manager_user_id=real_lidar.id, sequence_order=2),
                ProjectWorkstreamInput(department_code="bim", project_manager_user_id=bim.id, sequence_order=3),
            ]),
        )
        rows = list(db.scalars(select(ProjectDataHandover).where(ProjectDataHandover.project_id == project.id)).all())
        assert rows
        # Existing active connection was configured while demo managers were assigned.
        # Any NEW connection touching the real LiDAR PM must be blocked during UAT.
        updated_lidar = db.scalar(select(ProjectWorkstream).where(
            ProjectWorkstream.project_id == project.id,
            ProjectWorkstream.department_code == "lidar",
        ))
        assert updated_lidar is not None
        with pytest.raises(ValueError, match="reserved demo LiDAR PM"):
            create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
                project_id=project.id,
                from_workstream_id=updated_lidar.id,
                to_workstream_id=ws["bim"].id,
                title="Real email must stay disabled",
                expected_output="UAT must block this",
            ))
