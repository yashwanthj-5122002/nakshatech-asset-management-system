"""SEC-10 and SEC-11 regression: object-level scope and the IT asset register.

SEC-10 - ``GET /api/business/records/{id}/history`` carries actor identities and
the diff of every amount change. It must answer 404 for a caller who cannot see
the record in the overview, otherwise any signed-in employee can walk the
sequential record ids.

SEC-11 - ``GET /api/ticket-assets`` searches the live Asset Register to let an
employee pick their machine while raising a ticket. Unscoped, that endpoint
hands every holder, workstation number, department and specification to any
signed-in account, so the result set is limited to the caller's department, or
to assets recorded against their own name when no department resolves.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.testclient import TestClient


def _user(db, email: str, full_name: str, role: str):
    from app.models.entities import User

    user = User(
        email=email,
        full_name=full_name,
        password_hash="pytest-only-password-hash",
        role=role,
        branch="Head Office",
        is_active=True,
        token_version=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _record(db):
    from app.modules.business.models import BusinessRecord
    from app.modules.finance.models import FinanceProject

    project = FinanceProject(project_code="SCOPE-PRJ-1", project_name="Scope Fixture Project")
    db.add(project)
    db.commit()
    db.refresh(project)
    record = BusinessRecord(reporting_month="2026-09", project_id=project.id, department_code="ortho")
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def test_business_history_denied_to_caller_who_cannot_see_the_record():
    from app.core.database import SessionLocal
    from app.modules.business.service import record_history

    with SessionLocal() as db:
        employee = _user(db, "scope.employee@nakshatech.com", "Scope Employee", "employee")
        record = _record(db)

        try:
            record_history(db, record_id=record.id, viewer=employee, effective_role="employee")
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("employee read another account's business record history")


def test_business_history_allowed_for_privileged_role():
    from app.core.database import SessionLocal
    from app.modules.business.service import record_history

    with SessionLocal() as db:
        admin = _user(db, "scope.admin@nakshatech.com", "Scope Admin", "admin")
        record = _record(db)

        entries = record_history(db, record_id=record.id, viewer=admin, effective_role="admin")
        assert isinstance(entries, list)


def test_business_history_endpoint_returns_404_for_employee_and_200_for_admin():
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.main import app

    with SessionLocal() as db:
        employee = _user(db, "scope.http.employee@nakshatech.com", "Scope Http Employee", "employee")
        admin = _user(db, "scope.http.admin@nakshatech.com", "Scope Http Admin", "admin")
        record = _record(db)
        employee_token = create_access_token(employee.email, employee.role, token_version=int(employee.token_version or 0))
        admin_token = create_access_token(admin.email, admin.role, token_version=int(admin.token_version or 0))
        record_id = record.id

    client = TestClient(app)
    denied = client.get(f"/api/business/records/{record_id}/history", headers={"Authorization": f"Bearer {employee_token}"})
    assert denied.status_code == 404, denied.text

    allowed = client.get(f"/api/business/records/{record_id}/history", headers={"Authorization": f"Bearer {admin_token}"})
    assert allowed.status_code == 200, allowed.text


def test_ticket_asset_search_never_exposes_other_holders_to_an_employee():
    from app.core.database import SessionLocal
    from app.core.security import create_access_token
    from app.main import app
    from app.models.entities import Asset

    with SessionLocal() as db:
        _user(db, "scope.search@nakshatech.com", "Scope Search Employee", "employee")
        admin = _user(db, "scope.search.admin@nakshatech.com", "Scope Search Admin", "admin")
        db.add(Asset(asset_code="SCOPE-AST-1", device_type="Laptop", status="issued",
                     used_by="Somebody Else", department="FINANCE", workstation_no="WS-901"))
        db.add(Asset(asset_code="SCOPE-AST-2", device_type="Laptop", status="issued",
                     used_by="Scope Search Employee", department="IT", workstation_no="WS-902"))
        db.commit()
        employee_token = create_access_token("scope.search@nakshatech.com", "employee", token_version=0)
        admin_token = create_access_token(admin.email, admin.role, token_version=int(admin.token_version or 0))

    client = TestClient(app)
    employee_view = client.get(
        "/api/ticket-assets",
        params={"query": "scope-ast"},
        headers={"Authorization": f"Bearer {employee_token}"},
    )
    assert employee_view.status_code == 200, employee_view.text
    employee_codes = {row["asset_code"] for row in employee_view.json()}
    assert employee_codes == {"SCOPE-AST-2"}, employee_codes

    admin_view = client.get(
        "/api/ticket-assets",
        params={"query": "scope-ast"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert admin_view.status_code == 200, admin_view.text
    admin_codes = {row["asset_code"] for row in admin_view.json()}
    assert admin_codes == {"SCOPE-AST-1", "SCOPE-AST-2"}, admin_codes
