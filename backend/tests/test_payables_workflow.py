from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.payables.router import router


@pytest.fixture
def payable_api():
    accounts = {
        "admin": ("payables.admin@nakshatech.com", "admin"),
        "finance": ("finance@nakshatech.com", "finance"),
        "vinod": ("vinod@nakshatech.com", "management"),
        "chethan": ("chethan@nakshatech.com", "management"),
        "employee": ("payables.employee@nakshatech.com", "employee"),
    }
    ids = {}
    with SessionLocal() as db:
        for key, (email, role) in accounts.items():
            user = User(email=email, full_name=key, role=role, password_hash="test-only",
                        is_active=True, account_status="active")
            db.add(user)
            db.flush()
            ids[key] = user.id
        db.commit()
    identity = {"key": "admin"}

    def auth():
        with SessionLocal() as db:
            user = db.get(User, ids[identity["key"]])
            db.expunge(user)
            return CurrentAuth(user=user, claims={"role": user.role}, session=None)

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    test_app.dependency_overrides[get_current_auth] = auth
    with TestClient(test_app, raise_server_exceptions=False) as client:
        yield client, identity


def bill_payload():
    return {"bill_name": "Controlled QA bill", "bill_number": "QA-PAY-001",
            "bill_category": "Office", "vendor_name": "Synthetic QA Vendor",
            "bill_date": str(date.today()), "due_date": str(date.today()),
            "base_amount": "10000.00", "gst_rate": "18.00"}


def test_duplicate_vendor_bill_returns_conflict_instead_of_server_error(payable_api):
    client, _ = payable_api
    assert client.post("/api/payables", json=bill_payload()).status_code == 201
    response = client.post("/api/payables", json=bill_payload())
    assert response.status_code == 409, response.text
    assert len(client.get("/api/payables").json()) == 1


def test_payables_requires_both_approvals_and_reconciles_partial_payment(payable_api):
    client, identity = payable_api
    response = client.post("/api/payables", json=bill_payload())
    assert response.status_code == 201, response.text
    bill = response.json()
    assert bill["total_amount"] == 11800
    url = f'/api/payables/{bill["id"]}'
    assert client.post(url + "/submit").status_code == 409
    assert client.post(url + "/bill-document", files={"file": ("bill.pdf", b"%PDF-1.4\nQA", "application/pdf")}).status_code == 200
    assert client.post(url + "/submit").json()["status"] == "pending_approval"
    identity["key"] = "employee"
    assert client.get(url).status_code == 403
    identity["key"] = "vinod"
    assert client.post(url + "/decision", json={"decision": "approved"}).json()["status"] == "pending_approval"

    def payment(amount, reference):
        return client.post(url + "/payments", data={"amount": amount, "payment_date": str(date.today()),
                           "method": "bank_transfer", "reference": reference},
                           files={"proof": ("proof.pdf", b"%PDF-1.4\nQA", "application/pdf")})

    identity["key"] = "finance"
    assert payment("5000", "QA-FIRST").status_code == 409
    identity["key"] = "chethan"
    assert client.post(url + "/decision", json={"decision": "approved"}).json()["status"] == "approved"
    identity["key"] = "finance"
    assert payment("NaN", "QA-BAD").status_code == 400
    assert payment("11800.01", "QA-OVER").status_code == 400
    partial = payment("5000", "QA-FIRST")
    assert partial.status_code == 200, partial.text
    assert partial.json()["status"] == "partially_paid"
    assert partial.json()["balance_amount"] == 6800
    assert payment("100", "QA-FIRST").status_code == 409
    assert client.put(url, json=bill_payload()).status_code == 409
    closed = payment("6800", "QA-FINAL")
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "paid_closed"
    assert closed.json()["balance_amount"] == 0
    assert len(closed.json()["payments"]) == 2
    assert payment("1", "QA-AFTER-CLOSE").status_code == 409
