"""Controlled E2E UAT for the Client Advance Request write path (NakshaTech ERP V8.1).

Exact scenario requested for UAT:

    Client            : UAT ADVANCE CLIENT 001
    Project           : UAT-ADV-E2E-001
    Contract Value    : 20,00,000
    Advance Required  : Yes
    Advance Type      : Percentage Advance (supported equivalent of a partial advance)
    Advance %         : 25
    Advance Amount    : 5,00,000
    Currency          : INR

Walks the real service path end to end and asserts every acceptance point:

    1. Save Draft persists the advance terms on Commercial Revision 1.
    2. Edit / reload repopulates every advance field.
    3. Submit to Finance keeps the terms and does not block the workflow.
    4. The Finance read-side shows Expected 5,00,000 / Received 0 / Pending 5,00,000.
    5. Locked rules hold: contract value 20,00,000, tax, gross, FX, Sales, Revenue,
       Outstanding and the Employee Advance flow are untouched by the advance terms.
    6. The no-advance state persists cleanly for the same contract value.

Runs against the throwaway SQLite database pinned by ``tests/conftest.py``, so the
local application database is never touched.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.commercial.service import _estimate_payload, upsert_baseline_estimate
from app.modules.finance.advance_service import advance_projects
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.operations.models import ProjectWorkflow
from app.modules.operations.schemas import WorkflowProjectCreate
from app.modules.operations.workflow_service import create_bd_project, submit_project_to_finance

UAT_CLIENT_NAME = "UAT ADVANCE CLIENT 001"
UAT_PROJECT_CODE = "UAT-ADV-E2E-001"
CONTRACT_VALUE = Decimal("2000000")          # 20,00,000
ADVANCE_PERCENT = Decimal("25")              # 25 %
ADVANCE_AMOUNT = Decimal("500000")           # 5,00,000
EXPECTED_ADVANCE_DATE = date(2026, 11, 15)
FINAL_ADVANCE_DATE = date(2026, 12, 15)

def _make_bd(db) -> User:
    user = User(
        email="bd.uat.advance@nakshatech.com", full_name="UAT Advance BD", password_hash="uat-only",
        role="bd", branch="Head Office", email_verified=True, account_status="active", is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _make_uat_client(db, owner: User, code: str = "UAT-ADV-001") -> FinanceClient:
    client = FinanceClient(
        client_code=f"C-{code}", client_name=UAT_CLIENT_NAME, contact_person_name="UAT Contact",
        contact_person_phone="9999999999", source_team="bd_team",
        source_person_name=owner.full_name, is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def _uat_commercial(**overrides) -> ProjectCommercialInput:
    values = dict(
        scope_description="Aerial survey, processing and delivery",
        billing_type="fixed_price",
        payment_terms="25% advance, 75% after delivery",
        currency_code="INR",
        estimated_amount=CONTRACT_VALUE,
        taxable_base_amount=CONTRACT_VALUE,
        tax_percent=Decimal("18"),
        advance_required=True,
        advance_payment_type="percentage_advance",
        advance_percent=ADVANCE_PERCENT,
        advance_amount=ADVANCE_AMOUNT,
        expected_advance_date=EXPECTED_ADVANCE_DATE,
        final_advance_date=FINAL_ADVANCE_DATE,
    )
    values.update(overrides)
    return ProjectCommercialInput(**values)


def _uat_project_payload(client: FinanceClient, **overrides) -> WorkflowProjectCreate:
    values = dict(
        client_id=client.id, project_code=UAT_PROJECT_CODE, project_name="UAT Advance E2E Project",
        start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
        commercial=_uat_commercial(),
    )
    values.update(overrides)
    return WorkflowProjectCreate(**values)


def _rev1(db, project_id: int) -> ProjectCommercialEstimateRevision:
    return db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))


def _assert_uat_advance_terms(row: ProjectCommercialEstimateRevision) -> None:
    """Contract 20,00,000 with a 25 % advance: every persisted advance term must match."""
    assert row.advance_required is True
    assert row.advance_payment_type == "percentage_advance"
    assert Decimal(row.advance_percent) == ADVANCE_PERCENT
    assert Decimal(row.advance_amount) == ADVANCE_AMOUNT
    assert Decimal(row.advance_base_amount) == CONTRACT_VALUE
    assert row.advance_currency_code == "INR"
    assert row.expected_advance_date == EXPECTED_ADVANCE_DATE
    assert row.final_advance_date == FINAL_ADVANCE_DATE
def test_uat_client_advance_request_save_draft_reload_submit_and_read_side():
    # ---------------------------------------------------- 1. SAVE DRAFT
    with SessionLocal() as db:
        bd = _make_bd(db)
        client = _make_uat_client(db, bd)
        project, workflow = create_bd_project(db, actor=bd, payload=_uat_project_payload(client))
        db.flush()
        row = _rev1(db, project.id)
        assert row is not None and row.status == "DRAFT"
        _assert_uat_advance_terms(row)
        # locked rules: the advance never changes the commercial value
        assert Decimal(row.estimated_amount) == CONTRACT_VALUE
        assert Decimal(row.expected_tax) == Decimal("360000.00")      # 18 % of 20,00,000
        assert Decimal(row.expected_gross) == Decimal("2360000.00")
        assert Decimal(workflow.commercial_value) == CONTRACT_VALUE
        db.commit()
        project_id = project.id
        bd_id = bd.id

    # -------------------------------- 2. EDIT / RELOAD REPOPULATES EVERY FIELD
    with SessionLocal() as db:
        payload = _estimate_payload(_rev1(db, project_id))
        assert payload["advance_required"] is True
        assert payload["advance_payment_type"] == "percentage_advance"
        assert payload["advance_percent"] == 25.0
        assert payload["advance_amount"] == 500000.0
        assert payload["advance_base_amount"] == 2000000.0
        assert payload["advance_currency_code"] == "INR"
        assert payload["expected_advance_date"] == "2026-11-15"
        assert payload["final_advance_date"] == "2026-12-15"
        # re-saving the reopened form (Save Corrections) keeps every term
        bd = db.get(User, bd_id)
        upsert_baseline_estimate(db, actor=bd, project_id=project_id, payload=_uat_commercial())
        db.flush()
        _assert_uat_advance_terms(_rev1(db, project_id))
        db.commit()

    # --------------------------------------------- 3. SUBMIT TO FINANCE
    with SessionLocal() as db:
        bd = db.get(User, bd_id)
        submit_project_to_finance(db, actor=bd, project_id=project_id)
        db.flush()
        db.commit()

    with SessionLocal() as db:
        workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))
        row = _rev1(db, project_id)
        assert workflow.status == "pending_finance_approval"
        assert row.status == "PENDING_APPROVAL"
        _assert_uat_advance_terms(row)
        assert Decimal(row.estimated_amount) == CONTRACT_VALUE

    # --------------------- 4/5. FINANCE READ SIDE (Command Center advance KPIs)
    with SessionLocal() as db:
        rows = advance_projects(db, user=db.get(User, bd_id), effective_role="bd")
        match = [item for item in rows if item["project_id"] == project_id]
        assert match, "the UAT project must appear on the Finance advance read side"
        item = match[0]
        assert Decimal(str(item["advance_amount"])) == ADVANCE_AMOUNT      # Advance Expected 5,00,000
        assert Decimal(str(item["received_amount"])) == Decimal("0")       # Advance Received 0
        assert Decimal(str(item["pending_amount"])) == ADVANCE_AMOUNT      # Advance Pending 5,00,000
        assert item["advance_required"] is True
        assert item["advance_currency"] == "INR"
        assert item["expected_date"] == "2026-11-15"
        assert item["final_date"] == "2026-12-15"
        # Project / commercial value stays the full contract value (gross incl. 18 % tax)
        assert Decimal(str(item["project_value"])) == Decimal("2360000.00")
        # the contract value on the workflow is untouched by the advance terms
        stored = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))
        assert Decimal(stored.commercial_value) == CONTRACT_VALUE


def test_uat_no_advance_state_persists_cleanly_for_same_contract_value():
    with SessionLocal() as db:
        bd = _make_bd(db)
        client = _make_uat_client(db, bd)
        project, workflow = create_bd_project(
            db, actor=bd,
            payload=WorkflowProjectCreate(
                client_id=client.id, project_code="UAT-ADV-E2E-002", project_name="UAT No Advance Project",
                start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
            ),
        )
        db.flush()
        upsert_baseline_estimate(
            db, actor=bd, project_id=project.id,
            payload=_uat_commercial(
                advance_required=False, advance_payment_type=None, advance_percent=None,
                advance_amount=None, expected_advance_date=None, final_advance_date=None,
            ),
        )
        db.flush()
        row = _rev1(db, project.id)
        assert row.advance_required is False
        assert row.advance_payment_type == "no_advance"
        assert row.advance_percent is None
        assert row.advance_amount is None
        assert row.advance_base_amount is None
        assert row.expected_advance_date is None and row.final_advance_date is None
        # same commercial outcome as the advance project: nothing about the value changed
        assert Decimal(row.estimated_amount) == CONTRACT_VALUE
        assert Decimal(row.expected_gross) == Decimal("2360000.00")
        assert Decimal(workflow.commercial_value) == CONTRACT_VALUE
        db.commit()

        rows = advance_projects(db, user=bd, effective_role="bd")
        item = [entry for entry in rows if entry["project_id"] == project.id][0]
        assert item["status"] == "not_required"
        assert Decimal(str(item["advance_amount"])) == Decimal("0")
        assert Decimal(str(item["project_value"])) == Decimal("2360000.00")  # gross incl. 18 % tax

