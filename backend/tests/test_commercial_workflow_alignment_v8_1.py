"""Commercial workflow alignment (V8.1): Revision 1 travels with the project, Finance approves both,
the PM confirms operational billing facts, and Finance bills from approved basis + PM basis.

Service-level tests run inside one SQLAlchemy session; permission tests call the real HTTP routes with the
authentication dependency overridden to a chosen role (no password / token involved).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.models.entities import User
from app.modules.commercial.fx_service import (
    FxQuote,
    FxRateService,
    ProviderTransientError,
    ProviderUnsupported,
    set_fx_service,
)
from app.modules.commercial.models import (
    ProjectBillingBasis,
    ProjectCommercialEstimateRevision,
    ProjectCommercialMilestone,
    ProjectExpense,
    ProjectFxSnapshot,
)
from app.modules.commercial.schemas import (
    BillingBasisInput,
    CommercialEstimateDecision,
    CommercialEstimateInput,
    ProjectCommercialInput,
    ProjectExpenseInput,
)
from app.modules.commercial.service import (
    billing_recommendation,
    commercial_and_fx_variance,
    create_estimate_revision,
    decide_estimate_revision,
    freeze_baseline_on_finance_approval,
    list_estimate_queue,
    pm_billing_basis_view,
    prepare_revision1_for_finance_submission,
    record_billing_basis,
    upsert_baseline_estimate,
)
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.lifecycle_models import ProjectInvoice
from app.modules.operations.lifecycle_schemas import InvoiceDraftCreate, InvoiceRaise
from app.modules.operations.lifecycle_service import READY_FOR_BILLING, create_invoice_draft, raise_invoice
from app.modules.operations.models import ProjectWorkflow, ProjectWorkflowEvent
from app.modules.operations.schemas import WorkflowFinanceReview, WorkflowProjectCreate
from app.modules.operations.workflow_service import (
    create_bd_project,
    finance_review_project,
    submit_project_to_finance,
    update_bd_project,
)


# --------------------------------------------------------------------------------------------- fixtures
class FakeProvider:
    name = "fake"
    supports_historical = True

    def __init__(self, rates: dict[str, str]) -> None:
        self.rates = rates

    def get_rate(self, from_currency, to_currency, on_date, client):
        if from_currency not in self.rates:
            raise ProviderUnsupported("fake: no rate")
        return FxQuote(from_currency, to_currency, Decimal(self.rates[from_currency]), on_date or date.today(), None, "FAKE (test)", "AUTO")


class DownProvider:
    name = "down"
    supports_historical = True

    def get_rate(self, from_currency, to_currency, on_date, client):
        raise ProviderTransientError("down: timeout")


@pytest.fixture(autouse=True)
def deterministic_fx():
    set_fx_service(FxRateService(providers=[FakeProvider({"USD": "84.5", "EUR": "90.0"})], max_retries=0, sleep=lambda _s: None))
    yield
    set_fx_service(None)


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
        client_code=f"C-{code}", client_name="Alignment Test Client", contact_person_name="Contact",
        contact_person_phone="9999999999", source_team="bd_team", source_person_name=owner.full_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(client)
    db.flush()
    return client


def make_project(db, *, owner: User, code: str, status: str = "in_progress", pm: User | None = None) -> tuple[FinanceProject, ProjectWorkflow]:
    client = make_client(db, owner, code)
    project = FinanceProject(
        project_code=code, project_name="Alignment Project", client_id=client.id, client_name=client.client_name,
        is_active=True, created_by_id=owner.id,
    )
    db.add(project)
    db.flush()
    workflow = ProjectWorkflow(
        project_id=project.id, bd_owner_user_id=owner.id, status=status, scope_text="Survey", priority="medium",
        currency="INR", created_by_id=owner.id, updated_by_id=owner.id,
    )
    db.add(workflow)
    if pm is not None:
        db.add(FinanceProjectMasterProfile(project_id=project.id, project_status="active", project_manager_id=pm.id))
    db.flush()
    return project, workflow


def commercial(**overrides) -> ProjectCommercialInput:
    values = dict(
        scope_description="Aerial survey, processing and delivery",
        billing_type="fixed_price",
        payment_terms="30% advance, 40% after survey, 30% after delivery",
        po_wo_reference="PO-ALIGN-01",
        quotation_reference="QT-ALIGN-01",
        currency_code="INR",
        estimated_amount=Decimal("2000000"),
        taxable_base_amount=Decimal("2000000"),
        tax_percent=Decimal("18"),
        expected_billing_milestone="On final delivery",
    )
    if "estimated_amount" in overrides and "taxable_base_amount" not in overrides:
        overrides = {**overrides, "taxable_base_amount": overrides["estimated_amount"]}
    values.update(overrides)
    return ProjectCommercialInput(**values)


def revision_input(**overrides) -> CommercialEstimateInput:
    values = dict(
        scope_description="Additional scope", billing_type="fixed_price", payment_terms="30 days", currency_code="INR",
        estimated_amount=Decimal("2400000"), taxable_base_amount=Decimal("2400000"), tax_percent=Decimal("18"),
        estimate_date=date(2026, 9, 21), reason="Client added scope",
    )
    values.update(overrides)
    return CommercialEstimateInput(**values)


def project_payload(client: FinanceClient, code: str, **overrides) -> WorkflowProjectCreate:
    values = dict(
        client_id=client.id, project_code=code, project_name="Created With Revision 1",
        start_date=date(2026, 10, 1), end_date=date(2026, 12, 31), scope_text="Survey and deliver",
    )
    values.update(overrides)
    return WorkflowProjectCreate(**values)


def rev1_rows(db, project_id: int) -> list[ProjectCommercialEstimateRevision]:
    return list(db.scalars(select(ProjectCommercialEstimateRevision).where(
        ProjectCommercialEstimateRevision.project_id == project_id
    ).order_by(ProjectCommercialEstimateRevision.revision_no)).all())


# ------------------------------------------------------------- 1-3: create project + Revision 1, atomically
def test_bd_creates_project_with_commercial_revision1_linked_to_same_project_id():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align1@nakshatech.com", "bd")
        client = make_client(db, bd, "ALIGN-A")
        project, workflow = create_bd_project(
            db, actor=bd,
            payload=project_payload(client, "P-1001", commercial=commercial(
                currency_code="USD", estimated_amount=Decimal("10000"), taxable_base_amount=Decimal("10000"), tax_percent=Decimal("0"),
            )),
        )
        db.flush()

        assert db.scalar(select(func.count(FinanceProject.id)).where(FinanceProject.project_code == "P-1001")) == 1
        rows = rev1_rows(db, project.id)
        assert len(rows) == 1
        rev = rows[0]
        assert rev.project_id == project.id and rev.revision_no == 1 and rev.is_baseline is True
        assert rev.status == "DRAFT" and rev.is_locked is False
        assert rev.payment_terms.startswith("30% advance")
        assert rev.po_wo_reference == "PO-ALIGN-01" and rev.quotation_reference == "QT-ALIGN-01"
        # foreign currency: full FX snapshot stored on the revision and mirrored on the workflow summary
        assert rev.currency_code == "USD" and Decimal(rev.estimated_amount) == Decimal("10000.00")
        assert Decimal(rev.fx_rate_to_inr) == Decimal("84.50000000") and rev.fx_rate_source == "FAKE (test)" and rev.fx_rate_mode == "AUTO"
        assert rev.fx_rate_date == date.today()
        assert Decimal(rev.estimated_inr) == Decimal("845000.00")
        snapshot = db.get(ProjectFxSnapshot, rev.fx_snapshot_id)
        assert snapshot.project_id == project.id and Decimal(snapshot.inr_equivalent) == Decimal("845000.00")
        assert workflow.currency == "USD" and Decimal(workflow.commercial_value) == Decimal("10000.00")


def test_retrying_create_or_save_never_creates_a_second_revision1():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align2@nakshatech.com", "bd")
        client = make_client(db, bd, "ALIGN-B")
        project, _ = create_bd_project(db, actor=bd, payload=project_payload(client, "P-1002", commercial=commercial()))
        db.flush()
        # a retried create with the same Project ID is refused before any commercial row is written
        with pytest.raises(ValueError, match="already"):
            create_bd_project(db, actor=bd, payload=project_payload(client, "P-1002", commercial=commercial()))
        # re-saving the same commercial block (retry / double click) updates the SAME row
        upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(estimated_amount=Decimal("2100000"), taxable_base_amount=Decimal("2100000")))
        upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(estimated_amount=Decimal("2100000"), taxable_base_amount=Decimal("2100000")))
        db.flush()
        rows = rev1_rows(db, project.id)
        assert len(rows) == 1 and rows[0].revision_no == 1
        assert Decimal(rows[0].estimated_amount) == Decimal("2100000.00")


def test_fx_outage_on_create_rolls_the_whole_project_back():
    set_fx_service(FxRateService(providers=[DownProvider()], max_retries=0, sleep=lambda _s: None))
    with SessionLocal() as db:
        bd = make_user(db, "bd.align3@nakshatech.com", "bd")
        client = make_client(db, bd, "ALIGN-C")
        db.commit()
        client_id = client.id
        bd_id = bd.id
    with SessionLocal() as db:
        bd = db.get(User, bd_id)
        from app.modules.commercial.fx_service import FxUnavailableError

        with pytest.raises(FxUnavailableError):
            create_bd_project(db, actor=bd, payload=WorkflowProjectCreate(
                client_id=client_id, project_code="P-1003", project_name="No FX", start_date=date(2026, 10, 1),
                end_date=date(2026, 12, 31), scope_text="Survey scope",
                commercial=commercial(currency_code="USD", estimated_amount=Decimal("100"), taxable_base_amount=Decimal("100")),
            ))
        db.rollback()   # exactly what the router does on any error
    with SessionLocal() as db:
        assert db.scalar(select(func.count(FinanceProject.id)).where(FinanceProject.project_code == "P-1003")) == 0
        assert db.scalar(select(func.count(ProjectCommercialEstimateRevision.id))) == 0


# ---------------------------------------- 4-7: submit with project, Finance approval lock, return/resubmit, revisions
def test_submission_sends_revision1_with_project_and_finance_approval_locks_it():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align4@nakshatech.com", "bd")
        finance = make_user(db, "fin.align4@nakshatech.com", "finance")
        client = make_client(db, bd, "ALIGN-D")
        project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, "P-1004", commercial=commercial(currency_code="EUR", estimated_amount=Decimal("5000"), taxable_base_amount=Decimal("5000"))))
        submit_project_to_finance(db, actor=bd, project_id=project.id)
        db.flush()
        rev = rev1_rows(db, project.id)[0]
        assert workflow.status == "pending_finance_approval" and rev.status == "PENDING_APPROVAL" and rev.submitted_at is not None
        # Finance cannot approve Revision 1 separately from the project
        with pytest.raises(ValueError, match="approved together with the project"):
            decide_estimate_revision(db, actor=finance, revision_id=rev.id, payload=CommercialEstimateDecision(decision="approve", comments="ok"))
        assert list_estimate_queue(db) == []           # Revision 1 is not an independent queue item

        finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", feedback="Commercials verified"))
        db.flush()
        assert rev.status == "APPROVED" and rev.is_locked is True and rev.approved_by_id == finance.id and rev.approved_at is not None
        snapshot = db.get(ProjectFxSnapshot, rev.fx_snapshot_id)
        assert snapshot.fx_locked is True and snapshot.verified_by_id == finance.id
        events = [e.event_type for e in db.scalars(select(ProjectWorkflowEvent).where(ProjectWorkflowEvent.project_id == project.id)).all()]
        assert "commercial_revision1_submitted" in events and "commercial_revision1_approved_baseline" in events
        with pytest.raises(ValueError, match="baseline is locked"):
            upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(estimated_amount=Decimal("9999")))


def test_finance_return_keeps_ids_and_history_and_bd_can_correct_and_resubmit():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align5@nakshatech.com", "bd")
        finance = make_user(db, "fin.align5@nakshatech.com", "finance")
        client = make_client(db, bd, "ALIGN-E")
        project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, "P-1005", commercial=commercial()))
        submit_project_to_finance(db, actor=bd, project_id=project.id)
        rev = rev1_rows(db, project.id)[0]
        original_rev_id, original_project_id, original_client_id = rev.id, project.id, project.client_id

        # while under review BD cannot silently change the commercial terms
        with pytest.raises(ValueError, match="under Finance review"):
            upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(estimated_amount=Decimal("1")))

        finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="return", feedback="Payment terms unclear"))
        db.flush()
        assert workflow.status == "finance_returned"
        assert rev.status == "RETURNED" and rev.decision_comments == "Payment terms unclear"
        assert db.scalar(select(func.count(FinanceProject.id))) == 1 and rev.id == original_rev_id

        # BD corrects BOTH project data and commercial terms on the same record and resubmits
        update_bd_project(
            db, actor=bd, project_id=project.id,
            payload=project_payload(client, "P-1005", project_name="Corrected name", commercial=commercial(
                estimated_amount=Decimal("2200000"), taxable_base_amount=Decimal("2200000"), payment_terms="50% advance, 50% on delivery")),
        )
        db.flush()
        assert project.id == original_project_id and project.client_id == original_client_id and project.project_name == "Corrected name"
        rows = rev1_rows(db, project.id)
        assert len(rows) == 1 and rows[0].id == original_rev_id
        assert rows[0].status == "DRAFT" and Decimal(rows[0].estimated_amount) == Decimal("2200000.00")
        assert Decimal(rows[0].previous_amount) == Decimal("2000000.00")          # earlier value preserved as history

        submit_project_to_finance(db, actor=bd, project_id=project.id)
        finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", feedback=None))
        db.flush()
        assert rows[0].status == "APPROVED" and rows[0].is_locked
        events = [e.event_type for e in db.scalars(select(ProjectWorkflowEvent).where(ProjectWorkflowEvent.project_id == project.id).order_by(ProjectWorkflowEvent.id)).all()]
        for needed in ("submitted_to_finance", "commercial_revision1_returned", "finance_returned", "bd_project_corrected", "commercial_revision1_approved_baseline"):
            assert needed in events


def test_change_after_approval_creates_revision2_and_never_overwrites_revision1():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align6@nakshatech.com", "bd")
        finance = make_user(db, "fin.align6@nakshatech.com", "finance")
        client = make_client(db, bd, "ALIGN-F")
        project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, "P-1006", commercial=commercial(estimated_amount=Decimal("2000000"), taxable_base_amount=Decimal("2000000"))))
        submit_project_to_finance(db, actor=bd, project_id=project.id)
        finance_review_project(db, actor=finance, project_id=project.id, payload=WorkflowFinanceReview(decision="approve", feedback=None))
        db.flush()
        rev1 = rev1_rows(db, project.id)[0]
        before = (rev1.id, Decimal(rev1.estimated_amount), rev1.status, rev1.approved_at)

        rev2 = create_estimate_revision(db, actor=bd, project_id=project.id, payload=revision_input(estimated_amount=Decimal("2400000"), taxable_base_amount=Decimal("2400000")))
        db.flush()
        assert rev2.revision_no == 2 and rev2.status == "PENDING_APPROVAL" and rev2.is_baseline is False
        assert Decimal(rev2.previous_amount) == Decimal("2000000.00")
        assert [row["revision_no"] for row in list_estimate_queue(db)] == [2]      # Finance decides revisions >= 2 from the queue
        assert (rev1.id, Decimal(rev1.estimated_amount), rev1.status, rev1.approved_at) == before   # Revision 1 untouched
        decide_estimate_revision(db, actor=finance, revision_id=rev2.id, payload=CommercialEstimateDecision(decision="approve", comments="Variation verified"))
        db.flush()
        assert rev2.status == "APPROVED" and rev1.status == "APPROVED"
        assert Decimal(workflow.commercial_value) == Decimal("2400000.00")            # latest APPROVED revision is the active basis


def test_first_submission_requires_revision1_but_legacy_resubmission_is_allowed():
    with SessionLocal() as db:
        bd = make_user(db, "bd.align7@nakshatech.com", "bd")
        client = make_client(db, bd, "ALIGN-G")
        project, workflow = create_bd_project(db, actor=bd, payload=project_payload(client, "P-1007"))     # no commercial block
        with pytest.raises(ValueError, match="Revision 1"):
            submit_project_to_finance(db, actor=bd, project_id=project.id)
        assert workflow.status == "draft"
        # legacy project: already submitted/returned once before the commercial layer existed
        workflow.submission_count = 1
        workflow.status = "finance_returned"
        submit_project_to_finance(db, actor=bd, project_id=project.id)
        assert workflow.status == "pending_finance_approval"
        assert rev1_rows(db, project.id) == []


def test_revision1_schema_needs_payment_terms_and_valid_billing_structure():
    with pytest.raises(ValidationError, match="Payment terms are required"):
        commercial(payment_terms=None)
    assert commercial(billing_type="Per Sq.Km", unit_rate=Decimal("10000"), estimated_quantity=Decimal("100")).billing_type == "per_sq_km"
    with pytest.raises(ValidationError, match="rate per unit"):
        commercial(billing_type="per_km")
    with pytest.raises(ValidationError, match="at least one billing milestone"):
        commercial(billing_type="milestone")
    with pytest.raises(ValidationError, match="more than 100%"):
        commercial(billing_type="milestone", milestones=[{"milestone_name": "M1", "percent": 60}, {"milestone_name": "M2", "percent": 50}])
    with pytest.raises(ValidationError, match="Unsupported billing type"):
        commercial(billing_type="barter")


# -------------------------------------------------------- 8-10: PM billing basis over the real HTTP routes
class AuthAs:
    """Override the auth dependency for one role/user for the duration of a `with` block."""

    def __init__(self, user: User, role: str | None = None) -> None:
        self.user = user
        self.role = role or user.role

    def __enter__(self) -> TestClient:
        app.dependency_overrides[get_current_auth] = lambda: CurrentAuth(user=self.user, claims={"role": self.role}, session=None)
        return TestClient(app, base_url="http://localhost")

    def __exit__(self, *exc) -> None:
        app.dependency_overrides.pop(get_current_auth, None)


def detached(db, user: User) -> User:
    db.refresh(user)
    db.expunge(user)
    return user


def seed_approved_per_unit_project(db, *, code: str, pm: User, bd: User, status: str = "in_progress", **commercial_overrides):
    project, workflow = make_project(db, owner=bd, code=code, status=status, pm=pm)
    upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(
        billing_type=commercial_overrides.pop("billing_type", "per_sq_km"),
        unit_rate=commercial_overrides.pop("unit_rate", Decimal("10000")),
        estimated_quantity=commercial_overrides.pop("estimated_quantity", Decimal("100")),
        estimated_amount=Decimal("1000000"), taxable_base_amount=Decimal("1000000"), tax_percent=Decimal("18"),
        **commercial_overrides,
    ))
    freeze_baseline_on_finance_approval(db, actor=bd, project_id=project.id)
    db.flush()
    return project, workflow


def test_only_the_assigned_pm_can_confirm_billing_basis_and_sees_no_commercial_values():
    with SessionLocal() as db:
        bd = make_user(db, "bd.pm1@nakshatech.com", "bd")
        pm = make_user(db, "pm.pm1@nakshatech.com", "ortho", "PM One")
        other_pm = make_user(db, "pm.other@nakshatech.com", "ortho", "Other PM")
        employee = make_user(db, "emp.pm1@nakshatech.com", "employee")
        project, _ = seed_approved_per_unit_project(db, code="PM-1", pm=pm, bd=bd)
        other_project, _ = make_project(db, owner=bd, code="PM-2", pm=other_pm)
        db.commit()
        pid, other_pid = project.id, other_project.id
        pm, other_pm, employee = detached(db, pm), detached(db, other_pm), detached(db, employee)

    with AuthAs(pm) as client:
        view = client.get(f"/api/commercial/projects/{pid}/pm-billing-basis")
        assert view.status_code == 200, view.text
        body = view.json()
        assert body["billing_type"] == "per_sq_km" and body["quantity_unit"] == "sq.km" and body["commercial_values_visible"] is False
        flat = view.text.lower()
        for secret in ("unit_rate", "estimated_amount", "base_inr", "gross_inr", "fx_rate", "margin", "10000", "1000000", "tax_percent"):
            assert secret not in flat, f"PM view leaked {secret}"

        saved = client.post(f"/api/commercial/projects/{pid}/pm-billing-basis", json={
            "cumulative_billable_quantity": "85", "delivery_accepted": True, "acceptance_reference": "Client mail 12-Nov",
            "pm_remarks": "Blocks 1-4 accepted", "billing_readiness_date": "2026-11-15",
        })
        assert saved.status_code == 201, saved.text
        assert saved.json()["cumulative_billable_quantity"] == 85.0 and saved.json()["quantity_unit"] == "sq.km"
        for secret in ("unit_rate", "amount", "fx_rate", "margin"):
            assert secret not in saved.text.lower().replace("cumulative_billable_quantity", "")

        # a PM cannot confirm billing for a project they do not manage
        assert client.get(f"/api/commercial/projects/{other_pid}/pm-billing-basis").status_code == 403
        assert client.post(f"/api/commercial/projects/{other_pid}/pm-billing-basis", json={"cumulative_billable_quantity": "1", "delivery_accepted": True}).status_code == 403
    with AuthAs(other_pm) as client:
        assert client.post(f"/api/commercial/projects/{pid}/pm-billing-basis", json={"cumulative_billable_quantity": "999", "delivery_accepted": True}).status_code == 403
    with AuthAs(employee) as client:
        assert client.get(f"/api/commercial/projects/{pid}/pm-billing-basis").status_code == 403


def test_pm_cannot_edit_commercial_terms_or_read_profitability_and_finance_data():
    with SessionLocal() as db:
        bd = make_user(db, "bd.pm2@nakshatech.com", "bd")
        pm = make_user(db, "pm.pm2@nakshatech.com", "ortho")
        project, _ = seed_approved_per_unit_project(db, code="PM-3", pm=pm, bd=bd)
        db.commit()
        pid = project.id
        pm = detached(db, pm)
    body = {
        "scope_description": "tamper", "billing_type": "fixed_price", "payment_terms": "x", "currency_code": "INR",
        "estimated_amount": "1", "estimate_date": "2026-09-21", "reason": "tamper",
    }
    with AuthAs(pm) as client:
        assert client.put(f"/api/commercial/projects/{pid}/estimates/baseline", json=body).status_code == 403
        assert client.post(f"/api/commercial/projects/{pid}/estimates/revisions", json=body).status_code == 403
        assert client.get(f"/api/commercial/projects/{pid}/estimates").status_code == 403
        assert client.get(f"/api/commercial/projects/{pid}/billing-recommendation").status_code == 403
        assert client.get(f"/api/commercial/projects/{pid}/cost-summary").status_code == 403
        assert client.get("/api/commercial/management/analytics").status_code == 403
        assert client.get("/api/commercial/vendor-invoices").status_code == 403
        assert client.post("/api/commercial/estimates/revisions/1/decision", json={"decision": "approve", "comments": "self"}).status_code == 403
        # nor may the PM use the commercial-review or invoice routes of the lifecycle
        assert client.post(f"/api/operations/lifecycle/projects/{pid}/invoices", json={
            "invoice_number": "X", "invoice_date": "2026-09-21", "due_date": "2026-10-21", "amount": "1"}).status_code == 403


def test_pm_billing_basis_window_and_lock_after_invoice():
    with SessionLocal() as db:
        bd = make_user(db, "bd.pm3@nakshatech.com", "bd")
        finance = make_user(db, "fin.pm3@nakshatech.com", "finance")
        pm = make_user(db, "pm.pm3@nakshatech.com", "ortho")
        early, _ = make_project(db, owner=bd, code="PM-4", status="pending_finance_approval", pm=pm)
        with pytest.raises(ValueError, match="under way"):
            record_billing_basis(db, actor=pm, project_id=early.id, payload=BillingBasisInput(cumulative_billable_quantity=Decimal("1"), delivery_accepted=True, pm_remarks="x"))
        project, workflow = seed_approved_per_unit_project(db, code="PM-5", pm=pm, bd=bd)
        record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(cumulative_billable_quantity=Decimal("40"), delivery_accepted=True))
        workflow.status = READY_FOR_BILLING
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
            invoice_number="INV-PM-5", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("400000"),
            tax_amount=Decimal("72000"), billed_quantity=Decimal("40")))
        raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
        with pytest.raises(ValueError, match="already been raised"):
            record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(cumulative_billable_quantity=Decimal("60"), delivery_accepted=True))


# ------------------------------------------- 11-14: Finance billing consumes approved basis + PM basis (advisory)
def test_per_unit_recommendation_matches_the_worked_example_and_blocks_over_billing():
    with SessionLocal() as db:
        bd = make_user(db, "bd.unit@nakshatech.com", "bd")
        finance = make_user(db, "fin.unit@nakshatech.com", "finance")
        pm = make_user(db, "pm.unit@nakshatech.com", "ortho")
        project, workflow = seed_approved_per_unit_project(db, code="P-1001-U", pm=pm, bd=bd)

        none_yet = billing_recommendation(db, project_id=project.id)
        assert none_yet["recommendation"] is None and any("not confirmed a billable quantity" in w for w in none_yet["warnings"])

        record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(cumulative_billable_quantity=Decimal("85"), delivery_accepted=True, acceptance_reference="ACC-1"))
        result = billing_recommendation(db, project_id=project.id)
        basis, rec = result["commercial_basis"], result["recommendation"]
        assert basis["revision_no"] == 1 and basis["unit_rate"] == 10000.0 and basis["billing_type"] == "per_sq_km"
        assert rec["method"] == "UNIT_RATE" and rec["quantity"] == 85.0
        assert rec["base_amount"] == 850000.0          # 85 sq.km x Rs 10,000
        assert rec["tax_amount"] == 153000.0 and rec["gross_amount"] == 1003000.0
        assert "85" in rec["formula"] and "10000" in rec["formula"]
        assert result["pm_basis"]["cumulative_billable_quantity"] == 85.0 and result["pm_basis"]["acceptance_reference"] == "ACC-1"

        # Finance decides: advisory only, nothing was raised automatically
        assert db.scalar(select(func.count(ProjectInvoice.id)).where(ProjectInvoice.project_id == project.id)) == 0
        workflow.status = READY_FOR_BILLING
        with pytest.raises(ValueError, match="exceeds the PM-confirmed"):
            create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
                invoice_number="INV-U-0", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("900000"), billed_quantity=Decimal("90")))
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
            invoice_number="INV-U-1", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("850000"),
            tax_amount=Decimal("153000"), tax_percent=Decimal("18"), billed_quantity=Decimal("85"), billing_basis_id=result["pm_basis"]["id"]))
        assert invoice.estimate_revision_id == basis["id"] and Decimal(invoice.billed_quantity) == Decimal("85") and invoice.status == "INVOICE_DRAFT"
        fully = billing_recommendation(db, project_id=project.id)
        assert fully["recommendation"] is None and any("fully invoiced" in w for w in fully["warnings"])
        assert fully["invoiced_to_date"]["quantity"] == 85.0


def test_fixed_price_recommendation_uses_pm_completion_or_acceptance():
    with SessionLocal() as db:
        bd = make_user(db, "bd.fixed@nakshatech.com", "bd")
        pm = make_user(db, "pm.fixed@nakshatech.com", "ortho")
        project, _ = make_project(db, owner=bd, code="P-FIX", pm=pm)
        upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(estimated_amount=Decimal("1000000"), taxable_base_amount=Decimal("1000000")))
        freeze_baseline_on_finance_approval(db, actor=bd, project_id=project.id)
        record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(completion_percent=Decimal("60")))
        rec = billing_recommendation(db, project_id=project.id)["recommendation"]
        assert rec["method"] == "FIXED_PRICE" and rec["base_amount"] == 600000.0 and rec["completion_percent"] == 60.0
        record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(delivery_accepted=True, acceptance_reference="Final acceptance"))
        rec = billing_recommendation(db, project_id=project.id)["recommendation"]
        assert rec["base_amount"] == 1000000.0 and rec["completion_percent"] == 100.0
        with pytest.raises(ValueError, match="completion percentage or that delivery"):
            record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(pm_remarks="nothing concrete"))


def test_milestone_recommendation_follows_the_pm_confirmed_milestone():
    with SessionLocal() as db:
        bd = make_user(db, "bd.mile@nakshatech.com", "bd")
        finance = make_user(db, "fin.mile@nakshatech.com", "finance")
        pm = make_user(db, "pm.mile@nakshatech.com", "ortho")
        project, workflow = make_project(db, owner=bd, code="P-MILE", pm=pm)
        upsert_baseline_estimate(db, actor=bd, project_id=project.id, payload=commercial(
            billing_type="milestone", estimated_amount=Decimal("1000000"), taxable_base_amount=Decimal("1000000"),
            milestones=[{"milestone_name": "Advance", "percent": 30}, {"milestone_name": "Survey completed", "percent": 40}, {"milestone_name": "Final delivery", "percent": 30}]))
        freeze_baseline_on_finance_approval(db, actor=bd, project_id=project.id)
        milestones = list(db.scalars(select(ProjectCommercialMilestone).order_by(ProjectCommercialMilestone.sequence)).all())
        assert [(m.sequence, Decimal(m.amount)) for m in milestones] == [(1, Decimal("300000.00")), (2, Decimal("400000.00")), (3, Decimal("300000.00"))]

        view = pm_billing_basis_view(db, actor=pm, project_id=project.id)
        assert [m["name"] for m in view["milestones"]] == ["Advance", "Survey completed", "Final delivery"]
        assert all(set(m) == {"id", "sequence", "name"} for m in view["milestones"])       # names only: no percent / amount for the PM

        assert billing_recommendation(db, project_id=project.id)["recommendation"] is None
        with pytest.raises(ValueError, match="achieved and accepted"):
            record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(milestone_id=milestones[1].id, delivery_accepted=False))
        record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(milestone_id=milestones[1].id, delivery_accepted=True, acceptance_reference="Survey sign-off"))
        rec = billing_recommendation(db, project_id=project.id)["recommendation"]
        assert rec["method"] == "MILESTONE" and rec["milestone_name"] == "Survey completed" and rec["base_amount"] == 400000.0

        workflow.status = READY_FOR_BILLING
        with pytest.raises(ValueError, match="has not confirmed this milestone"):
            create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
                invoice_number="INV-M-X", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("300000"), billed_milestone_id=milestones[2].id))
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
            invoice_number="INV-M-2", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("400000"), billed_milestone_id=milestones[1].id))
        assert invoice.billed_milestone_id == milestones[1].id
        assert billing_recommendation(db, project_id=project.id)["recommendation"] is None     # milestone 2 is now invoiced
        with pytest.raises(ValueError, match="already been invoiced"):
            record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(milestone_id=milestones[1].id, delivery_accepted=True))


# ----------------------------------------------------------------------------- 15-20: legacy + unchanged behaviour
def test_legacy_project_without_commercial_revision_still_works_end_to_end():
    with SessionLocal() as db:
        finance = make_user(db, "fin.legacy@nakshatech.com", "finance")
        pm = make_user(db, "pm.legacy@nakshatech.com", "ortho")
        project, workflow = make_project(db, owner=finance, code="P-LEGACY", status="in_progress", pm=pm)
        workflow.submission_count = 1          # submitted/approved before the commercial layer existed
        assert rev1_rows(db, project.id) == []
        assert prepare_revision1_for_finance_submission(db, actor=finance, project_id=project.id) is None   # legacy: first submission of an existing row
        result = billing_recommendation(db, project_id=project.id)
        assert result["commercial_basis"] is None and result["recommendation"] is None
        assert any("legacy project" in w for w in result["warnings"])
        # the PM can still confirm a generic operational basis (no approved commercial billing type to follow)
        entry = record_billing_basis(db, actor=pm, project_id=project.id, payload=BillingBasisInput(pm_remarks="Delivered 12 sites", cumulative_billable_quantity=Decimal("12"), quantity_unit="site"))
        assert entry.billing_type == "other" and entry.estimate_revision_id is None
        workflow.status = READY_FOR_BILLING
        invoice = create_invoice_draft(db, actor=finance, project_id=project.id, payload=InvoiceDraftCreate(
            invoice_number="INV-LEG-1", invoice_date=date(2026, 9, 21), due_date=date(2026, 10, 21), amount=Decimal("5000")))
        assert invoice.estimate_revision_id is None and Decimal(invoice.base_inr) == Decimal("5000.00")


def test_employee_project_expenses_remain_inr_only():
    assert not hasattr(ProjectExpense, "currency_code") and not hasattr(ProjectExpense, "currency") and not hasattr(ProjectExpense, "fx_rate_to_inr")
    assert not {"currency", "currency_code", "fx_rate_to_inr", "fx_rate_mode"} & set(ProjectExpenseInput.model_fields)


def test_commercial_vs_fx_variance_formula_matches_the_documented_example():
    baseline = SimpleNamespace(currency_code="USD", taxable_base_amount=Decimal("10000"), fx_rate_to_inr=Decimal("84"))
    invoices = [SimpleNamespace(currency="USD", amount=Decimal("11000"), fx_rate_to_inr=Decimal("88.5"))]
    scope, fx = commercial_and_fx_variance(baseline, invoices)
    assert scope == Decimal("84000.00")                    # (11,000 - 10,000) x 84
    assert fx == Decimal("49500.00")                       # 11,000 x (88.5 - 84)
    assert scope + fx == Decimal("973500.00") - Decimal("840000.00")
    two = commercial_and_fx_variance(baseline, [
        SimpleNamespace(currency="USD", amount=Decimal("6000"), fx_rate_to_inr=Decimal("86")),
        SimpleNamespace(currency="USD", amount=Decimal("5000"), fx_rate_to_inr=Decimal("90"))])
    assert two == (Decimal("84000.00"), Decimal("42000.00"))     # 6000x2 + 5000x6
    assert commercial_and_fx_variance(baseline, [SimpleNamespace(currency="EUR", amount=Decimal("1"), fx_rate_to_inr=Decimal("90"))]) == (None, None)
    assert commercial_and_fx_variance(None, invoices) == (None, None)


def test_http_create_project_with_revision1_is_atomic_and_maps_fx_outage_to_503():
    with SessionLocal() as db:
        bd = make_user(db, "bd.http@nakshatech.com", "bd")
        client_row = make_client(db, bd, "ALIGN-H")
        db.commit()
        client_id = client_row.id
        bd = detached(db, bd)
    body = {
        "client_id": client_id, "project_code": "P-HTTP-1", "project_name": "HTTP created", "start_date": "2026-10-01", "end_date": "2026-12-31",
        "scope_text": "Survey", "commercial": {
            "scope_description": "Survey and deliver", "billing_type": "Per Sq.Km", "unit_rate": "10000", "estimated_quantity": "100",
            "payment_terms": "30 days", "currency_code": "INR", "estimated_amount": "1000000", "tax_percent": "18", "po_wo_reference": "PO-9"},
    }
    with AuthAs(bd) as client:
        created = client.post("/api/operations/workflow/bd/projects", json=body)
        assert created.status_code == 201, created.text
        summary = created.json()["commercial"]
        assert summary["has_commercial"] and summary["baseline"]["revision_no"] == 1 and summary["baseline"]["billing_type_label"] == "Per Sq.Km"
        # BD registers the project with its commercial summary (Finance review reads the same payload)
        register = client.get("/api/operations/workflow/bd/dashboard").json()
        assert register["projects"][0]["commercial_summary"]["baseline"]["currency_code"] == "INR"
        # submit -> Revision 1 goes with it
        assert client.post(f"/api/operations/workflow/bd/projects/{created.json()['project_id']}/submit-finance").status_code == 200

        # foreign currency while every FX provider is down: structured 503 and NOTHING is created
        set_fx_service(FxRateService(providers=[DownProvider()], max_retries=0, sleep=lambda _s: None))
        down = client.post("/api/operations/workflow/bd/projects", json={**body, "project_code": "P-HTTP-2", "commercial": {**body["commercial"], "billing_type": "fixed_price", "unit_rate": None, "estimated_quantity": None, "currency_code": "USD"}})
        assert down.status_code == 503 and down.json()["detail"]["code"] == "FX_UNAVAILABLE"
    with SessionLocal() as db:
        assert db.scalar(select(func.count(FinanceProject.id)).where(FinanceProject.project_code == "P-HTTP-2")) == 0
        assert db.scalar(select(func.count(FinanceProject.id)).where(FinanceProject.project_code == "P-HTTP-1")) == 1
