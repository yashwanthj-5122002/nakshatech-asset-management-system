"""Invoice-format export and Finance-only edit API regression tests."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.api.dependencies import get_current_auth
from app.core.database import SessionLocal
from app.main import app
from app.modules.employee_portal.models import AuditEvent
from app.modules.finance.advance import ClientAdvanceTransaction
from app.modules.finance.standalone_invoice_models import StandaloneInvoice
from app.modules.operations.lifecycle_models import ProjectInvoice
from test_standalone_invoice_generation import API, _client_for, _payload, _seed_finance_and_denied_roles


def test_standalone_edit_reuses_existing_tax_validation_and_does_not_touch_project_ledgers():
    with SessionLocal() as db:
        users = _seed_finance_and_denied_roles(db)
        project_count = db.scalar(select(func.count(ProjectInvoice.id)))
        advance_count = db.scalar(select(func.count(ClientAdvanceTransaction.id)))

    client, _ = _client_for("finance", users["finance"])
    try:
        created = client.post(API, json=_payload("INV-EDIT-ONLY", tax_mode="igst"))
        assert created.status_code == 201, created.text
        invoice_id = created.json()["invoice"]["id"]
        before_total = Decimal(str(created.json()["totals"]["invoice_total"]))
        assert before_total == Decimal("88500")

        data = client.get(f"{API}/{invoice_id}/edit")
        assert data.status_code == 200, data.text
        form = data.json()
        assert form["seller"]["gstin"] == "29ABCDE1234F1Z5"
        assert form["line_items"][0]["hsn_sac"] == "998314"
        assert form["tax_mode"] == "igst"

        # Edit only the descriptive fields; invoice number + all tax data must remain the same.
        form["notes"] = "Client-approved revised descriptive notes"
        form["terms_conditions"] = "Net 15; revised service instructions"
        edited = client.put(f"{API}/{invoice_id}", json=form)
        assert edited.status_code == 200, edited.text
        assert edited.json()["invoice"]["id"] == invoice_id
        assert edited.json()["totals"] == created.json()["totals"]
        assert edited.json()["notes"].startswith("Client-approved")
        assert [line["hsn_sac"] for line in edited.json()["line_items"]] == ["998314", "998314"]

        # Financially inconsistent updates must fail without modifying the stored invoice.
        broken = dict(form)
        broken["line_items"] = [dict(line) for line in form["line_items"]]
        broken["line_items"][0]["tax_amount"] = "0.01"
        rejected = client.put(f"{API}/{invoice_id}", json=broken)
        assert rejected.status_code == 422, rejected.text
        assert client.get(f"{API}/{invoice_id}").json()["totals"] == edited.json()["totals"]

        renumber = dict(form)
        renumber["invoice_number"] = "NEW-NUMBER-FORBIDDEN"
        assert client.put(f"{API}/{invoice_id}", json=renumber).status_code == 422

        # Export all 3 formats without creating additional invoice records.
        for template in ("green_gold", "modern_teal", "geospatial_blue"):
            pdf = client.get(f"{API}/{invoice_id}/document.pdf?template={template}&download=true")
            assert pdf.status_code == 200, pdf.text[:250] if not pdf.content.startswith(b"%PDF") else ""
            assert pdf.content.startswith(b"%PDF")
            assert template in pdf.headers["content-disposition"]
        assert client.get(f"{API}/{invoice_id}/document.pdf?template=unknown").status_code == 422

        denied, _ = _client_for("employee", users["employee"])
        assert denied.get(f"{API}/{invoice_id}/edit").status_code == 403
        assert denied.put(f"{API}/{invoice_id}", json=form).status_code == 403
        # Restore Finance auth for counting irrelevant, but no more calls needed.
        with SessionLocal() as db:
            assert db.scalar(select(func.count(ProjectInvoice.id))) == project_count
            assert db.scalar(select(func.count(ClientAdvanceTransaction.id))) == advance_count
            assert db.scalar(select(func.count(StandaloneInvoice.id))) == 1
            assert db.scalar(select(func.count(AuditEvent.id)).where(AuditEvent.event_type == "STANDALONE_INVOICE_EDITED")) == 1
    finally:
        app.dependency_overrides.pop(get_current_auth, None)


def test_project_draft_edit_is_metadata_only_and_issued_invoices_are_locked():
    from fastapi.testclient import TestClient
    from app.api.dependencies import CurrentAuth
    from app.models.entities import User
    from app.modules.operations.lifecycle_service import create_invoice_draft
    from test_invoice_generation_v2 import _billable_project, _demo_payload

    with SessionLocal() as db:
        actor, _, project = _billable_project(db, "STYLE_EDIT")
        row = create_invoice_draft(db, actor=actor, project_id=project.id,
                                   payload=_demo_payload(invoice_number="INV-STYLE-EDIT"))
        project_id, invoice_id, actor_email = project.id, row.id, actor.email
        db.commit()

    def authenticated_finance():
        with SessionLocal() as db:
            finance = db.scalar(select(User).where(User.email == actor_email))
            return CurrentAuth(user=finance, claims={"role": "finance"}, session=None)

    app.dependency_overrides[get_current_auth] = authenticated_finance
    try:
        client = TestClient(app)
        before = client.get(f"/api/operations/lifecycle/invoices/{invoice_id}/document")
        assert before.status_code == 200, before.text
        original_totals = before.json()["totals"]
        original_lines = before.json()["tax_lines"]
        edited = client.patch(f"/api/operations/lifecycle/invoices/{invoice_id}/draft-details", json={
            "notes": "Updated project draft details for client", "place_of_supply": "Karnataka",
            "payment_terms": "Net 30 revised notes", "dispatch_details": "Deliverables dispatched digitally",
        })
        assert edited.status_code == 200, edited.text
        assert edited.json()["totals"] == original_totals
        assert edited.json()["tax_lines"] == original_lines
        assert edited.json()["invoice"]["place_of_supply"] == "Karnataka"
        with SessionLocal() as db:
            persisted = db.get(ProjectInvoice, invoice_id)
            assert persisted.amount == Decimal("125000")
            assert persisted.tax_amount == Decimal("22500")
            assert persisted.cgst_amount == Decimal("11250")
            assert persisted.sgst_amount == Decimal("11250")
            assert persisted.project_id == project_id
            assert persisted.status == "INVOICE_DRAFT"
            # Simulate subsequent authorized issuing; no edits afterward.
            persisted.status = "INVOICE_RAISED"
            db.commit()
        denied = client.patch(f"/api/operations/lifecycle/invoices/{invoice_id}/draft-details", json={"notes": "illegal issued edit"})
        assert denied.status_code == 409
        with SessionLocal() as db:
            assert db.get(ProjectInvoice, invoice_id).notes == "Updated project draft details for client"
    finally:
        app.dependency_overrides.pop(get_current_auth, None)
