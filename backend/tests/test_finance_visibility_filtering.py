from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.service import all_projects, list_finance_clients
from app.modules.finance.visibility import (
    FINANCE_CLEANUP_PATCH_ID,
    exclude_hidden_clients,
    exclude_hidden_projects,
    filter_visible_project_ids,
    hidden_client_ids,
    hidden_project_ids,
)
from app.core.database import Base
from sqlalchemy import select

from app.models.entities import User
from app.modules.business import models as _business_models  # noqa: F401
from app.modules.commercial import models as _commercial_models  # noqa: F401
from app.modules.operations import lifecycle_models as _lifecycle_models  # noqa: F401
from app.modules.operations import monitoring_models as _monitoring_models  # noqa: F401
from app.modules.operations import completion_models as _completion_models  # noqa: F401
from app.modules.operations import handover_models as _handover_models  # noqa: F401
from app.modules.operations.models import OrthoProjectProfile, ProjectWorkstream, ProjectWorkflow
from app.modules.operations.workflow_service import finance_dashboard, ortho_dashboard
from app.modules.operations.lifecycle_service import lifecycle_dashboard
from app.modules.operations.monitoring_service import _visible_project_ids as monitoring_visible_project_ids
from app.modules.operations.completion_service import _visible_project_ids as completion_visible_project_ids
from app.modules.operations.handover_service import handover_dashboard_payload
from app.modules.operations.service import project_workstreams_dashboard_payload, visible_ortho_profiles
from app.modules.operations.reporting_service import reporting_dashboard_payload
from app.modules.commercial.service import (
    list_estimate_queue,
    list_project_expenses,
    list_vendor_invoices,
    management_analytics,
)
from app.modules.commercial.models import ProjectCommercialEstimateRevision, ProjectExpense, ProjectVendorInvoice
from app.modules.operations.service import corporate_summary_payload
from app.modules.operations.models import BDOpportunity
from app.modules.business.service import _project_rows
from app.modules.finance.reporting import (
    filtered_finance_claims,
    filtered_finance_payments,
    finance_report_payload,
    resolve_report_period,
)
from app.modules.finance.models import ExpenseClaim


def _seed_hidden_schema(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE IF NOT EXISTS patch_v81_hidden_entities (
                patch_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id BIGINT NOT NULL,
                entity_key TEXT NOT NULL,
                reason TEXT NOT NULL,
                hidden_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (patch_id, entity_type, entity_id)
            )
            """
        ))


def test_hidden_entities_are_excluded_from_registers():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_hidden_schema(engine)

    with Session(engine) as db:
        visible_client = FinanceClient(
            client_code="VIS001",
            client_name="Visible Client",
            contact_person_name="Someone",
            contact_person_phone="1",
            source_team="bd_team",
            source_person_name="BD",
            is_active=True,
        )
        hidden_client = FinanceClient(
            client_code="HID001",
            client_name="Hidden UAT Client",
            contact_person_name="Someone",
            contact_person_phone="1",
            source_team="bd_team",
            source_person_name="BD",
            is_active=True,
        )
        db.add_all([visible_client, hidden_client])
        db.flush()

        visible_project = FinanceProject(
            project_code="VIS-P1",
            project_name="Visible Project",
            client_id=visible_client.id,
            client_name=visible_client.client_name,
            project_source_team="bd_team",
            is_active=True,
        )
        hidden_project = FinanceProject(
            project_code="HID-P1",
            project_name="Hidden UAT Project",
            client_id=hidden_client.id,
            client_name=hidden_client.client_name,
            project_source_team="bd_team",
            is_active=True,
        )
        hidden_orphan = FinanceProject(
            project_code="HID-P2",
            project_name="Hidden Project Under Visible Client",
            client_id=visible_client.id,
            client_name=visible_client.client_name,
            project_source_team="bd_team",
            is_active=True,
        )
        db.add_all([visible_project, hidden_project, hidden_orphan])
        db.flush()

        db.execute(text(
            "INSERT INTO patch_v81_hidden_entities (patch_id, entity_type, entity_id, entity_key, reason) VALUES "
            "(:patch_id, 'finance_client', :client_id, 'HID001', 'cleanup'), "
            "(:patch_id, 'finance_project', :project_id, 'HID-P1', 'cleanup'), "
            "(:patch_id, 'finance_project', :orphan_id, 'HID-P2', 'cleanup')"
        ), {
            "patch_id": FINANCE_CLEANUP_PATCH_ID,
            "client_id": hidden_client.id,
            "project_id": hidden_project.id,
            "orphan_id": hidden_orphan.id,
        })
        db.commit()

        assert hidden_client_ids(db) == {hidden_client.id}
        assert hidden_project_ids(db) == {hidden_project.id, hidden_orphan.id}

        clients = list_finance_clients(db)
        assert [c.client_code for c in clients] == ["VIS001"]

        projects = all_projects(db)
        assert sorted(p.project_code for p in projects) == ["VIS-P1"]

        client_query = exclude_hidden_clients(db, select(FinanceClient))
        assert db.scalars(client_query).all() == [visible_client]

        project_query = exclude_hidden_projects(db, select(FinanceProject))
        rows = list(db.scalars(project_query).all())
        assert [p.project_code for p in rows] == ["VIS-P1"]


def test_missing_hidden_table_is_a_noop_filter():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        client = FinanceClient(
            client_code="ONLY1",
            client_name="Only Client",
            contact_person_name="Someone",
            contact_person_phone="1",
            source_team="bd_team",
            source_person_name="BD",
            is_active=True,
        )
        db.add(client)
        db.flush()
        db.commit()

        assert exclude_hidden_clients(db, select(FinanceClient)).whereclause is None
        codes = [row.client_code for row in db.scalars(select(FinanceClient)).all()]
        assert codes == ["ONLY1"]


def _seed_visible_and_hidden(db: Session) -> tuple[User, FinanceClient, FinanceProject, FinanceProject]:
    actor = User(
        email="vis.p0@nakshatech.com",
        full_name="Visibility P0",
        password_hash="test-only",
        role="admin",
        branch="Head Office",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(actor)
    db.flush()

    visible_client = FinanceClient(
        client_code="VIS001",
        client_name="Visible Client",
        contact_person_name="Someone",
        contact_person_phone="1",
        source_team="bd_team",
        source_person_name="BD",
        is_active=True,
        created_by_id=actor.id,
    )
    hidden_client = FinanceClient(
        client_code="HID001",
        client_name="Hidden UAT Client",
        contact_person_name="Someone",
        contact_person_phone="1",
        source_team="bd_team",
        source_person_name="BD",
        is_active=True,
        created_by_id=actor.id,
    )
    db.add_all([visible_client, hidden_client])
    db.flush()

    visible_project = FinanceProject(
        project_code="VIS-P1",
        project_name="Visible Project",
        client_id=visible_client.id,
        client_name=visible_client.client_name,
        project_source_team="bd_team",
        is_active=True,
        created_by_id=actor.id,
        start_date=date(2026, 1, 1),
    )
    hidden_project = FinanceProject(
        project_code="HID-P1",
        project_name="Hidden UAT Project",
        client_id=hidden_client.id,
        client_name=hidden_client.client_name,
        project_source_team="bd_team",
        is_active=True,
        created_by_id=actor.id,
        start_date=date(2026, 1, 1),
    )
    db.add_all([visible_project, hidden_project])
    db.flush()

    for project in (visible_project, hidden_project):
        db.add(ProjectWorkflow(
            project_id=project.id,
            bd_owner_user_id=actor.id,
            status="draft",
            performing_department_code="ortho",
            created_by_id=actor.id,
            updated_by_id=actor.id,
        ))
    db.flush()

    db.execute(text(
        "INSERT INTO patch_v81_hidden_entities (patch_id, entity_type, entity_id, entity_key, reason) VALUES "
        "(:patch_id, 'finance_client', :client_id, 'HID001', 'cleanup'), "
        "(:patch_id, 'finance_project', :project_id, 'HID-P1', 'cleanup')"
    ), {
        "patch_id": FINANCE_CLEANUP_PATCH_ID,
        "client_id": hidden_client.id,
        "project_id": hidden_project.id,
    })
    db.commit()
    return actor, visible_client, visible_project, hidden_project


def test_p0_sites_exclude_hidden_projects_and_clients():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_hidden_schema(engine)

    with Session(engine) as db:
        actor, _visible_client, visible_project, hidden_project = _seed_visible_and_hidden(db)

        # 1) Finance workflow dashboard (P0 gap fixed)
        payload = finance_dashboard(db)
        codes = [p["project_code"] for p in payload["projects"]]
        assert "VIS-P1" in codes
        assert "HID-P1" not in codes

        # 2) Lifecycle / Billing dashboard (P0 gap fixed)
        life = lifecycle_dashboard(db, actor=actor, role="admin")
        life_codes = [p["project_code"] for p in life["projects"]]
        assert "VIS-P1" in life_codes
        assert "HID-P1" not in life_codes
        assert life["summary"]["total_projects"] == 1
        # department overview client count ignores hidden clients
        assert life["department_overview"]["bd"]["clients"] == 1
        assert life["department_overview"]["finance"]["clients"] == 1

        # 3) Commercial management analytics (P0 gap fixed)
        analytics = management_analytics(db, date_from=None, date_to=None, project_id=None, display_currency="INR")
        analytics_ids = [row["project_id"] for row in analytics["projects"]]
        assert visible_project.id in analytics_ids
        assert hidden_project.id not in analytics_ids

        # 4) Business overview project rows (P0 gap fixed)
        rows = _project_rows(db, month="2026-09")
        row_ids = [row.project_id for row in rows]
        assert visible_project.id in row_ids
        assert hidden_project.id not in row_ids


def test_p1_sites_exclude_hidden_projects():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_hidden_schema(engine)

    with Session(engine) as db:
        actor, _visible_client, visible_project, hidden_project = _seed_visible_and_hidden(db)

        # Seed operational rows on both projects so role-based id collectors see them.
        for project, status in (
            (visible_project, "in_progress"),
            (hidden_project, "in_progress"),
        ):
            # workflow status non-draft so admin ortho list can surface the row after filtering
            workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project.id))
            workflow.status = status
            db.add(OrthoProjectProfile(
                project_id=project.id,
                project_manager_user_id=actor.id,
                created_by_id=actor.id,
            ))
            db.add(ProjectWorkstream(
                project_id=project.id,
                department_code="lidar",
                project_manager_user_id=actor.id,
                created_by_id=actor.id,
                updated_by_id=actor.id,
            ))
            db.add(ExpenseClaim(
                claim_code=f"CLM-{project.project_code}",
                requester_id=actor.id,
                project_id=project.id,
                claim_type="reimbursement",
                purpose_description="P1 visibility",
                total_amount=Decimal("100.00"),
                status="submitted",
                submitted_at=date(2026, 9, 1),
            ))
        db.commit()

        # Helper passes only non-hidden candidates
        visible_ids = filter_visible_project_ids(db, [visible_project.id, hidden_project.id])
        assert visible_project.id in visible_ids
        assert hidden_project.id not in visible_ids

        # Workflow ortho dashboard (admin role)
        ortho = ortho_dashboard(db, actor=actor, role="admin")
        ortho_codes = [p["project_code"] for p in ortho["projects"]]
        assert "VIS-P1" in ortho_codes
        assert "HID-P1" not in ortho_codes

        # Operations ortho profiles (oversight role)
        profiles = visible_ortho_profiles(db, actor=actor, effective_role="admin")
        profile_ids = [p.project_id for p in profiles]
        assert visible_project.id in profile_ids
        assert hidden_project.id not in profile_ids

        # Project workstreams dashboard (admin)
        ws = project_workstreams_dashboard_payload(db, actor=actor, effective_role="admin")
        ws_codes = [p["project_code"] for p in ws["projects"]]
        assert "VIS-P1" in ws_codes
        assert "HID-P1" not in ws_codes

        # Monitoring id collector (admin)
        _mode, mon_ids = monitoring_visible_project_ids(db, actor=actor, effective_role="admin")
        assert visible_project.id in mon_ids
        assert hidden_project.id not in mon_ids

        # Completion id collector (admin)
        _mode, comp_ids = completion_visible_project_ids(db, actor=actor, effective_role="admin")
        assert visible_project.id in comp_ids
        assert hidden_project.id not in comp_ids

        # Handover dashboard (admin)
        hand = handover_dashboard_payload(db, actor=actor, effective_role="admin")
        hand_codes = [p["project_code"] for p in hand["projects"]]
        assert "VIS-P1" in hand_codes
        assert "HID-P1" not in hand_codes

        # Finance report claims + payload exclude hidden project claims
        period = resolve_report_period("all")
        claims = filtered_finance_claims(db, period=period)
        claim_project_ids = {c.project_id for c in claims}
        assert visible_project.id in claim_project_ids
        assert hidden_project.id not in claim_project_ids

        report = finance_report_payload(db, period="all")
        report_codes = {row.get("project_code") for row in report.get("claims", [])}
        assert "VIS-P1" in report_codes
        assert "HID-P1" not in report_codes
        # totals come from the same filtered condition set as the claim rows
        assert int(report.get("total_records") or 0) == len(claims)
        # payments join the same hidden-project conditions
        payments = filtered_finance_payments(db, period=period)
        paid_claim_ids = {p.claim_id for p in payments}
        hidden_claim_id = db.scalar(
            select(ExpenseClaim.id).where(ExpenseClaim.project_id == hidden_project.id)
        )
        assert hidden_claim_id not in paid_claim_ids or hidden_claim_id is None


def _seed_commercial_rows(db: Session, actor: User, visible_project: FinanceProject, hidden_project: FinanceProject) -> None:
    from datetime import datetime

    for project in (visible_project, hidden_project):
        db.add(ProjectCommercialEstimateRevision(
            project_id=project.id,
            revision_no=2,
            status="PENDING_APPROVAL",
            scope_description="P2 visibility",
            billing_type="fixed",
            currency_code="INR",
            estimated_amount=Decimal("1000.00"),
            taxable_base_amount=Decimal("1000.00"),
            expected_gross=Decimal("1000.00"),
            fx_rate_to_inr=Decimal("1"),
            fx_rate_date=date(2026, 9, 1),
            fx_rate_source="manual",
            fx_rate_mode="BASE_CURRENCY",
            estimated_inr=Decimal("1000.00"),
            base_inr=Decimal("1000.00"),
            tax_inr=Decimal("0.00"),
            gross_inr=Decimal("1000.00"),
            estimate_date=date(2026, 9, 1),
            created_by_id=actor.id,
            submitted_at=datetime(2026, 9, 1, 12, 0, 0),
        ))
        db.add(ProjectExpense(
            expense_code=f"PEXP-{project.project_code}",
            project_id=project.id,
            employee_id=actor.id,
            expense_date=date(2026, 9, 1),
            category="travel",
            purpose="P2 visibility",
            amount=Decimal("50.00"),
            status="SUBMITTED",
        ))
        db.add(ProjectVendorInvoice(
            project_id=project.id,
            vendor_name=f"Vendor {project.project_code}",
            invoice_number=f"INV-{project.project_code}",
            invoice_date=date(2026, 9, 1),
            category="services",
            description="P2 visibility",
            taxable_amount=Decimal("100.00"),
            gross_amount=Decimal("100.00"),
            taxable_inr=Decimal("100.00"),
            tax_inr=Decimal("0.00"),
            gross_inr=Decimal("100.00"),
            created_by_id=actor.id,
        ))
        db.add(BDOpportunity(
            opportunity_code=f"OPP-{project.project_code}",
            title=f"Opp {project.project_code}",
            requirement="P2 visibility",
            owner_user_id=actor.id,
            linked_project_id=project.id,
            stage="accepted",
        ))
    db.commit()


def test_p2_commercial_queues_and_bd_summary_exclude_hidden_projects():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    _seed_hidden_schema(engine)

    with Session(engine) as db:
        actor, _visible_client, visible_project, hidden_project = _seed_visible_and_hidden(db)
        _seed_commercial_rows(db, actor, visible_project, hidden_project)

        # 1) Estimate revision queue
        queue = list_estimate_queue(db, statuses=("PENDING_APPROVAL",))
        queue_ids = {row["project_id"] for row in queue}
        assert visible_project.id in queue_ids
        assert hidden_project.id not in queue_ids

        # 2) Project expenses (list-all path)
        expenses = list_project_expenses(db, actor=actor, role="admin")
        expense_ids = {row["project_id"] for row in expenses}
        assert visible_project.id in expense_ids
        assert hidden_project.id not in expense_ids

        # 3) Vendor invoices (list-all path)
        invoices = list_vendor_invoices(db)
        invoice_ids = {row["project_id"] for row in invoices}
        assert visible_project.id in invoice_ids
        assert hidden_project.id not in invoice_ids

        # 4) BD corporate summary: linked_projects must not count hidden projects
        summary = corporate_summary_payload(db)
        assert summary["bd"]["total_opportunities"] == 2  # history preserved
        assert summary["bd"]["linked_projects"] == 1  # only the visible project link
        assert summary["ortho"]["projects"] == 0  # no ortho profiles seeded
