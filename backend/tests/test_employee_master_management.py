"""Management publication controls access to Excel employee identities."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import Workbook
import pytest
from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.core.security import create_access_token
from app.main import app
from app.models.entities import User
from app.modules.employee_portal.models import AuditEvent, Branch, EmailOTPChallenge, EmployeeMaster, EmployeeMasterPublication


@pytest.fixture(autouse=True)
def isolated_application_database():
    """Only the tables this control flow uses; the full ERP schema is large."""
    tables = [User.__table__, Branch.__table__, EmployeeMasterPublication.__table__,
              EmployeeMaster.__table__, EmailOTPChallenge.__table__, AuditEvent.__table__]
    Base.metadata.create_all(bind=engine, tables=tables)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine, tables=tables)


def _user(email: str, role: str) -> dict[str, str]:
    with SessionLocal() as db:
        db.add(User(email=email, full_name=role.title(), password_hash="test-only", role=role,
                    branch="Head Office", is_active=True, account_status="active"))
        db.commit()
    token = create_access_token(email, role, token_version=0)
    return {"Authorization": f"Bearer {token}"}


def _workbook() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.append(["SL.No", "Accesscardno", "Employee Number", "Employee Name", "Phone",
                  "Curr.Department", "Curr.Designation", "Email"])
    sheet.append([1, "NT1001", "1001", "Example Employee", "9876543210", "IT",
                  "Engineer", "example.employee@nakshatech.com"])
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def test_management_import_publish_hide_and_purge() -> None:
    manager = _user("manager.control@nakshatech.com", "management")
    software = _user("software.control@nakshatech.com", "software_team")
    content = _workbook()
    upload = lambda: {"file": ("employees.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    client = TestClient(app)

    assert client.post("/api/management/employee-master/preview", headers=software, files=upload()).status_code == 403
    preview = client.post("/api/management/employee-master/preview", headers=manager, files=upload())
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_import"] is True
    assert preview.json()["report"]["total_rows"] == 1

    imported = client.post("/api/management/employee-master/import", headers=manager, files=upload())
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 1
    assert client.get("/api/management/employee-master/status", headers=manager).json()["published"] is False
    assert client.get("/api/software/employee-master", headers=software).json() == []
    assert client.post("/api/auth/register/request-otp", json={"email": "example.employee@nakshatech.com"}).status_code == 403

    published = client.put("/api/management/employee-master/publication", headers=manager, json={"published": True})
    assert published.status_code == 200, published.text
    assert len(client.get("/api/software/employee-master", headers=software).json()) == 1
    otp = client.post("/api/auth/register/request-otp", json={"email": "example.employee@nakshatech.com"})
    assert otp.status_code == 200, otp.text

    assert client.put("/api/management/employee-master/publication", headers=manager, json={"published": False}).status_code == 200
    assert client.get("/api/software/employee-master", headers=software).json() == []
    assert client.post("/api/auth/register/verify-otp", json={"email": "example.employee@nakshatech.com", "otp": otp.json()["development_otp"]}).status_code == 403
    assert client.put("/api/management/employee-master/publication", headers=manager, json={"published": True}).status_code == 200
    reimported = client.post("/api/management/employee-master/import", headers=manager, files=upload())
    assert reimported.status_code == 200, reimported.text
    assert reimported.json()["updated"] == 1
    assert client.get("/api/management/employee-master/status", headers=manager).json()["published"] is False
    assert client.get("/api/software/employee-master", headers=software).json() == []
    assert client.request("DELETE", "/api/management/employee-master/imported", headers=manager, json={"confirmation": "wrong"}).status_code == 400

    purged = client.request("DELETE", "/api/management/employee-master/imported", headers=manager,
                           json={"confirmation": "DELETE EMPLOYEE MASTER"})
    assert purged.status_code == 200, purged.text
    assert purged.json()["removed"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(EmployeeMaster.id)) is None


def test_purge_keeps_existing_user_account() -> None:
    manager = _user("manager.retention@nakshatech.com", "management")
    _user("example.employee@nakshatech.com", "employee")
    client = TestClient(app)
    imported = client.post("/api/management/employee-master/import", headers=manager,
                           files={"file": ("employees.xlsx", _workbook())})
    assert imported.status_code == 200, imported.text
    removed = client.request("DELETE", "/api/management/employee-master/imported", headers=manager,
                            json={"confirmation": "DELETE EMPLOYEE MASTER"})
    assert removed.status_code == 200, removed.text
    assert removed.json()["existing_accounts_retained"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(User.id).where(User.email == "example.employee@nakshatech.com")) is not None
        assert db.scalar(select(EmployeeMaster.id)) is None
