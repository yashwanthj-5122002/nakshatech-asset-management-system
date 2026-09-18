from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import BDOpportunity
from app.modules.operations.completion_models import MasterProjectCompletion
from app.modules.operations.completion_schemas import (
    DepartmentCompletionRequest,
    FinanceClosureUpdate,
    MasterProjectDeliveryRequest,
)
from app.modules.operations.completion_service import (
    assert_legacy_ortho_final_delivery_allowed,
    complete_department_workstream,
    create_bd_financial_closure_notification,
    create_bd_project_ready_notification,
    create_finance_master_completion_notifications,
    project_completion_readiness,
    record_master_project_delivery,
    update_finance_closure,
)
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


def add_user(db, email: str, name: str, role: str, department: str, employee_id: str) -> User:
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


def build_chain(db):
    finance = add_user(db, "finance.v719@nakshatech.com", "Finance V719", "finance", "Finance", "V719-FIN")
    bd = add_user(db, "bd.v719@nakshatech.com", "BD V719", "bd", "Business Development", "V719-BD")
    mobile = add_user(db, "mobile.mapping.demo@nakshatech.com", "Mobile Mapping Demo PM", "mobile_mapping", "Mobile Mapping", "DEMO-V715-MOBILE-PM")
    lidar = add_user(db, "lidar.demo@nakshatech.com", "LiDAR Demo PM", "lidar", "LiDAR", "DEMO-V715-LIDAR-PM")
    bim = add_user(db, "bim.demo@nakshatech.com", "BIM Demo PM", "bim", "BIM", "DEMO-V715-BIM-PM")

    client = FinanceClient(
        client_code="V719-C01",
        client_name="Completion Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name=bd.full_name,
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code="V719-P01",
        project_name="Completion Project",
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
        title="Completion technical project",
        client_id=client.id,
        requirement="Mobile Mapping -> LiDAR -> BIM",
        priority="high",
    ))
    update_bd_stage(db, opportunity=opportunity, actor=bd, payload=BDStageUpdate(stage="accepted"))
    opportunity, _ = link_bd_project(db, opportunity=opportunity, actor=bd, payload=BDProjectLink(project_id=project.id))
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
    ws = {row.department_code: row for row in rows}
    first = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
        project_id=project.id,
        from_workstream_id=ws["mobile_mapping"].id,
        to_workstream_id=ws["lidar"].id,
        title="Mobile mapping source",
        expected_output="Registered source data",
    ))
    second = create_project_handover(db, actor=bd, payload=ProjectDataHandoverCreate(
        project_id=project.id,
        from_workstream_id=ws["lidar"].id,
        to_workstream_id=ws["bim"].id,
        title="LiDAR source for BIM",
        expected_output="Classified LiDAR output",
    ))
    db.flush()
    return finance, bd, mobile, lidar, bim, project, opportunity, ws, first, second


def start_and_accept_first(db, mobile, lidar, ws, first):
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
        payload=ProjectDataHandoverSubmit(output_reference="shared://v719/mobile/final"),
    )
    decide_project_handover(
        db,
        handover=first,
        actor=lidar,
        effective_role="lidar",
        payload=ProjectDataHandoverDecision(decision="accepted"),
    )


def complete_full_chain(db, mobile, lidar, bim, ws, first, second):
    start_and_accept_first(db, mobile, lidar, ws, first)
    complete_department_workstream(
        db,
        workstream=ws["mobile_mapping"],
        actor=mobile,
        effective_role="mobile_mapping",
        payload=DepartmentCompletionRequest(note="Mobile mapping final output accepted"),
    )
    update_project_workstream_status(
        db,
        row=ws["lidar"],
        actor=lidar,
        effective_role="lidar",
        payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
    )
    submit_project_handover(
        db,
        handover=second,
        actor=lidar,
        effective_role="lidar",
        payload=ProjectDataHandoverSubmit(output_reference="shared://v719/lidar/final"),
    )
    decide_project_handover(
        db,
        handover=second,
        actor=bim,
        effective_role="bim",
        payload=ProjectDataHandoverDecision(decision="accepted"),
    )
    complete_department_workstream(
        db,
        workstream=ws["lidar"],
        actor=lidar,
        effective_role="lidar",
        payload=DepartmentCompletionRequest(note="LiDAR final output accepted by BIM"),
    )
    update_project_workstream_status(
        db,
        row=ws["bim"],
        actor=bim,
        effective_role="bim",
        payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
    )
    complete_department_workstream(
        db,
        workstream=ws["bim"],
        actor=bim,
        effective_role="bim",
        payload=DepartmentCompletionRequest(note="BIM deliverable complete"),
    )


def test_department_cannot_complete_until_outgoing_handover_is_accepted():
    with SessionLocal() as db:
        _, _, mobile, lidar, _, _, _, ws, first, _ = build_chain(db)
        update_project_workstream_status(
            db,
            row=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectWorkstreamStatusUpdate(status="in_progress"),
        )
        with pytest.raises(ValueError, match="outgoing data handovers"):
            complete_department_workstream(
                db,
                workstream=ws["mobile_mapping"],
                actor=mobile,
                effective_role="mobile_mapping",
                payload=DepartmentCompletionRequest(),
            )
        submit_project_handover(
            db,
            handover=first,
            actor=mobile,
            effective_role="mobile_mapping",
            payload=ProjectDataHandoverSubmit(output_reference="shared://v719/mobile/a1"),
        )
        decide_project_handover(
            db,
            handover=first,
            actor=lidar,
            effective_role="lidar",
            payload=ProjectDataHandoverDecision(decision="accepted"),
        )
        row = complete_department_workstream(
            db,
            workstream=ws["mobile_mapping"],
            actor=mobile,
            effective_role="mobile_mapping",
            payload=DepartmentCompletionRequest(note="Done"),
        )
        assert row.status == "completed"


def test_final_department_completion_notifies_bd_that_master_delivery_is_ready():
    with SessionLocal() as db:
        _, bd, mobile, lidar, bim, project, _, ws, first, second = build_chain(db)
        complete_full_chain(db, mobile, lidar, bim, ws, first, second)
        db.commit()
        created = create_bd_project_ready_notification(db, project_id=project.id)
        db.commit()
        assert len(created) == 1
        assert created[0].recipient_user_id == bd.id
        assert created[0].event_type == "bd.project.ready_for_final_delivery"


def test_master_delivery_is_blocked_until_every_team_and_handover_is_complete():
    with SessionLocal() as db:
        _, bd, mobile, lidar, bim, project, opportunity, ws, first, second = build_chain(db)
        with pytest.raises(ValueError, match="not ready"):
            record_master_project_delivery(
                db,
                project_id=project.id,
                actor=bd,
                payload=MasterProjectDeliveryRequest(final_output_reference="shared://v719/master"),
            )
        complete_full_chain(db, mobile, lidar, bim, ws, first, second)
        readiness = project_completion_readiness(db, project_id=project.id)
        assert readiness["ready"] is True
        completion = record_master_project_delivery(
            db,
            project_id=project.id,
            actor=bd,
            payload=MasterProjectDeliveryRequest(final_output_reference="shared://v719/master", remarks="Client delivery package"),
        )
        assert completion.finance_status == "pending_billing"
        assert opportunity.stage == "delivered"


def test_master_delivery_notifies_only_finance_using_existing_event_contract():
    with SessionLocal() as db:
        finance, bd, mobile, lidar, bim, project, _, ws, first, second = build_chain(db)
        complete_full_chain(db, mobile, lidar, bim, ws, first, second)
        completion = record_master_project_delivery(
            db,
            project_id=project.id,
            actor=bd,
            payload=MasterProjectDeliveryRequest(final_output_reference="shared://v719/master"),
        )
        db.commit()
        created = create_finance_master_completion_notifications(db, completion_id=completion.id)
        db.commit()
        assert len(created) == 1
        assert created[0].recipient_user_id == finance.id
        assert created[0].event_type == "finance.project_completed"
        assert created[0].dedupe_key == f"finance.project_completed.{project.id}"


def test_finance_closure_requires_billing_start_and_notifies_bd_when_closed():
    with SessionLocal() as db:
        finance, bd, mobile, lidar, bim, project, _, ws, first, second = build_chain(db)
        complete_full_chain(db, mobile, lidar, bim, ws, first, second)
        completion = record_master_project_delivery(
            db,
            project_id=project.id,
            actor=bd,
            payload=MasterProjectDeliveryRequest(final_output_reference="shared://v719/master"),
        )
        with pytest.raises(ValueError, match="Start billing"):
            update_finance_closure(
                db,
                completion=completion,
                actor=finance,
                effective_role="finance",
                payload=FinanceClosureUpdate(status="financially_closed"),
            )
        update_finance_closure(
            db,
            completion=completion,
            actor=finance,
            effective_role="finance",
            payload=FinanceClosureUpdate(status="billing_in_progress", note="Invoice preparation started"),
        )
        closed = update_finance_closure(
            db,
            completion=completion,
            actor=finance,
            effective_role="finance",
            payload=FinanceClosureUpdate(status="financially_closed", note="Payment and settlement complete"),
        )
        assert closed.finance_status == "financially_closed"
        assert db.scalar(select(BDOpportunity).where(BDOpportunity.linked_project_id == project.id)).stage == "closed"
        db.commit()
        notifications = create_bd_financial_closure_notification(db, completion_id=closed.id)
        db.commit()
        assert len(notifications) == 1
        assert notifications[0].recipient_user_id == bd.id
        assert notifications[0].event_type == "bd.project.financially_closed"


def test_legacy_ortho_final_delivery_is_blocked_for_multi_department_master_project():
    with SessionLocal() as db:
        _, _, _, _, _, project, _, _, _, _ = build_chain(db)
        with pytest.raises(ValueError, match="multi-department Master Project"):
            assert_legacy_ortho_final_delivery_allowed(db, project_id=project.id)
