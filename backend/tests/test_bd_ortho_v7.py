from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.models import BDOpportunity, OrthoDailyUpdate, OrthoProjectMember, OrthoProjectProfile, OrthoReview, OrthoWorkPackage, OrthoWorkSession
from app.modules.operations.schemas import (
    BDOpportunityCreate,
    BDProjectLink,
    BDStageUpdate,
    OrthoDeliveryRequest,
    OrthoDailyUpdateRequest,
    OrthoProjectActivate,
    OrthoMemberUpsert,
    OrthoReviewRequest,
    OrthoTeamSetup,
    OrthoWorkPackageAssignments,
    OrthoWorkPackageCreate,
)
from app.modules.operations.service import (
    activate_ortho_project,
    bd_dashboard_payload,
    configure_project_team,
    corporate_summary_payload,
    create_bd_opportunity,
    create_work_package,
    finalize_delivery,
    link_bd_project,
    ortho_dashboard_payload,
    record_daily_update,
    review_package,
    send_ortho_assignment_email,
    submit_to_qc,
    update_bd_stage,
    update_package_assignments,
    upsert_project_member,
    work_action,
)


def user(db, email: str, name: str, role: str, department: str | None = None) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="test-hash",
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


def project_fixture(db):
    finance = user(db, "finance.v7@nakshatech.com", "Finance V7", "finance", "Finance")
    pm = user(db, "ortho.pm.v7@nakshatech.com", "Ortho PM", "ortho", "Ortho")
    # Team Leader / Production / QC / QA remain normal employee accounts. A PM
    # assignment grants only the matching Ortho project responsibility; it does
    # not replace their Employee role or create a second login.
    tl = user(db, "employee.tl.v7@nakshatech.com", "Employee TL", "employee", "Production")
    prod = user(db, "employee.prod.v7@nakshatech.com", "Employee Production", "employee", "Production")
    qc = user(db, "employee.qc.v7@nakshatech.com", "Employee QC", "employee", "Quality")
    qa = user(db, "employee.qa.v7@nakshatech.com", "Employee QA", "employee", "Quality")
    bd = user(db, "bd.v7@nakshatech.com", "BD V7", "bd", "Business Development")
    management = user(db, "management.v7@nakshatech.com", "Management V7", "management", "Management")
    client = FinanceClient(
        client_code="NT-V7-C01",
        client_name="V7 Client",
        contact_person_name="Client Contact",
        contact_person_phone="9999999999",
        country="India",
        source_team="bd_team",
        source_person_name="BD V7",
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(client)
    db.flush()
    project = FinanceProject(
        project_code="NT1021-V7",
        project_name="Ortho Reference Project",
        client_id=client.id,
        client_name=client.client_name,
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        is_active=True,
        created_by_id=finance.id,
    )
    db.add(project)
    db.flush()
    db.add(FinanceProjectMasterProfile(
        project_id=project.id,
        project_status="active",
        project_manager_id=pm.id,
        created_by_id=finance.id,
        updated_by_id=finance.id,
    ))
    db.commit()
    return finance, pm, tl, prod, qc, qa, bd, management, client, project


def _link_and_assign(db, *, pm, tl, prod, qc, qa, bd, client, project, title="Full V7 Workflow"):
    opp = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
        title=title, client_id=client.id, requirement="Ortho production", priority="medium"
    ))
    update_bd_stage(db, opportunity=opp, actor=bd, payload=BDStageUpdate(stage="accepted"))
    _, profile = link_bd_project(db, opportunity=opp, actor=bd, payload=BDProjectLink(project_id=project.id))
    db.flush()
    for target, role in [(tl, "team_leader"), (prod, "production"), (qc, "qc"), (qa, "qa")]:
        upsert_project_member(db, project_id=project.id, actor=pm, payload=OrthoMemberUpsert(user_id=target.id, member_role=role))
    return opp, profile



def test_ortho_activation_requires_finance_project_manager_assignment():
    with SessionLocal() as db:
        finance = user(db, "finance.activate.v708@nakshatech.com", "Finance Activate", "finance", "Finance")
        pm = user(db, "ortho.activate.v708@nakshatech.com", "Ortho Activate PM", "ortho", "Ortho")
        client = FinanceClient(
            client_code="NT-V708-C01",
            client_name="V708 Activation Client",
            contact_person_name="Client Contact",
            contact_person_phone="9999999998",
            country="India",
            source_team="bd_team",
            source_person_name="BD",
            is_active=True,
            created_by_id=finance.id,
        )
        db.add(client); db.flush()
        project = FinanceProject(
            project_code="NT-V708-P01",
            project_name="Finance PM Required",
            client_id=client.id,
            client_name=client.client_name,
            start_date=date(2026, 9, 4),
            end_date=date(2026, 9, 30),
            is_active=True,
            created_by_id=finance.id,
        )
        db.add(project); db.flush()
        db.add(FinanceProjectMasterProfile(
            project_id=project.id, project_status="active", project_manager_id=None,
            created_by_id=finance.id, updated_by_id=finance.id,
        ))
        db.flush()

        with pytest.raises(ValueError, match="Business Development must assign the Project Manager"):
            activate_ortho_project(db, actor=pm, payload=OrthoProjectActivate(project_id=project.id))

        master = db.get(FinanceProjectMasterProfile, project.id)
        master.project_manager_id = pm.id
        db.flush()
        profile = activate_ortho_project(db, actor=pm, payload=OrthoProjectActivate(project_id=project.id, total_area=25))
        assert profile.project_manager_user_id == pm.id
        assert float(profile.total_area or 0) == 25.0

def test_bd_handoff_links_only_existing_finance_project_master():
    with SessionLocal() as db:
        _, pm, _, _, _, _, bd, _, client, project = project_fixture(db)
        opp = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
            title="Messina Ortho Work",
            client_id=client.id,
            requirement="DTM + Orthomosaic technical production",
            priority="high",
        ))
        update_bd_stage(db, opportunity=opp, actor=bd, payload=BDStageUpdate(stage="accepted", comments="Client accepted"))
        opp, profile = link_bd_project(db, opportunity=opp, actor=bd, payload=BDProjectLink(project_id=project.id))
        db.commit()

        assert opp.linked_project_id == project.id
        assert opp.stage == "project_linked"
        assert profile.project_id == project.id
        assert profile.project_manager_user_id == pm.id
        assert db.get(FinanceProject, project.id).project_code == "NT1021-V7"

        dashboard = bd_dashboard_payload(db, actor=bd, effective_role="bd")
        assert dashboard["summary"]["linked"] == 1
        assert dashboard["opportunities"][0]["linked_project"]["project_code"] == "NT1021-V7"


def test_project_manager_operates_production_qc_qa_rework_and_delivery_for_assigned_employees():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, _, client, project = project_fixture(db)
        opp, profile = _link_and_assign(db, pm=pm, tl=tl, prod=prod, qc=qc, qa=qa, bd=bd, client=client, project=project)

        package = create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="102_02_Messina",
            package_name="102_02 Messina",
            area=15,
            area_unit="ha",
            target_hours=6,
            team_leader_user_id=tl.id,
            production_user_id=prod.id,
            qc_user_id=qc.id,
            qa_user_id=qa.id,
        ))
        db.flush()

        work_action(db, work_package=package, actor=pm, action="start")
        running = db.scalar(select(OrthoWorkSession).where(OrthoWorkSession.work_package_id == package.id, OrthoWorkSession.ended_at.is_(None)))
        assert running is not None
        assert running.user_id == prod.id  # time belongs to assigned employee, not PM

        work_action(db, work_package=package, actor=pm, action="pause")
        work_action(db, work_package=package, actor=pm, action="resume")
        work_action(db, work_package=package, actor=pm, action="complete")
        submit_to_qc(db, work_package=package, actor=pm)
        assert package.current_stage == "qc"

        review_package(db, work_package=package, actor=pm, review_type="qc", payload=OrthoReviewRequest(decision="reject", comments="Edge mismatch"))
        assert package.current_stage == "production_rework"
        assert package.rework_source == "qc"

        work_action(db, work_package=package, actor=pm, action="start")
        work_action(db, work_package=package, actor=pm, action="complete")
        submit_to_qc(db, work_package=package, actor=pm)
        review_package(db, work_package=package, actor=pm, review_type="qc", payload=OrthoReviewRequest(decision="approve", comments="QC passed"))
        assert package.current_stage == "qa"

        review_package(db, work_package=package, actor=pm, review_type="qa", payload=OrthoReviewRequest(decision="reject", comments="Final seam issue"))
        assert package.current_stage == "production_rework"
        assert package.rework_source == "qa"

        work_action(db, work_package=package, actor=pm, action="start")
        work_action(db, work_package=package, actor=pm, action="complete")
        submit_to_qc(db, work_package=package, actor=pm)
        review_package(db, work_package=package, actor=pm, review_type="qc", payload=OrthoReviewRequest(decision="approve"))
        review_package(db, work_package=package, actor=pm, review_type="qa", payload=OrthoReviewRequest(decision="approve"))
        assert package.current_stage == "delivery_ready"

        delivery = finalize_delivery(db, profile=profile, actor=pm, payload=OrthoDeliveryRequest(remarks="Delivered to BD"))
        db.commit()
        assert delivery.package_count == 1
        assert package.current_stage == "delivered"
        assert db.get(OrthoProjectProfile, project.id).status == "delivered"
        saved_opp = db.get(BDOpportunity, opp.id)
        assert saved_opp.stage == "delivered"
        reviews = db.scalars(select(OrthoReview).where(OrthoReview.work_package_id == package.id)).all()
        assert [(r.review_type, r.attempt_no, r.decision) for r in reviews] == [
            ("qc", 1, "reject"), ("qc", 2, "approve"), ("qa", 1, "reject"), ("qc", 3, "approve"), ("qa", 2, "approve")
        ]
        assert all(review.reviewer_user_id == pm.id for review in reviews)


def test_assigned_employees_update_only_their_responsibility_and_pm_can_override_all():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, _, client, project = project_fixture(db)
        _link_and_assign(db, pm=pm, tl=tl, prod=prod, qc=qc, qa=qa, bd=bd, client=client, project=project, title="Role Collaboration Guard")
        package = create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="ROLE-COLLAB", package_name="Role Collaboration", team_leader_user_id=tl.id,
            production_user_id=prod.id, qc_user_id=qc.id, qa_user_id=qa.id,
        ))
        db.flush()

        # Team Leader records daily progress, but cannot change PM-owned assignments.
        daily = record_daily_update(db, work_package=package, actor=tl, payload=OrthoDailyUpdateRequest(
            update_date=date(2026, 9, 4), achieved_area=2.5, progress_percent=25,
            hours_spent=4, status="on_track", remarks="Daily production progressing",
        ))
        assert daily.updated_by_id == tl.id
        assert float(daily.progress_percent or 0) == 25.0
        with pytest.raises(PermissionError, match="Project Manager"):
            update_package_assignments(db, work_package=package, actor=tl, payload=OrthoWorkPackageAssignments(production_user_id=prod.id))

        # Production employee operates their package and submits it to QC.
        work_action(db, work_package=package, actor=prod, action="start")
        work_action(db, work_package=package, actor=prod, action="complete")
        submit_to_qc(db, work_package=package, actor=prod)
        assert package.current_stage == "qc"
        with pytest.raises(PermissionError, match="assigned QA employee|Project Manager"):
            review_package(db, work_package=package, actor=prod, review_type="qa", payload=OrthoReviewRequest(decision="approve"))

        # QC employee records QC only.
        review_package(db, work_package=package, actor=qc, review_type="qc", payload=OrthoReviewRequest(decision="approve", comments="QC passed"))
        assert package.current_stage == "qa"
        with pytest.raises(PermissionError, match="assigned QA employee|Project Manager"):
            review_package(db, work_package=package, actor=qc, review_type="qa", payload=OrthoReviewRequest(decision="approve"))

        # QA employee records QA. PM remains a valid override at every stage.
        review_package(db, work_package=package, actor=qa, review_type="qa", payload=OrthoReviewRequest(decision="reject", comments="QA rework"))
        assert package.current_stage == "production_rework"
        work_action(db, work_package=package, actor=pm, action="start")
        work_action(db, work_package=package, actor=pm, action="complete")
        submit_to_qc(db, work_package=package, actor=pm)
        review_package(db, work_package=package, actor=pm, review_type="qc", payload=OrthoReviewRequest(decision="approve"))
        review_package(db, work_package=package, actor=pm, review_type="qa", payload=OrthoReviewRequest(decision="approve"))
        assert package.current_stage == "delivery_ready"


def test_ortho_dashboard_scopes_pm_participant_and_management_views():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, management, client, project = project_fixture(db)
        _link_and_assign(db, pm=pm, tl=tl, prod=prod, qc=qc, qa=qa, bd=bd, client=client, project=project, title="Scope Test")
        create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="102_04_Messina", package_name="102_04", production_user_id=prod.id,
            qc_user_id=qc.id, qa_user_id=qa.id, team_leader_user_id=tl.id,
        ))
        outsider = user(db, "ortho.outsider.v7@nakshatech.com", "Ortho Outsider", "ortho", "Ortho")
        employee_outsider = user(db, "employee.outsider.v7@nakshatech.com", "Employee Outsider", "employee", "Production")
        db.commit()

        pm_view = ortho_dashboard_payload(db, actor=pm, effective_role="ortho")
        assert pm_view["viewer_mode"] == "project_manager"
        assert all(pm_view["view_permissions"].values())
        assert len(pm_view["projects"]) == 1
        assert all(pm_view["projects"][0]["permissions"].values())

        # Assigned employee keeps the normal employee role but can access only
        # the project/section responsibility explicitly assigned by the PM.
        employee_service_view = ortho_dashboard_payload(db, actor=prod, effective_role="employee")
        assert employee_service_view["viewer_mode"] == "participant"
        assert len(employee_service_view["projects"]) == 1
        assert employee_service_view["view_permissions"]["production"] is True
        assert employee_service_view["view_permissions"]["project_manager"] is False
        assert employee_service_view["view_permissions"]["team_leader"] is False
        assert employee_service_view["view_permissions"]["qc"] is False
        assert employee_service_view["view_permissions"]["qa"] is False
        employee_pkg = employee_service_view["projects"][0]["work_packages"][0]
        assert employee_pkg["permissions"]["can_production"] is True
        assert employee_pkg["permissions"]["can_daily_update"] is False
        assert employee_pkg["permissions"]["can_qc"] is False
        assert employee_pkg["permissions"]["can_qa"] is False

        outsider_view = ortho_dashboard_payload(db, actor=outsider, effective_role="ortho")
        assert outsider_view["projects"] == []
        assert not any(outsider_view["view_permissions"].values())

        employee_outsider_view = ortho_dashboard_payload(db, actor=employee_outsider, effective_role="employee")
        assert employee_outsider_view["viewer_mode"] == "participant"
        assert employee_outsider_view["projects"] == []
        assert not any(employee_outsider_view["view_permissions"].values())

        management_view = ortho_dashboard_payload(db, actor=management, effective_role="management")
        assert management_view["viewer_mode"] == "read_only"
        assert all(management_view["view_permissions"].values())
        assert len(management_view["projects"]) == 1


def test_pm_can_assign_existing_employee_by_typed_email_and_assignment_email_contains_project_context(monkeypatch):
    sent: list[dict] = []

    def fake_send_email(**kwargs):
        sent.append(kwargs)

    monkeypatch.setattr("app.modules.operations.service.send_email", fake_send_email)
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, _, client, project = project_fixture(db)
        opp = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(
            title="Email Assignment", client_id=client.id, requirement="Ortho collaboration assignment"
        ))
        update_bd_stage(db, opportunity=opp, actor=bd, payload=BDStageUpdate(stage="accepted"))
        _, profile = link_bd_project(db, opportunity=opp, actor=bd, payload=BDProjectLink(project_id=project.id))
        profile.scope_text = "Orthomosaic + QC + QA delivery"
        db.flush()

        member = upsert_project_member(db, project_id=project.id, actor=pm, payload=OrthoMemberUpsert(
            employee_name="Employee TL",
            employee_email=tl.email,
            member_role="team_leader",
            send_email=True,
        ))
        assert member.user_id == tl.id
        send_ortho_assignment_email(db, project_id=project.id, member=member)

        assert len(sent) == 1
        message = sent[0]
        assert message["recipient"] == tl.email
        assert "NT1021-V7" in message["subject"]
        assert "Role / Responsibility: Team Leader" in message["body"]
        assert "Project Manager: Ortho PM" in message["body"]
        assert f"Project Manager Email: {pm.email}" in message["body"]
        assert "V7 Client" in message["body"]
        assert "/ortho" in message["body"]
        assert "daily project/work-package update" in message["body"]


def test_team_leader_daily_update_is_append_only_history_and_pm_can_also_update():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, _, client, project = project_fixture(db)
        _link_and_assign(db, pm=pm, tl=tl, prod=prod, qc=qc, qa=qa, bd=bd, client=client, project=project, title="Daily History")
        package = create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="DAILY-01", package_name="Daily Area", team_leader_user_id=tl.id,
            production_user_id=prod.id, qc_user_id=qc.id, qa_user_id=qa.id,
        ))

        first = record_daily_update(db, work_package=package, actor=tl, payload=OrthoDailyUpdateRequest(
            update_date=date(2026, 9, 4), achieved_area=3, progress_percent=30, hours_spent=6,
            status="on_track", remarks="TL update",
        ))
        second = record_daily_update(db, work_package=package, actor=pm, payload=OrthoDailyUpdateRequest(
            update_date=date(2026, 9, 4), achieved_area=4, progress_percent=40, hours_spent=7,
            status="at_risk", blockers="Cloud gap", remarks="PM follow-up",
        ))
        db.commit()

        rows = db.scalars(select(OrthoDailyUpdate).where(OrthoDailyUpdate.work_package_id == package.id).order_by(OrthoDailyUpdate.id)).all()
        assert [row.id for row in rows] == [first.id, second.id]
        assert [row.updated_by_id for row in rows] == [tl.id, pm.id]
        assert rows[0].remarks == "TL update"
        assert rows[1].blockers == "Cloud gap"


def test_final_delivery_blocked_until_every_package_is_qa_approved():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, bd, _, client, project = project_fixture(db)
        _, profile = _link_and_assign(db, pm=pm, tl=tl, prod=prod, qc=qc, qa=qa, bd=bd, client=client, project=project, title="Delivery Guard")
        create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="P1", package_name="Package 1", production_user_id=prod.id,
            qc_user_id=qc.id, qa_user_id=qa.id, team_leader_user_id=tl.id,
        ))
        with pytest.raises(ValueError, match="All work packages"):
            finalize_delivery(db, profile=profile, actor=pm, payload=OrthoDeliveryRequest())


def test_finance_project_master_remains_authoritative_for_project_manager():
    with SessionLocal() as db:
        finance, pm, _, _, _, _, bd, _, client, project = project_fixture(db)
        opp = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(title="PM Authority", client_id=client.id, requirement="PM authority"))
        update_bd_stage(db, opportunity=opp, actor=bd, payload=BDStageUpdate(stage="accepted"))
        link_bd_project(db, opportunity=opp, actor=bd, payload=BDProjectLink(project_id=project.id))
        replacement_pm = user(db, "ortho.pm2.v7@nakshatech.com", "Replacement PM", "ortho", "Ortho")
        master = db.get(FinanceProjectMasterProfile, project.id)
        master.project_manager_id = replacement_pm.id
        master.updated_by_id = finance.id
        db.commit()

        old_view = ortho_dashboard_payload(db, actor=pm, effective_role="ortho")
        new_view = ortho_dashboard_payload(db, actor=replacement_pm, effective_role="ortho")
        assert old_view["projects"] == []
        assert len(new_view["projects"]) == 1
        assert new_view["projects"][0]["profile"]["project_manager_user_id"] == replacement_pm.id


def test_corporate_summary_aggregates_bd_and_ortho_without_mutating_finance():
    with SessionLocal() as db:
        _, _, _, _, _, _, bd, _, client, project = project_fixture(db)
        opp = create_bd_opportunity(db, actor=bd, payload=BDOpportunityCreate(title="Summary", client_id=client.id, requirement="Summary"))
        update_bd_stage(db, opportunity=opp, actor=bd, payload=BDStageUpdate(stage="accepted"))
        link_bd_project(db, opportunity=opp, actor=bd, payload=BDProjectLink(project_id=project.id))
        db.commit()
        summary = corporate_summary_payload(db)
        assert summary["bd"]["total_opportunities"] == 1
        assert summary["bd"]["linked_projects"] == 1
        assert summary["ortho"]["projects"] == 1
        assert db.get(FinanceProject, project.id).project_code == "NT1021-V7"


def test_v710_fresh_finance_pm_can_discover_assignment_before_ortho_activation():
    """A Finance PM assignment must be discoverable before any Ortho profile exists.

    V7.0.9 only returned Finance Project Master rows after the user already had a
    visible Ortho PM project, which made first-project activation circular. V7.0.10
    returns only the Finance projects assigned to the logged-in Ortho PM and does
    not leak projects assigned to another PM.
    """
    with SessionLocal() as db:
        finance = user(db, "finance.v710@nakshatech.com", "Finance V710", "finance", "Finance")
        pm = user(db, "ortho.fresh.v710@nakshatech.com", "Fresh Ortho PM", "ortho", "Ortho")
        other_pm = user(db, "ortho.other.v710@nakshatech.com", "Other Ortho PM", "ortho", "Ortho")
        client = FinanceClient(
            client_code="NT-V710-C01",
            client_name="V710 Client",
            contact_person_name="Client Contact",
            contact_person_phone="9999999910",
            country="India",
            source_team="bd_team",
            source_person_name="BD",
            is_active=True,
            created_by_id=finance.id,
        )
        db.add(client); db.flush()

        assigned = FinanceProject(
            project_code="NT-V710-P01",
            project_name="Fresh PM Assignment",
            client_id=client.id,
            client_name=client.client_name,
            start_date=date(2026, 9, 4),
            end_date=date(2026, 9, 30),
            is_active=True,
            created_by_id=finance.id,
        )
        other = FinanceProject(
            project_code="NT-V710-P02",
            project_name="Other PM Assignment",
            client_id=client.id,
            client_name=client.client_name,
            start_date=date(2026, 9, 4),
            end_date=date(2026, 9, 30),
            is_active=True,
            created_by_id=finance.id,
        )
        db.add_all([assigned, other]); db.flush()
        db.add_all([
            FinanceProjectMasterProfile(
                project_id=assigned.id,
                project_status="active",
                project_manager_id=pm.id,
                created_by_id=finance.id,
                updated_by_id=finance.id,
            ),
            FinanceProjectMasterProfile(
                project_id=other.id,
                project_status="active",
                project_manager_id=other_pm.id,
                created_by_id=finance.id,
                updated_by_id=finance.id,
            ),
        ])
        db.commit()

        dashboard = ortho_dashboard_payload(db, actor=pm, effective_role="ortho")
        assert dashboard["viewer_mode"] == "project_manager"
        assert dashboard["view_permissions"]["project_manager"] is True
        assert dashboard["projects"] == []
        assert [row["project_code"] for row in dashboard["project_master"]] == ["NT-V710-P01"]

        activate_ortho_project(db, actor=pm, payload=OrthoProjectActivate(project_id=assigned.id, total_area=60))
        db.commit()
        dashboard_after = ortho_dashboard_payload(db, actor=pm, effective_role="ortho")
        assert [row["project"]["project_code"] for row in dashboard_after["projects"]] == ["NT-V710-P01"]
        assert [row["project_code"] for row in dashboard_after["project_master"]] == ["NT-V710-P01"]


def test_v713_project_team_setup_saves_four_roles_and_fills_only_unassigned_package_owners():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, _, _, _, project = project_fixture(db)
        activate_ortho_project(db, actor=pm, payload=OrthoProjectActivate(project_id=project.id, total_area=30))
        package = create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="V713-WP-01", package_name="V713 Unassigned Package", area=10, target_hours=8,
        ))
        assert package.team_leader_user_id is None
        assert package.production_user_id is None
        assert package.qc_user_id is None
        assert package.qa_user_id is None

        rows = configure_project_team(db, project_id=project.id, actor=pm, payload=OrthoTeamSetup(
            team_leader_user_id=tl.id,
            production_user_id=prod.id,
            qc_user_id=qc.id,
            qa_user_id=qa.id,
            apply_to_unassigned_packages=True,
        ))
        db.flush()

        assert {row.member_role for row in rows} == {"team_leader", "production", "qc", "qa"}
        assert all(row.is_active for row in rows)
        db.refresh(package)
        assert package.team_leader_user_id == tl.id
        assert package.production_user_id == prod.id
        assert package.qc_user_id == qc.id
        assert package.qa_user_id == qa.id
        assert tl.role == "employee"
        assert prod.role == "employee"
        assert qc.role == "employee"
        assert qa.role == "employee"


def test_v713_project_team_reassignment_does_not_overwrite_explicit_package_assignment():
    with SessionLocal() as db:
        _, pm, tl, prod, qc, qa, _, _, _, project = project_fixture(db)
        alternate_tl = user(db, "employee.alt.tl.v713@nakshatech.com", "Alternate TL", "employee", "Production")
        activate_ortho_project(db, actor=pm, payload=OrthoProjectActivate(project_id=project.id, total_area=30))
        configure_project_team(db, project_id=project.id, actor=pm, payload=OrthoTeamSetup(
            team_leader_user_id=tl.id, production_user_id=prod.id, qc_user_id=qc.id, qa_user_id=qa.id,
        ))
        package = create_work_package(db, project_id=project.id, actor=pm, payload=OrthoWorkPackageCreate(
            package_code="V713-WP-02", package_name="V713 Explicit Owner", area=10,
            team_leader_user_id=tl.id, production_user_id=prod.id, qc_user_id=qc.id, qa_user_id=qa.id,
        ))
        configure_project_team(db, project_id=project.id, actor=pm, payload=OrthoTeamSetup(
            team_leader_user_id=alternate_tl.id, production_user_id=prod.id, qc_user_id=qc.id, qa_user_id=qa.id,
            apply_to_unassigned_packages=True,
        ))
        db.flush(); db.refresh(package)
        assert package.team_leader_user_id == tl.id
        active_tl_rows = list(db.scalars(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == project.id,
            OrthoProjectMember.member_role == "team_leader",
            OrthoProjectMember.is_active.is_(True),
        )).all())
        assert {row.user_id for row in active_tl_rows} == {tl.id, alternate_tl.id}
