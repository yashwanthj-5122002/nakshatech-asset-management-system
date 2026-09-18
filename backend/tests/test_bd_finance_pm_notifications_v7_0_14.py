from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProjectMasterProfile
from app.modules.finance.schemas import FinanceClientProjectCreateRequest, FinanceClientProjectUpdateRequest
from app.modules.finance.service import create_client_project, update_client_project
from app.modules.notifications.models import GlobalNotification
from app.modules.operations.models import BDOpportunity, OrthoProjectMember, OrthoProjectProfile
from app.modules.operations.schemas import BDOpportunityCreate, BDProjectLink, BDProjectManagerUpdate, BDStageUpdate
from app.modules.operations.service import (
    assign_bd_project_manager,
    create_bd_opportunity,
    create_finance_bd_opportunity_notifications,
    create_finance_project_completion_notifications,
    link_bd_project,
    update_bd_stage,
)


def make_user(db, email: str, name: str, role: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-only",
        role=role,
        branch="Head Office",
        department=role.title(),
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def make_client(db, finance: User) -> FinanceClient:
    row = FinanceClient(
        client_code="V714-C01",
        client_name="V714 Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="BD V714",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(row)
    db.flush()
    return row


def create_payload(pm_id: int | None) -> FinanceClientProjectCreateRequest:
    return FinanceClientProjectCreateRequest(
        project_code="V714-P01",
        project_name="V714 Ortho Project",
        task="Ortho production",
        project_status="active",
        project_manager_id=pm_id,
        reporting_manager_id=None,
        assigned_employee_ids=[],
        project_source_team="bd_team",
        project_source_person_name="BD V714",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 10, 10),
        is_active=True,
    )


def update_payload(pm_id: int | None) -> FinanceClientProjectUpdateRequest:
    return FinanceClientProjectUpdateRequest(
        project_name="V714 Ortho Project Updated",
        task="Ortho production updated",
        project_status="active",
        project_manager_id=pm_id,
        reporting_manager_id=None,
        assigned_employee_ids=[],
        project_source_team="bd_team",
        project_source_person_name="BD V714",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 10, 20),
        is_active=True,
    )


def test_finance_cannot_assign_or_change_project_manager_but_bd_can():
    with SessionLocal() as db:
        finance = make_user(db, "finance.v714@nakshatech.com", "Finance V714", "finance")
        bd = make_user(db, "bd.v714@nakshatech.com", "BD V714", "bd")
        pm1 = make_user(db, "ortho.pm1.v714@nakshatech.com", "Ortho PM One", "ortho")
        pm2 = make_user(db, "ortho.pm2.v714@nakshatech.com", "Ortho PM Two", "ortho")
        client = make_client(db, finance)

        project = create_client_project(db, client=client, actor=finance, payload=create_payload(pm1.id))
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id is None

        opportunity = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
            title="V714 secured work", client_id=client.id, requirement="Orthomosaic + DTM", priority="high"
        ))
        update_bd_stage(db, opportunity=opportunity, actor=bd, payload=BDStageUpdate(stage="accepted"))
        opportunity, profile = link_bd_project(
            db, opportunity=opportunity, actor=bd,
            payload=BDProjectLink(project_id=project.id, project_manager_id=pm1.id),
        )
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == pm1.id
        assert profile.project_manager_user_id == pm1.id

        update_client_project(db, project=project, actor=finance, payload=update_payload(pm2.id))
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == pm1.id

        changed = assign_bd_project_manager(
            db, opportunity=opportunity, actor=bd,
            payload=BDProjectManagerUpdate(project_manager_id=pm2.id),
        )
        assert changed.id == pm2.id
        assert db.get(FinanceProjectMasterProfile, project.id).project_manager_id == pm2.id
        assert db.get(OrthoProjectProfile, project.id).project_manager_user_id == pm2.id
        active_pm_members = list(db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id,
            OrthoProjectMember.member_role == "project_manager",
            OrthoProjectMember.is_active.is_(True),
        )).all())
        assert [row.user_id for row in active_pm_members] == [pm2.id]


def test_all_active_finance_users_receive_bd_dashboard_notification():
    with SessionLocal() as db:
        finance1 = make_user(db, "finance1.v714@nakshatech.com", "Finance One", "finance")
        finance2 = make_user(db, "finance2.v714@nakshatech.com", "Finance Two", "finance")
        bd = make_user(db, "bd.notice.v714@nakshatech.com", "BD Notice", "bd")
        make_user(db, "employee.v714@nakshatech.com", "Employee", "employee")
        opportunity = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
            title="Immediate Finance Notice", client_name="New Prospect Ltd", requirement="New geospatial project", priority="urgent"
        ))
        created = create_finance_bd_opportunity_notifications(db, opportunity_id=opportunity.id)
        db.flush()
        assert {row.recipient_user_id for row in created} == {finance1.id, finance2.id}
        assert all(row.event_type == "finance.bd_opportunity.created" for row in created)
        assert all("New Prospect Ltd" in row.message for row in created)


def test_project_completion_notification_targets_finance_only():
    with SessionLocal() as db:
        finance = make_user(db, "finance.complete.v714@nakshatech.com", "Finance Complete", "finance")
        bd = make_user(db, "bd.complete.v714@nakshatech.com", "BD Complete", "bd")
        pm = make_user(db, "ortho.complete.v714@nakshatech.com", "Ortho Complete", "ortho")
        client = make_client(db, finance)
        project = create_client_project(db, client=client, actor=finance, payload=create_payload(None))
        opportunity = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
            title="Completion flow", client_id=client.id, requirement="Delivery", priority="medium"
        ))
        update_bd_stage(db, opportunity=opportunity, actor=bd, payload=BDStageUpdate(stage="accepted"))
        link_bd_project(db, opportunity=opportunity, actor=bd, payload=BDProjectLink(project_id=project.id, project_manager_id=pm.id))

        created = create_finance_project_completion_notifications(
            db, project_id=project.id, package_count=3, delivered_by_id=pm.id, remarks="Final files delivered"
        )
        db.flush()
        assert len(created) == 1
        assert created[0].recipient_user_id == finance.id
        assert created[0].event_type == "finance.project_completed"
        assert "Finance action" in created[0].message
        assert not db.scalars(select(GlobalNotification).where(GlobalNotification.recipient_user_id == bd.id)).all()
