"""Client Advance Request on the BD project creation / commercial form (Finance V8 Phase 3 UI wiring).

Covers the write path added to the commercial layer:
* ``CommercialEstimateInput`` accepts and validates the existing advance columns.
* ``upsert_baseline_estimate`` / ``create_estimate_revision`` persist them (Save Draft AND Submit).
* ``_estimate_payload`` returns them so edit/reopen repopulates the form.
* The no-advance state is persisted cleanly (``advance_required=False``, ``no_advance``).
* Advance terms never change commercial value, tax, FX or the workflow summary.
* The Finance advance read-side (summary) reflects the persisted terms with project value unchanged.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.entities import User
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.commercial.schemas import CommercialEstimateInput, ProjectCommercialInput
from app.modules.commercial.service import (
    _estimate_payload,
    create_estimate_revision,
    freeze_baseline_on_finance_approval,
    prepare_revision1_for_finance_submission,
    upsert_baseline_estimate,
)
from app.modules.finance.advance_service import advance_projects
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.operations.models import ProjectWorkflow
from app.modules.operations.schemas import WorkflowProjectCreate
from app.modules.operations.workflow_service import create_bd_project, submit_project_to_finance
from app.core.database import SessionLocal


# -------------------------------------------------------------------------------------------- helpers
def make_user(db, email: str, role: str, name: str | None = None) -> User:
    row = User(
        email=email, full_name=name or email.split("@", 1)[0], password_hash="test-only", role=role,
        branch="Head Office", email_verified=True, account_status="active", is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def make_client(db, owner: User, code: str) -> FinanceClient:
    client = FinanceClient(
        client_code=f"C-{code}", client_name="Advance Form Client", contact_person_name="Contact",
        contact_person_phone="9999999999", source_team="bd_team", source_person_name=owner.full_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def commercial(**overrides) -> ProjectCommercialInput:
    values = dict(
        scope_description="Aerial survey, processing and delivery",
        billing_type="fixed_price",
        payment_terms="25% advance, 75% after delivery",
        currency_code="INR",
        estimated_amount=Decimal("2000000"),
        taxable_base_amount=Decimal("2000000"),
        tax_percent=Decimal("18"),
        # The user's test scenario: Contract 20,00,000 / Yes / Percentage Advance / 25% / 5,00,000 / INR.
        advance_required=True,
        advance_payment_type="percentage_advance",
        advance_percent=Decimal("25"),
        advance_amount=Decimal("500000"),
        expected_advance_date=date(2026, 11, 15),
        final_advance_date=date(2026, 12, 15),
    )
    values.update(overrides)
    return ProjectCommercialInput(**values)


def project_payload(client: FinanceClient, code: str, **overrides) -> WorkflowProjectCreate:
    values = dict(
        client_id=client.id, project_code=code, project_name="Advance Request Project",
        start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
    )
    values.update(overrides)
    return WorkflowProjectCreate(**values)


def rev1(db, project_id: int) -> ProjectCommercialEstimateRevision:
    return db.scalar(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id,
        ProjectCommercialEstimateRevision.revision_no == 1,
    ))


# ----------------------------------------------------------------- 1: schema accepts + validates
def test_schema_accepts_advance_request_fields():
    payload = commercial()
    assert payload.advance_required is True
    assert payload.advance_payment_type == "percentage_advance"
    assert payload.advance_percent == Decimal("25")
    assert payload.advance_amount == Decimal("500000")
    # currency defaults to the commercial currency when omitted
    assert payload.advance_currency_code == "INR"
    # percentage request anchors the % to the taxable base
    assert payload.advance_base_amount == Decimal("2000000")


def test_schema_no_advance_state_is_clean():
    payload = commercial(advance_required=False, advance_payment_type=None, advance_percent=None,
                         advance_amount=None, expected_advance_date=None, final_advance_date=None)
    assert payload.advance_required is False
    assert payload.advance_payment_type == "no_advance"
    assert payload.advance_percent is None and payload.advance_amount is None
    assert payload.advance_base_amount is None
    assert payload.expected_advance_date is None and payload.final_advance_date is None


def test_schema_rejects_unsupported_advance_type():
    with pytest.raises(ValueError, match="Advance Payment Type"):
        commercial(advance_payment_type="credit_payment")


def test_schema_rejects_percent_above_100():
    with pytest.raises(ValueError):
        commercial(advance_percent=Decimal("120"))


def test_schema_rejects_final_date_before_expected_date():
    with pytest.raises(ValueError, match="Final Advance Date"):
        commercial(expected_advance_date=date(2026, 12, 15), final_advance_date=date(2026, 11, 15))


def test_schema_requires_percent_or_amount_when_yes():
    with pytest.raises(ValueError, match="percentage or the advance amount"):
        commercial(advance_percent=None, advance_amount=None)


def test_schema_requires_payment_type_when_yes():
    with pytest.raises(ValueError, match="Advance Payment Type"):
        commercial(advance_payment_type=None, advance_amount=Decimal("500000"))


def test_schema_legacy_payload_without_advance_stays_null():
    payload = commercial(advance_required=None, advance_payment_type=None, advance_percent=None,
                         advance_amount=None, expected_advance_date=None, final_advance_date=None)
    assert payload.advance_required is None
    assert payload.advance_payment_type is None


# ------------------------------------------------------- 2: persistence on create (Save Draft path)
def test_create_project_persists_advance_request_on_revision1():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform1@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-A")
        project, workflow = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-01", commercial=commercial()),
        )
        db.flush()

        row = rev1(db, project.id)
        assert row is not None
        assert row.advance_required is True
        assert row.advance_payment_type == "percentage_advance"
        assert Decimal(row.advance_percent) == Decimal("25.00")
        assert Decimal(row.advance_amount) == Decimal("500000.00")
        assert Decimal(row.advance_base_amount) == Decimal("2000000.00")
        assert row.advance_currency_code == "INR"
        assert row.expected_advance_date == date(2026, 11, 15)
        assert row.final_advance_date == date(2026, 12, 15)
        # commercial value untouched by the advance request
        assert Decimal(row.estimated_amount) == Decimal("2000000.00")
        assert Decimal(row.expected_tax) == Decimal("360000.00")
        assert Decimal(workflow.commercial_value) == Decimal("2000000.00")


def test_create_project_persists_no_advance_state():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform2@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-B")
        project, workflow = create_bd_project(
            db, actor=bd,
            payload=project_payload(client, "P-ADV-02", commercial=commercial(
                advance_required=False, advance_payment_type=None, advance_percent=None,
                advance_amount=None, expected_advance_date=None, final_advance_date=None,
            )),
        )
        db.flush()

        row = rev1(db, project.id)
        assert row.advance_required is False
        assert row.advance_payment_type == "no_advance"
        assert row.advance_percent is None and row.advance_amount is None
        assert row.advance_base_amount is None
        assert row.expected_advance_date is None and row.final_advance_date is None
        assert Decimal(workflow.commercial_value) == Decimal("2000000.00")


def test_fixed_advance_amount_without_percent_persists():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform3@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-C")
        project, _ = create_bd_project(
            db, actor=bd,
            payload=project_payload(client, "P-ADV-03", commercial=commercial(
                advance_payment_type="fixed_advance", advance_percent=None, advance_amount=Decimal("300000"),
            )),
        )
        db.flush()

        row = rev1(db, project.id)
        assert row.advance_payment_type == "fixed_advance"
        assert row.advance_percent is None
        assert Decimal(row.advance_amount) == Decimal("300000.00")
        assert row.advance_base_amount is None


# ------------------------------------------------- 3: persistence on update (edit / Save Corrections)
def test_upsert_update_path_persists_advance_fields_and_repopulates():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform4@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-D")
        project, _ = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-04", commercial=commercial()),
        )
        db.flush()

        # edit: change to a fixed advance of 6,00,000 and later dates
        upsert_baseline_estimate(
            db, actor=bd, project_id=project.id,
            payload=commercial(advance_payment_type="fixed_advance", advance_percent=None,
                               advance_amount=Decimal("600000"), expected_advance_date=date(2026, 11, 20),
                               final_advance_date=date(2026, 12, 20)),
        )
        db.flush()
        row = rev1(db, project.id)
        assert row.advance_payment_type == "fixed_advance"
        assert Decimal(row.advance_amount) == Decimal("600000.00")
        assert row.expected_advance_date == date(2026, 11, 20)

        # edit: switch to No advance — the no-advance state must persist cleanly
        upsert_baseline_estimate(
            db, actor=bd, project_id=project.id,
            payload=commercial(advance_required=False, advance_payment_type=None, advance_percent=None,
                               advance_amount=None, expected_advance_date=None, final_advance_date=None),
        )
        db.flush()
        row = rev1(db, project.id)
        assert row.advance_required is False
        assert row.advance_payment_type == "no_advance"
        assert row.advance_amount is None

        # _estimate_payload returns the saved values so the form repopulates on reopen
        payload = _estimate_payload(row)
        assert payload["advance_required"] is False
        assert payload["advance_payment_type"] == "no_advance"
        assert payload["advance_amount"] is None
        assert payload["expected_advance_date"] is None


def test_estimate_payload_returns_advance_fields_for_repopulation():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform5@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-E")
        project, _ = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-05", commercial=commercial()),
        )
        db.flush()
        payload = _estimate_payload(rev1(db, project.id))
        assert payload["advance_required"] is True
        assert payload["advance_payment_type"] == "percentage_advance"
        assert payload["advance_percent"] == 25.0
        assert payload["advance_amount"] == 500000.0
        assert payload["advance_base_amount"] == 2000000.0
        assert payload["advance_currency_code"] == "INR"
        assert payload["expected_advance_date"] == "2026-11-15"
        assert payload["final_advance_date"] == "2026-12-15"


# --------------------------------------------- 4: Submit to Finance preserves the advance fields
def test_submit_to_finance_preserves_advance_fields_and_does_not_block():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform6@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-F")
        project, workflow = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-06", commercial=commercial()),
        )
        db.flush()
        db.commit()
        project_id, bd_id = project.id, bd.id

    with SessionLocal() as db:
        bd = db.get(User, bd_id)
        submit_project_to_finance(db, actor=bd, project_id=project_id)
        db.flush()
        db.commit()

    with SessionLocal() as db:
        workflow = db.scalar(select(ProjectWorkflow).where(ProjectWorkflow.project_id == project_id))
        assert workflow.status == "pending_finance_approval"
        row = rev1(db, project_id)
        assert row.status == "PENDING_APPROVAL"
        # advance fields survive the submission untouched
        assert row.advance_required is True
        assert row.advance_payment_type == "percentage_advance"
        assert Decimal(row.advance_amount) == Decimal("500000.00")
        assert Decimal(row.estimated_amount) == Decimal("2000000.00")


def test_finance_approval_locks_baseline_and_keeps_advance_terms():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform7@nakshatech.com", "bd")
        finance = make_user(db, "finance.advform7@nakshatech.com", "finance")
        client = make_client(db, bd, "ADVFORM-G")
        project, _ = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-07", commercial=commercial()),
        )
        db.flush()
        prepare_revision1_for_finance_submission(db, actor=bd, project_id=project.id)
        freeze_baseline_on_finance_approval(db, actor=finance, project_id=project.id)
        db.flush()

        row = rev1(db, project.id)
        assert row.status == "APPROVED" and row.is_locked is True
        assert row.advance_required is True
        assert Decimal(row.advance_amount) == Decimal("500000.00")
        assert Decimal(row.estimated_amount) == Decimal("2000000.00")


# ------------------------------------- 5: later revisions carry the advance request too
def test_create_estimate_revision_persists_advance_fields():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform8@nakshatech.com", "bd")
        finance = make_user(db, "finance.advform8@nakshatech.com", "finance")
        client = make_client(db, bd, "ADVFORM-H")
        project, _ = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-08", commercial=commercial()),
        )
        db.flush()
        prepare_revision1_for_finance_submission(db, actor=bd, project_id=project.id)
        freeze_baseline_on_finance_approval(db, actor=finance, project_id=project.id)
        db.flush()

        revision = create_estimate_revision(
            db, actor=bd, project_id=project.id,
            payload=CommercialEstimateInput(
                scope_description="Added deliverables", billing_type="fixed_price", payment_terms="30 days",
                currency_code="INR", estimated_amount=Decimal("2400000"), taxable_base_amount=Decimal("2400000"),
                tax_percent=Decimal("18"), estimate_date=date(2026, 10, 5), reason="Client added scope",
                advance_required=True, advance_payment_type="percentage_advance",
                advance_percent=Decimal("25"), expected_advance_date=date(2026, 11, 25),
                final_advance_date=date(2026, 12, 25),
            ),
        )
        db.flush()
        assert revision.revision_no == 2
        assert revision.advance_required is True
        assert revision.advance_payment_type == "percentage_advance"
        assert Decimal(revision.advance_percent) == Decimal("25.00")
        assert Decimal(revision.advance_base_amount) == Decimal("2400000.00")
        assert revision.expected_advance_date == date(2026, 11, 25)


# ------------------------------- 6: Finance advance read-side sees the persisted terms, value unchanged
def test_advance_summary_reflects_saved_request_with_project_value_unchanged():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform9@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-I")
        project, workflow = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-09", commercial=commercial()),
        )
        db.flush()
        db.commit()
        project_id = project.id

    with SessionLocal() as db:
        # The Finance read-side accessor follows the frozen Client Advance contract
        # (db, *, user, effective_role); advance_projects returns one snapshot row per
        # project (advance_summary is the totals-only roll-up).
        rows = advance_projects(db, user=db.get(User, bd.id), effective_role="bd")
        projects = [row for row in rows if row["project_id"] == project_id]
        assert projects, "advance read-side must include the project with advance terms"
        row = projects[0]
        # Contract 20,00,000 with a 25% advance: expected 5,00,000, nothing received yet.
        assert Decimal(str(row["advance_amount"])) == Decimal("500000.00")
        assert Decimal(str(row["received_amount"])) == Decimal("0")
        assert Decimal(str(row["pending_amount"])) == Decimal("500000.00")
        assert row["advance_required"] is True
        # expected_advance_date is still in the future, so the ledger reports "requested"
        # (it becomes "pending" from the expected date, then overdue after the final date).
        assert row["status"] == "requested"
        assert row["expected_date"] == "2026-11-15"
        assert row["final_date"] == "2026-12-15"
        # project value stays the full contract value (gross incl. 18% tax)
        assert Decimal(str(row["project_value"])) == Decimal("2360000.00")


# ------------------------------------------------- 7: advance never mutates commercial calculations
def test_advance_request_does_not_change_tax_or_workflow_value():
    with SessionLocal() as db:
        bd = make_user(db, "bd.advform10@nakshatech.com", "bd")
        client = make_client(db, bd, "ADVFORM-J")
        with_advance, workflow_a = create_bd_project(
            db, actor=bd, payload=project_payload(client, "P-ADV-10", commercial=commercial()),
        )
        without_advance, workflow_b = create_bd_project(
            db, actor=bd,
            payload=project_payload(client, "P-ADV-11", commercial=commercial(
                advance_required=False, advance_payment_type=None, advance_percent=None,
                advance_amount=None, expected_advance_date=None, final_advance_date=None,
            )),
        )
        db.flush()
        a, b = rev1(db, with_advance.id), rev1(db, without_advance.id)
        # identical commercial math with and without an advance request
        assert Decimal(a.estimated_amount) == Decimal(b.estimated_amount)
        assert Decimal(a.expected_tax) == Decimal(b.expected_tax)
        assert Decimal(a.expected_gross) == Decimal(b.expected_gross)
        assert Decimal(a.estimated_inr) == Decimal(b.estimated_inr)
        assert Decimal(workflow_a.commercial_value) == Decimal(workflow_b.commercial_value)
