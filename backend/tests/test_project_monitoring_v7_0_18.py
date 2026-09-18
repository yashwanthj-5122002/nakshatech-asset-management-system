from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.core.database import SessionLocal
from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.operations.handover_schemas import (
    ProjectDataHandoverCreate,
    ProjectDataHandoverDecision,
    ProjectDataHandoverSubmit,
)
from app.modules.operations.handover_service import (
    create_project_handover,
    decide_project_handover,
    submit_project_handover,
)
from app.modules.operations.monitoring_schemas import ProjectHandoverScheduleUpdate, ProjectWorkstreamProgressUpdate
from app.modules.operations.monitoring_service import (
    monitoring_dashboard_payload,
    update_handover_schedule,
    update_workstream_progress,
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
    finance = user(db, "finance.v718@nakshatech.com", "Finance V718", "finance", "Finance", "V718-FIN")
    bd = user(db, "bd.v718@nakshatech.com", "BD V718", "bd", "Business Development", "V718-BD")
    other_bd = user(db, "bd.other.v718@nakshatech.com", "Other BD V718", "bd", "Business Development", "V718-BD2")
    management = user(db, "management.v718@nakshatech.com", "Management V718", "management", "Management", "V718-MGT")
    mobile = user(db, "mobile.mapping.demo@nakshatech.com", "Mobile Mapping Demo PM", "mobile_mapping", "Mobile Mapping", "DEMO-V715-MOBILE-PM")
    lidar = user(db, "lidar.demo@nakshatech.com", "LiDAR Demo PM", "lidar", "LiDAR", "DEMO-V715-LIDAR-PM")
    bim = user(db, "bim.demo@nakshatech.com", "BIM Demo PM", "bim", "BIM", "DEMO-V715-BIM-PM")

    client = FinanceClient(
        client_code="V718-C01",
        client_name="Monitoring Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="BD V718",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code="V718-P01",
        project_name="Cross Team Monitoring Project",
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
        title="Monitoring technical project",
        client_id=client.id,
        requirement="Mobile Mapping feeds LiDAR and LiDAR feeds BIM",
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
        ]),
    )
    db.flush()
    ws = {row.department_code: row for row in rows}
    first = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
        project_id=project.id,
        from_workstream_id=ws["mobile_mapping"].id,
        to_workstream_id=ws["lidar"].id,
        title="Registered mobile mapping data",
        expected_output="Registered point cloud and trajectory",
    ))
    second = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
        project_id=project.id,
        from_workstream_id=ws["lidar"].id,
        to_workstream_id=ws["bim"].id,
        title="Classified LiDAR data",
        expected_output="Classified point cloud for BIM",
    ))
    db.flush()
    return finance, bd, other_bd, management, mobile, lidar, bim, project, opportunity, ws, first, second


def test_monitoring_aggregates_peer_workstreams_progress_and_current_bottleneck():
    with SessionLocal() as db:
        _, bd, _, management, mobile, _, _, project, _, ws, first, _ = fixture(db)
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        update_workstream_progress(
            db,
            workstream=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamProgressUpdate(progress_percent=40, note="Registration 40% complete"),
        )
        dashboard = monitoring_dashboard_payload(db, actor=bd, effective_role="bd")
        assert dashboard["viewer_mode"] == "bd_monitor"
        assert len(dashboard["projects"]) == 1
        row = dashboard["projects"][0]
        assert row["project_id"] == project.id
        assert row["summary"]["overall_progress_percent"] == pytest.approx(13.3, abs=0.1)
        assert row["summary"]["bottleneck_departments"] == ["LiDAR", "Mobile Mapping"]
        first_payload = next(item for item in row["handovers"] if item["id"] == first.id)
        assert first_payload["action_required"] == "Mobile Mapping to submit data"
        assert first_payload["bottleneck_department_label"] == "Mobile Mapping"

        management_dashboard = monitoring_dashboard_payload(db, actor=management, effective_role="management")
        assert management_dashboard["viewer_mode"] == "read_only"
        assert management_dashboard["projects"][0]["project_id"] == project.id


def test_bottleneck_moves_from_sender_to_receiver_then_back_to_sender_on_revision():
    with SessionLocal() as db:
        _, bd, _, _, mobile, lidar, _, _, _, ws, first, _ = fixture(db)
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        submit_project_handover(
            db,
            handover=first,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://v718/mobile/attempt-1"),
        )
        pending = monitoring_dashboard_payload(db, actor=bd, effective_role="bd")["projects"][0]
        first_pending = next(item for item in pending["handovers"] if item["id"] == first.id)
        assert first_pending["status"] == "pending_receipt"
        assert first_pending["bottleneck_department_label"] == "LiDAR"
        assert first_pending["action_required"] == "LiDAR to review / accept"

        decide_project_handover(
            db,
            handover=first,
            actor=lidar,
            effective_role="lidar",
            payload=ProjectDataHandoverDecision(decision="revision_requested", feedback="Trajectory file missing"),
        )
        revision = monitoring_dashboard_payload(db, actor=bd, effective_role="bd")["projects"][0]
        first_revision = next(item for item in revision["handovers"] if item["id"] == first.id)
        assert first_revision["status"] == "revision_requested"
        assert first_revision["bottleneck_department_label"] == "Mobile Mapping"
        assert revision["summary"]["health"] == "blocked"


def test_only_reserved_demo_department_pm_can_report_own_progress_during_uat():
    with SessionLocal() as db:
        _, _, _, _, mobile, lidar, _, _, _, ws, _, _ = fixture(db)
        saved = update_workstream_progress(
            db,
            workstream=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamProgressUpdate(progress_percent=55, note="Survey processing underway"),
        )
        assert saved.progress_percent == 55

        with pytest.raises(PermissionError, match="reserved demo"):
            update_workstream_progress(
                db,
                workstream=ws["mobile_mapping"],
                actor=lidar,
                effective_role="lidar",
                payload=ProjectWorkstreamProgressUpdate(progress_percent=75),
            )

        real_mobile = user(db, "real.mobile.v718@nakshatech.com", "Real Mobile PM", "mobile_mapping", "Mobile Mapping", "REAL-MOBILE-V718")
        ws["mobile_mapping"].project_manager_user_id = real_mobile.id
        db.flush()
        with pytest.raises(PermissionError, match="reserved demo"):
            update_workstream_progress(
                db,
                workstream=ws["mobile_mapping"],
                actor=real_mobile,
                effective_role="mobile_mapping",
                payload=ProjectWorkstreamProgressUpdate(progress_percent=60),
            )


def test_bd_owner_sets_handover_due_time_and_dashboard_marks_true_overdue():
    with SessionLocal() as db:
        _, bd, other_bd, _, _, _, _, _, _, _, first, _ = fixture(db)
        due = utc_now() - timedelta(hours=2)
        schedule = update_handover_schedule(
            db,
            handover=first,
            actor=bd,
            payload=ProjectHandoverScheduleUpdate(due_at=due, note="Client dependency milestone"),
        )
        assert schedule.due_at == due
        dashboard = monitoring_dashboard_payload(db, actor=bd, effective_role="bd")["projects"][0]
        first_payload = next(item for item in dashboard["handovers"] if item["id"] == first.id)
        assert first_payload["overdue"] is True
        assert dashboard["summary"]["overdue_handovers"] == 1
        assert dashboard["summary"]["health"] == "delayed"

        with pytest.raises(PermissionError, match="BD owner"):
            update_handover_schedule(
                db,
                handover=first,
                actor=other_bd,
                payload=ProjectHandoverScheduleUpdate(due_at=utc_now() + timedelta(days=1)),
            )
