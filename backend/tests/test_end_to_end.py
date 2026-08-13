from __future__ import annotations

from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

TEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_asset_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret-only-change-me-32-characters"
os.environ["LOCAL_BACKUP_AGENT_ENABLED"] = "true"
os.environ["LOCAL_BACKUP_AGENT_TOKEN"] = "test-local-backup-token-abcdefghijklmnopqrstuvwxyz-123456"
os.environ["BACKUP_TIMEZONE"] = "Asia/Kolkata"
os.environ["EMAIL_DELIVERY_MODE"] = "console"
os.environ["IT_SUPPORT_EMAIL"] = "software.team@nakshatech.com"
os.environ["NAKSHA_COPILOT_ENABLED"] = "true"
os.environ["GEMINI_API_KEY"] = "test-gemini-key-never-used-on-network"
os.environ["GEMINI_MODEL"] = "gemini-3.5-flash-lite"
os.environ["NAKSHA_COPILOT_REQUESTS_PER_HOUR"] = "50"
os.environ["SEED_ADMIN_EMAIL"] = "admin@nakshatech.com"
os.environ["SEED_ADMIN_PASSWORD"] = "Admin@123"
os.environ["SEED_SOFTWARE_TEAM_EMAIL"] = "software.team@nakshatech.com"
os.environ["SEED_SOFTWARE_TEAM_PASSWORD"] = "SoftwareTemporary@2026"
os.environ["SEED_ORGANIZATION_ADMIN_EMAIL"] = ""
os.environ["SEED_ORGANIZATION_ADMIN_PASSWORD"] = ""
os.environ["SEED_MANAGEMENT_EMAIL"] = "vinod@nakshatech.com"
os.environ["SEED_MANAGEMENT_PASSWORD"] = "VinodTemporary@2026"
os.environ["SEED_MANAGEMENT_SECONDARY_EMAIL"] = "chethan@nakshatech.com"
os.environ["SEED_MANAGEMENT_SECONDARY_PASSWORD"] = "ChethanTemporary@2026"
os.environ["TOTP_ENCRYPTION_KEY"] = "test-totp-encryption-key-at-least-32-characters"
os.environ["SEED_IT_EMAIL"] = "it-support@nakshatech.com"
os.environ["SEED_IT_PASSWORD"] = "ITTemporary@2026"
os.environ["SEED_DRONE_EMAIL"] = "drone@nakshatech.com"
os.environ["SEED_DRONE_PASSWORD"] = "Drone@123"

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models.entities import ApprovalDecisionHistory, User  # noqa: E402
from app.modules.employee_portal.models import AuthenticatorCredential  # noqa: E402
from app.modules.employee_portal.service import decrypt_totp_secret, totp_code  # noqa: E402


MANAGEMENT_TEST_EMAIL = "vinod@nakshatech.com"
MANAGEMENT_TEMP_PASSWORD = "VinodTemporary@2026"
MANAGEMENT_PERMANENT_PASSWORD = "VinodPermanent@2026"
SOFTWARE_TEST_EMAIL = "software.team@nakshatech.com"
SOFTWARE_TEMP_PASSWORD = "SoftwareTemporary@2026"
SOFTWARE_PERMANENT_PASSWORD = "SoftwarePermanent@2026"
IT_TEST_EMAIL = "it-support@nakshatech.com"
IT_TEMP_PASSWORD = "ITTemporary@2026"
IT_PERMANENT_PASSWORD = "ITPermanent@2026"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
    TEST_DB.unlink(missing_ok=True)


def _authenticator_code(email: str) -> str:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        credential = db.scalar(
            select(AuthenticatorCredential).where(AuthenticatorCredential.user_id == user.id)
        )
        assert credential is not None
        return totp_code(decrypt_totp_secret(credential.encrypted_secret))


def _ensure_privileged_test_login(
    client: TestClient,
    *,
    role: str,
    email: str,
    temporary_password: str,
    permanent_password: str,
):
    response = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": permanent_password},
    )
    if response.status_code == 200 and response.json().get("access_token"):
        return response

    first_login = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": temporary_password},
    )
    assert first_login.status_code == 200, first_login.text
    first_payload = first_login.json()
    assert first_payload["mfa_setup_required"] is True

    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={
            "mfa_setup_token": first_payload["mfa_setup_token"],
            "code": _authenticator_code(email),
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_payload = confirmed.json()
    assert confirmed_payload["password_change_required"] is True

    completed = client.post(
        "/api/auth/privileged/complete-setup",
        json={
            "password_change_token": confirmed_payload["password_change_token"],
            "new_password": permanent_password,
            "confirm_password": permanent_password,
        },
    )
    assert completed.status_code == 200, completed.text
    return completed


def login(client: TestClient, role: str, email: str, password: str) -> dict[str, str]:
    if role == "management":
        response = _ensure_privileged_test_login(
            client,
            role=role,
            email=MANAGEMENT_TEST_EMAIL,
            temporary_password=MANAGEMENT_TEMP_PASSWORD,
            permanent_password=MANAGEMENT_PERMANENT_PASSWORD,
        )
    elif role == "software_team":
        response = _ensure_privileged_test_login(
            client,
            role=role,
            email=SOFTWARE_TEST_EMAIL,
            temporary_password=SOFTWARE_TEMP_PASSWORD,
            permanent_password=SOFTWARE_PERMANENT_PASSWORD,
        )
    elif role == "it":
        response = _ensure_privileged_test_login(
            client,
            role=role,
            email=IT_TEST_EMAIL,
            temporary_password=IT_TEMP_PASSWORD,
            permanent_password=IT_PERMANENT_PASSWORD,
        )
    elif role == "admin":
        response = client.post(
            "/api/auth/login",
            json={"role": "admin", "email": "admin@nakshatech.com", "password": "Admin@123"},
        )
    else:
        response = client.post(
            "/api/auth/login",
            json={"role": role, "email": email, "password": password},
        )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == role
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _approval_notification(
    client: TestClient,
    headers: dict[str, str],
    *,
    event_type: str,
    record_code: str,
    target_prefix: str,
) -> dict:
    response = client.get(
        "/api/notifications/global?category=approval&limit=200",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    matches = [
        item for item in response.json()
        if item["event_type"] == event_type and record_code in f"{item['title']} {item['message']}"
    ]
    assert len(matches) == 1, (event_type, record_code, response.json())
    assert matches[0]["target_url"].startswith(target_prefix)
    return matches[0]


def test_health_and_all_development_accounts(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "healthy"
    accounts = [
        ("admin", "admin@nakshatech.com", "Admin@123"),
        ("management", "management@nakshatech.com", "Manager@123"),
        ("it", "it@nakshatech.com", "IT@123456"),
        ("drone", "drone@nakshatech.com", "Drone@123"),
    ]
    for role, email, password in accounts:
        login(client, role, email, password)


def test_it_dashboard_is_seeded_from_company_workbook(client: TestClient) -> None:
    headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    response = client.get("/api/dashboard/it", headers=headers)
    assert response.status_code == 200, response.text
    kpis = response.json()["kpis"]
    assert kpis["total"] == 183
    assert kpis["computers"] == 153
    assert kpis["laptops"] == 28
    assert kpis["smartphones"] == 2

    assets = client.get("/api/assets?limit=500", headers=headers)
    assert assets.status_code == 200
    assert len(assets.json()) == 183


def test_exact_company_excel_and_dashboard_exports(client: TestClient) -> None:
    headers = login(client, "it", "it@nakshatech.com", "IT@123456")

    asset_export = client.get("/api/reports/nakshatech-assets.xlsx", headers=headers)
    assert asset_export.status_code == 200, asset_export.text
    assert "NakshaTech Asset Details" in asset_export.headers["content-disposition"]
    workbook = load_workbook(BytesIO(asset_export.content), read_only=True)
    current_sheet = datetime.now().strftime("%B %Y")
    assert workbook.sheetnames[0] == current_sheet
    sheet = workbook[current_sheet]
    assert [sheet.cell(1, column).value for column in range(1, 9)] == [
        "SL", "USED BY", "WS No", "DEPARTMENT", "cpu", "MONITOR", "MOUSE", "KB"
    ]

    dashboard_export = client.get("/api/reports/dashboard.xlsx", headers=headers)
    assert dashboard_export.status_code == 200, dashboard_export.text
    dashboard = load_workbook(BytesIO(dashboard_export.content), read_only=True)
    assert "Dashboard Summary" in dashboard.sheetnames
    assert "Asset Register" in dashboard.sheetnames
    assert "Work Records" in dashboard.sheetnames
    assert "Replacement Records" not in dashboard.sheetnames
    assert "Data Quality" in dashboard.sheetnames

    replacement_export = client.get("/api/reports/replacement-history.xlsx", headers=headers)
    assert replacement_export.status_code == 200
    replacement_book = load_workbook(BytesIO(replacement_export.content), read_only=True)
    assert "Component Replacements" in replacement_book.sheetnames
    assert "Complete Asset Replacements" in replacement_book.sheetnames

def test_printer_import_dashboard_export_and_replacement_guard(client: TestClient) -> None:
    from app.core.config import settings

    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    management_headers = login(client, "management", settings.seed_management_email, settings.seed_management_password)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Printer Assets"
    sheet.append([
        "Asset ID", "Assigned User", "Brand", "Model", "Serial No.", "Connection",
        "Department", "Floor", "Status", "Remarks", "Last Updated",
    ])
    sheet.append(["PRN-QA-001", "Printer User", "Epson", "L4360", "QA-PRN-SERIAL-001", "WiFi/USB", "Finance", "3rd Floor", "Active", "", datetime(2026, 8, 5)])
    sheet.append(["PRN-QA-002", "", "Epson", "L3250", "", "LAN/USB", "HR", "3rd Floor", "Available", "Shared backup printer", datetime(2026, 8, 5)])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    imported = client.post(
        "/api/imports/printers.xlsx",
        headers=it_headers,
        files={
            "file": (
                "Printer_Asset_Register.xlsx",
                stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["created"] == 2
    assert result["updated"] == 0
    assert result["warning_count"] == 1
    assert result["error_count"] == 0

    printers = client.get("/api/assets?device_type=Printer&limit=100", headers=it_headers)
    assert printers.status_code == 200, printers.text
    printer_rows = {item["cpu_asset_tag"]: item for item in printers.json()}
    assert {"PRN-QA-001", "PRN-QA-002"}.issubset(printer_rows)
    assigned_printer = printer_rows["PRN-QA-001"]
    available_printer = printer_rows["PRN-QA-002"]
    assert assigned_printer["brand"] == "Epson"
    assert assigned_printer["model"] == "L4360"
    assert assigned_printer["serial_number"] == "QA-PRN-SERIAL-001"
    assert assigned_printer["connection_type"] == "WiFi/USB"
    assert assigned_printer["location"] == "3rd Floor"
    assert available_printer["department"] == "HR"
    assert available_printer["status"] == "available"

    dashboard = client.get("/api/dashboard/it", headers=it_headers)
    assert dashboard.status_code == 200, dashboard.text
    assert dashboard.json()["kpis"]["printers"] >= 2

    current_month = datetime.now().strftime("%Y-%m")
    printer_export = client.get(f"/api/reports/printers.xlsx?month={current_month}", headers=it_headers)
    assert printer_export.status_code == 200, printer_export.text
    exported = load_workbook(BytesIO(printer_export.content), read_only=True, data_only=True)
    printer_sheet = exported["Printer Assets"]
    assert [printer_sheet.cell(1, column).value for column in range(1, 12)] == [
        "Asset ID", "Assigned User", "Brand", "Model", "Serial No.", "Connection",
        "Department", "Floor", "Status", "Remarks", "Last Updated",
    ]
    exported_rows = {printer_sheet.cell(row, 1).value for row in range(2, printer_sheet.max_row + 1)}
    assert {"PRN-QA-001", "PRN-QA-002"}.issubset(exported_rows)
    exported.close()

    non_printer = next(
        item for item in client.get("/api/assets?status=available&limit=1000", headers=it_headers).json()
        if item["device_type"] != "Printer"
    )
    mismatch = client.post(
        "/api/replacements",
        headers=it_headers,
        json={
            "old_asset_id": assigned_printer["id"],
            "new_asset_id": non_printer["id"],
            "reason": "Printer replacement type validation",
            "damage_category": "technical_failure",
            "inspection_finding": "Printer requires full replacement",
            "final_action": "replacement_pending",
        },
    )
    assert mismatch.status_code == 400
    assert "same device type" in mismatch.json()["detail"]

    replacement = client.post(
        "/api/replacements",
        headers=it_headers,
        json={
            "old_asset_id": assigned_printer["id"],
            "reason": "Printer is beyond economical repair",
            "damage_category": "technical_failure",
            "inspection_finding": "Printer main board failed",
            "final_action": "replacement_pending",
        },
    )
    assert replacement.status_code == 200, replacement.text
    approved = client.patch(
        f"/api/replacements/{replacement.json()['id']}",
        headers=management_headers,
        json={
            "approval_status": "approved",
            "new_asset_id": available_printer["id"],
            "final_action": "replace_and_retire",
            "remarks": "Approved printer replacement integration test",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["new_asset_code"] == available_printer["asset_code"]



def test_external_hdd_import_dashboard_drawer_export_and_audit(client: TestClient) -> None:
    from app.core.config import settings

    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    primary_total_before = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "External HDD Asset Register"
    sheet.append([
        "Asset ID", "Brand", "Capacity", "Serial No.", "Ownership", "Department",
        "Client Name", "Project ID", "Current Holder", "Status", "Remarks",
    ])
    sheet.append(["HDD-QA-001", "Seagate", "2 TB", "QA-HDD-SERIAL-001", "NakshaTech", "Mapping", "-", "PRJ-QA-001", "Mapping Dept", "In Use", "Internal project backup"])
    sheet.append(["HDD-QA-002", "WD", "4 TB", "QA-HDD-SERIAL-002", "Client", "LiDAR", "QA Client", "PRJ-QA-002", "Client", "Returned", "Client-owned project drive"])
    sheet.append(["HDD-QA-003", "Toshiba", "1 TB", "QA-HDD-SERIAL-003", "NakshaTech", "Drone", "QA Consultants", "PRJ-QA-003", "Client", "Issued", "Temporary field delivery"])
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    imported = client.post(
        "/api/imports/external-hdds.xlsx",
        headers=it_headers,
        files={
            "file": (
                "External_HDD_Asset_Register.xlsx",
                stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json()["created"] == 3
    assert imported.json()["updated"] == 0
    assert imported.json()["error_count"] == 0

    assets = client.get("/api/assets?device_type=External%20HDD&limit=100", headers=it_headers)
    assert assets.status_code == 200, assets.text
    rows = {item["cpu_asset_tag"]: item for item in assets.json()}
    assert {"HDD-QA-001", "HDD-QA-002", "HDD-QA-003"}.issubset(rows)
    first = rows["HDD-QA-001"]
    assert first["device_type"] == "External HDD"
    assert first["capacity"] == "2 TB"
    assert first["ownership"] == "NakshaTech"
    assert first["project_id"] == "PRJ-QA-001"
    assert first["current_holder"] == "Mapping Dept"
    assert first["status"] == "in_use"

    dashboard = client.get("/api/dashboard/it", headers=it_headers)
    assert dashboard.status_code == 200, dashboard.text
    dashboard_data = dashboard.json()
    assert dashboard_data["kpis"]["external_hdds"] >= 3
    assert dashboard_data["kpis"]["total"] == primary_total_before
    assert all(item["name"] != "External HDD" for item in dashboard_data["device_distribution"])

    current_month = datetime.now().strftime("%Y-%m")
    primary_drilldown = client.get(
        f"/api/dashboard/it/assets?month={current_month}&scope=primary&page=1&page_size=100",
        headers=it_headers,
    )
    assert primary_drilldown.status_code == 200, primary_drilldown.text
    assert primary_drilldown.json()["scope_total"] == dashboard_data["kpis"]["total"]
    assert all(asset["device_type"] != "External HDD" for asset in primary_drilldown.json()["assets"])

    drilldown = client.get(
        f"/api/dashboard/it/assets?month={current_month}&scope=device&scope_value=External%20HDD&ownership=Client&page=1&page_size=100",
        headers=it_headers,
    )
    assert drilldown.status_code == 200, drilldown.text
    assert drilldown.json()["filtered_total"] == 1
    assert drilldown.json()["summary"]["client_owned"] >= 1
    assert drilldown.json()["assets"][0]["cpu_asset_tag"] == "HDD-QA-002"

    exported = client.get(f"/api/reports/external-hdds.xlsx?month={current_month}", headers=it_headers)
    assert exported.status_code == 200, exported.text
    report = load_workbook(BytesIO(exported.content), read_only=True, data_only=True)
    external_sheet = report["External HDD Asset Register"]
    assert [external_sheet.cell(1, column).value for column in range(1, 12)] == [
        "Asset ID", "Brand", "Capacity", "Serial No.", "Ownership", "Department",
        "Client Name", "Project ID", "Current Holder", "Status", "Remarks",
    ]
    exported_ids = {external_sheet.cell(row, 1).value for row in range(2, external_sheet.max_row + 1)}
    assert {"HDD-QA-001", "HDD-QA-002", "HDD-QA-003"}.issubset(exported_ids)
    report.close()

    # Keep this test self-contained: create its own printer before finalizing
    # the previous-month snapshot instead of depending on another test's data.
    printer_workbook = Workbook()
    printer_sheet = printer_workbook.active
    printer_sheet.title = "Printer Assets"
    printer_sheet.append([
        "Asset ID", "Assigned User", "Brand", "Model", "Serial No.", "Connection",
        "Department", "Floor", "Status", "Remarks", "Last Updated",
    ])
    printer_sheet.append([
        "PRN-MONTH-QA-001", "Monthly Test User", "Epson", "L3250",
        "QA-MONTH-PRINTER-001", "LAN/USB", "IT", "Head Office",
        "Active", "Monthly printer snapshot test", datetime.now(),
    ])
    printer_stream = BytesIO()
    printer_workbook.save(printer_stream)
    printer_workbook.close()

    printer_imported = client.post(
        "/api/imports/printers.xlsx",
        headers=it_headers,
        files={
            "file": (
                "Monthly_Printer_Asset_Register.xlsx",
                printer_stream.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert printer_imported.status_code == 200, printer_imported.text
    assert printer_imported.json()["created"] == 1
    primary_total_after_printer = client.get(
        "/api/dashboard/it",
        headers=it_headers,
    ).json()["kpis"]["total"]

    assert primary_total_after_printer == primary_total_before + 1

    current_start = datetime.now().replace(day=1)
    if current_start.month == 1:
        previous_start = current_start.replace(year=current_start.year - 1, month=12)
    else:
        previous_start = current_start.replace(month=current_start.month - 1)
    previous_month = previous_start.strftime("%Y-%m")
    from app.core.database import SessionLocal
    from app.services.monthly_snapshot_service import finalize_month_snapshot, parse_month_key

    with SessionLocal() as snapshot_db:
        snapshot = finalize_month_snapshot(
            snapshot_db,
            parse_month_key(previous_month),
            finalized_by="automated-test",
            source="test",
            replace_existing=True,
        )
        assert snapshot.status == "finalized"

    previous_printers = client.get(f"/api/reports/printers.xlsx?month={previous_month}", headers=it_headers)
    assert previous_printers.status_code == 200, previous_printers.text
    previous_printer_book = load_workbook(BytesIO(previous_printers.content), read_only=True, data_only=True)
    previous_printer_ids = {
        previous_printer_book["Printer Assets"].cell(row, 1).value
        for row in range(2, previous_printer_book["Printer Assets"].max_row + 1)
    }
    assert "PRN-MONTH-QA-001" in previous_printer_ids
    previous_printer_book.close()

    updated = client.patch(
        f"/api/assets/{first['id']}",
        headers=it_headers,
        json={
            "reporting_month": current_month,
            "current_holder": "QA Client",
            "client_name": "QA Client",
            "project_id": "PRJ-QA-004",
            "status": "issued",
            "audit_reason": "External HDD issued for project delivery",
            "audit_remarks": "Holder and project movement test",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["current_holder"] == "QA Client"
    assert updated.json()["status"] == "issued"

    detail = client.get(f"/api/assets/{first['id']}", headers=it_headers)
    assert detail.status_code == 200, detail.text
    assert any(
        history.get("change_type") == "full_edit"
        and "External HDD issued for project delivery" in (history.get("reason") or "")
        for history in detail.json()["history"]
    )

    previous_hdds = client.get(f"/api/reports/external-hdds.xlsx?month={previous_month}", headers=it_headers)
    assert previous_hdds.status_code == 200, previous_hdds.text
    previous_hdd_book = load_workbook(BytesIO(previous_hdds.content), read_only=True, data_only=True)
    previous_hdd_sheet = previous_hdd_book["External HDD Asset Register"]
    previous_hdd_rows = {
        previous_hdd_sheet.cell(row, 1).value: {
            "project": previous_hdd_sheet.cell(row, 8).value,
            "holder": previous_hdd_sheet.cell(row, 9).value,
            "status": previous_hdd_sheet.cell(row, 10).value,
        }
        for row in range(2, previous_hdd_sheet.max_row + 1)
    }
    assert previous_hdd_rows["HDD-QA-001"] == {
        "project": "PRJ-QA-001",
        "holder": "Mapping Dept",
        "status": "In Use",
    }
    previous_hdd_book.close()

    previous_dashboard = client.get(f"/api/dashboard/it?month={previous_month}", headers=it_headers)
    assert previous_dashboard.status_code == 200, previous_dashboard.text
    assert previous_dashboard.json()["kpis"]["total"] == primary_total_after_printer
    assert previous_dashboard.json()["kpis"]["external_hdds"] >= 3


def test_work_and_replacement_workflows(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    management_headers = login(client, "management", "management@nakshatech.com", "Manager@123")
    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    old_asset = client.get("/api/assets?status=assigned&limit=1", headers=it_headers).json()[0]
    new_asset = client.get("/api/assets?status=available&limit=1", headers=it_headers).json()[0]

    work = client.post(
        "/api/work-records",
        headers=it_headers,
        json={
            "module": "it",
            "asset_id": old_asset["id"],
            "title": "Inspect non-working system",
            "work_type": "Hardware inspection",
            "issue_description": "System does not power on",
            "priority": "high",
            "technician": "IT Department",
            "details": "Created by automated integration test",
        },
    )
    assert work.status_code == 200, work.text
    assert work.json()["status"] == "open"
    work_id = work.json()["id"]

    invalid_direct_complete = client.patch(
        f"/api/work-records/{work_id}",
        headers=it_headers,
        json={"status": "completed"},
    )
    assert invalid_direct_complete.status_code == 409

    started = client.patch(f"/api/work-records/{work_id}", headers=it_headers, json={"status": "in_progress"})
    assert started.status_code == 200, started.text
    completed = client.patch(
        f"/api/work-records/{work_id}",
        headers=it_headers,
        json={"status": "completed", "resolution": "Inspection completed"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "completed"
    assert completed.json()["approval_status"] == "pending"
    assert completed.json()["submitted_by_role"] == "it"
    assert completed.json()["submitted_at"] is not None
    work_code = completed.json()["work_code"]
    pending_notice = _approval_notification(
        client,
        management_headers,
        event_type="approval.it_work.submitted",
        record_code=work_code,
        target_prefix="/work",
    )
    assert pending_notice["is_read"] is False

    locked_after_submit = client.patch(
        f"/api/work-records/{work_id}",
        headers=it_headers,
        json={"resolution": "Attempted edit after submission"},
    )
    assert locked_after_submit.status_code == 409

    forged_generic_approval = client.patch(
        f"/api/work-records/{work_id}",
        headers=management_headers,
        json={"status": "closed", "approval_status": "approved"},
    )
    assert forged_generic_approval.status_code in {400, 403}

    forbidden_it_decision = client.post(
        f"/api/work-records/{work_id}/decision",
        headers=it_headers,
        json={"action": "approve"},
    )
    assert forbidden_it_decision.status_code == 403
    forbidden_admin_decision = client.post(
        f"/api/work-records/{work_id}/decision",
        headers=admin_headers,
        json={"action": "approve"},
    )
    assert forbidden_admin_decision.status_code == 403

    closed = client.post(
        f"/api/work-records/{work_id}/decision",
        headers=management_headers,
        json={"action": "approve", "comments": "Inspection verified by Management"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["approval_status"] == "approved"
    assert closed.json()["approved_by_role"] == "management"
    assert closed.json()["approval_comments"] == "Inspection verified by Management"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.it_work.approved",
        record_code=work_code,
        target_prefix="/work",
    )

    duplicate_decision = client.post(
        f"/api/work-records/{work_id}/decision",
        headers=management_headers,
        json={"action": "approve"},
    )
    assert duplicate_decision.status_code == 409

    returned_work = client.post(
        "/api/work-records",
        headers=it_headers,
        json={
            "module": "it",
            "asset_id": old_asset["id"],
            "title": "Validate returned approval cycle",
            "work_type": "Inspection",
            "issue_description": "Approval return regression test",
            "priority": "medium",
            "technician": "IT Department",
        },
    )
    assert returned_work.status_code == 200, returned_work.text
    returned_work_id = returned_work.json()["id"]
    assert client.patch(f"/api/work-records/{returned_work_id}", headers=it_headers, json={"status": "in_progress"}).status_code == 200
    assert client.patch(f"/api/work-records/{returned_work_id}", headers=it_headers, json={"status": "completed"}).status_code == 200
    missing_return_comment = client.post(
        f"/api/work-records/{returned_work_id}/decision",
        headers=management_headers,
        json={"action": "return"},
    )
    assert missing_return_comment.status_code == 400
    returned = client.post(
        f"/api/work-records/{returned_work_id}/decision",
        headers=management_headers,
        json={"action": "return", "comments": "Add the final verification result"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "in_progress"
    assert returned.json()["approval_status"] == "returned"
    returned_work_code = returned.json()["work_code"]
    _approval_notification(
        client,
        it_headers,
        event_type="approval.it_work.returned",
        record_code=returned_work_code,
        target_prefix="/work",
    )
    resubmitted_work = client.patch(
        f"/api/work-records/{returned_work_id}",
        headers=it_headers,
        json={"status": "completed", "resolution": "Verification added"},
    )
    assert resubmitted_work.status_code == 200, resubmitted_work.text
    assert resubmitted_work.json()["approval_status"] == "pending"
    _approval_notification(
        client,
        management_headers,
        event_type="approval.it_work.resubmitted",
        record_code=returned_work_code,
        target_prefix="/work",
    )

    replacement = client.post(
        "/api/replacements",
        headers=it_headers,
        json={
            "old_asset_id": old_asset["id"],
            "reason": "Beyond economical repair",
            "damage_category": "Technical Failure",
            "inspection_finding": "Replacement recommended after inspection",
            "final_action": "replacement_pending",
        },
    )
    assert replacement.status_code == 200, replacement.text
    replacement_id = replacement.json()["id"]
    replacement_code = replacement.json()["replacement_code"]
    assert replacement.json()["approval_status"] == "pending"
    _approval_notification(
        client,
        management_headers,
        event_type="approval.replacement.submitted",
        record_code=replacement_code,
        target_prefix="/replacements",
    )

    duplicate_replacement = client.post(
        "/api/replacements",
        headers=it_headers,
        json={
            "old_asset_id": old_asset["id"],
            "reason": "Duplicate request must be blocked",
            "damage_category": "technical_failure",
        },
    )
    assert duplicate_replacement.status_code == 409

    forbidden_replacement_admin = client.patch(
        f"/api/replacements/{replacement_id}",
        headers=admin_headers,
        json={
            "approval_status": "approved",
            "new_asset_id": new_asset["id"],
            "final_action": "replace_and_retire",
        },
    )
    assert forbidden_replacement_admin.status_code == 403

    missing_replacement_return_comment = client.patch(
        f"/api/replacements/{replacement_id}",
        headers=management_headers,
        json={"approval_status": "returned"},
    )
    assert missing_replacement_return_comment.status_code == 400

    returned_replacement = client.patch(
        f"/api/replacements/{replacement_id}",
        headers=management_headers,
        json={
            "approval_status": "returned",
            "remarks": "Clarify the inspection finding before approval",
        },
    )
    assert returned_replacement.status_code == 200, returned_replacement.text
    assert returned_replacement.json()["approval_status"] == "returned"
    assert returned_replacement.json()["decision_remarks"] == "Clarify the inspection finding before approval"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.replacement.returned",
        record_code=replacement_code,
        target_prefix="/replacements",
    )

    resubmitted_replacement = client.put(
        f"/api/replacements/{replacement_id}/resubmit",
        headers=it_headers,
        json={
            "reason": "Beyond economical repair after second verification",
            "damage_category": "technical_failure",
            "inspection_finding": "Main board confirmed failed and repair is uneconomical",
            "final_action": "replacement_pending",
        },
    )
    assert resubmitted_replacement.status_code == 200, resubmitted_replacement.text
    assert resubmitted_replacement.json()["approval_status"] == "pending"
    assert resubmitted_replacement.json()["approved_by"] is None
    _approval_notification(
        client,
        management_headers,
        event_type="approval.replacement.resubmitted",
        record_code=replacement_code,
        target_prefix="/replacements",
    )

    approved = client.patch(
        f"/api/replacements/{replacement_id}",
        headers=management_headers,
        json={
            "approval_status": "approved",
            "new_asset_id": new_asset["id"],
            "final_action": "replace_and_retire",
            "remarks": "Approved by management integration test",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_status"] == "approved"
    assert approved.json()["new_asset_code"] == new_asset["asset_code"]
    assert approved.json()["approved_by_role"] == "management"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.replacement.approved",
        record_code=replacement_code,
        target_prefix="/replacements",
    )

    duplicate_replacement_decision = client.patch(
        f"/api/replacements/{replacement_id}",
        headers=management_headers,
        json={"approval_status": "rejected", "remarks": "Must not overwrite approval"},
    )
    assert duplicate_replacement_decision.status_code == 409

    assigned_candidates = client.get("/api/assets?status=assigned&limit=10", headers=it_headers).json()
    reject_old_asset = next(item for item in assigned_candidates if item["id"] != old_asset["id"])
    reject_request = client.post(
        "/api/replacements",
        headers=it_headers,
        json={
            "old_asset_id": reject_old_asset["id"],
            "reason": "Replacement rejection regression test",
            "damage_category": "technical_failure",
            "inspection_finding": "Repair remains viable",
            "final_action": "replacement_pending",
        },
    )
    assert reject_request.status_code == 200, reject_request.text
    reject_request_id = reject_request.json()["id"]
    reject_without_remarks = client.patch(
        f"/api/replacements/{reject_request_id}",
        headers=management_headers,
        json={"approval_status": "rejected"},
    )
    assert reject_without_remarks.status_code == 400
    rejected_replacement = client.patch(
        f"/api/replacements/{reject_request_id}",
        headers=management_headers,
        json={"approval_status": "rejected", "remarks": "Repair the existing asset instead"},
    )
    assert rejected_replacement.status_code == 200, rejected_replacement.text
    assert rejected_replacement.json()["approval_status"] == "rejected"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.replacement.rejected",
        record_code=reject_request.json()["replacement_code"],
        target_prefix="/replacements",
    )
    reject_asset_after = client.get(f"/api/assets/{reject_old_asset['id']}", headers=it_headers)
    assert reject_asset_after.status_code == 200
    assert reject_asset_after.json()["status"] == "assigned"

    with SessionLocal() as db:
        work_actions = db.scalars(
            select(ApprovalDecisionHistory.action)
            .where(
                ApprovalDecisionHistory.workflow_type == "it_work",
                ApprovalDecisionHistory.record_id == returned_work_id,
            )
            .order_by(ApprovalDecisionHistory.id.asc())
        ).all()
        replacement_actions = db.scalars(
            select(ApprovalDecisionHistory.action)
            .where(
                ApprovalDecisionHistory.workflow_type == "asset_replacement",
                ApprovalDecisionHistory.record_id == replacement_id,
            )
            .order_by(ApprovalDecisionHistory.id.asc())
        ).all()
    assert work_actions == ["submitted", "returned", "resubmitted"]
    assert replacement_actions == ["submitted", "returned", "resubmitted", "approved"]


def test_purchase_permission_approval_conversion_and_excel(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    management_headers = login(client, "management", "management@nakshatech.com", "Manager@123")
    month = datetime.now().strftime("%Y-%m")

    created = client.post(
        "/api/it-activity/purchase-requests",
        headers=it_headers,
        json={
            "reporting_month": month,
            "requesting_department": "Software",
            "requested_employee": "QA Software Employee",
            "item_type": "hardware",
            "item_name": "AI Development Workstation",
            "item_description": "High performance workstation for model development",
            "quantity": 2,
            "estimated_unit_price": 125000,
            "business_reason": "Required for approved AI development workload",
            "priority": "high",
            "it_remarks": "Automated purchase approval test",
        },
    )
    assert created.status_code == 200, created.text
    request = created.json()
    assert request["status"] == "pending_approval"
    assert request["estimated_total_amount"] == 250000
    assert request["histories"][0]["action"] == "submitted"
    _approval_notification(
        client,
        management_headers,
        event_type="approval.purchase_request.submitted",
        record_code=request["request_code"],
        target_prefix="/it/purchase-requests",
    )

    direct_purchase = client.post(
        "/api/it-activity/purchases",
        headers=it_headers,
        json={
            "reporting_month": month,
            "purchase_date": datetime.now().date().isoformat(),
            "supplier_name": "QA Supplier",
            "item_description": "Direct purchase must be blocked",
            "quantity": 1,
            "total_price": 1000,
        },
    )
    assert direct_purchase.status_code == 400
    assert "approved purchase request" in direct_purchase.json()["detail"].lower()

    forbidden_decision = client.post(
        f"/api/it-activity/purchase-requests/{request['id']}/decision",
        headers=it_headers,
        json={"action": "approve"},
    )
    assert forbidden_decision.status_code == 403

    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    forbidden_admin_decision = client.post(
        f"/api/it-activity/purchase-requests/{request['id']}/decision",
        headers=admin_headers,
        json={"action": "approve"},
    )
    assert forbidden_admin_decision.status_code == 403

    approved = client.post(
        f"/api/it-activity/purchase-requests/{request['id']}/decision",
        headers=management_headers,
        json={
            "action": "approve",
            "approved_amount": 240000,
            "management_remarks": "Approved within the sanctioned budget",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
    assert approved.json()["approved_amount"] == 240000
    assert approved.json()["decided_by_role"] == "management"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.purchase_request.approved",
        record_code=request["request_code"],
        target_prefix="/it/purchase-requests",
    )
    with SessionLocal() as db:
        purchase_approval_actions = db.scalars(
            select(ApprovalDecisionHistory.action)
            .where(
                ApprovalDecisionHistory.workflow_type == "purchase_request",
                ApprovalDecisionHistory.record_id == request["id"],
            )
            .order_by(ApprovalDecisionHistory.id.asc())
        ).all()
    assert purchase_approval_actions == ["submitted", "approved"]

    purchase = client.post(
        "/api/it-activity/purchases",
        headers=it_headers,
        json={
            "reporting_month": month,
            "purchase_request_id": request["id"],
            "purchase_date": datetime.now().date().isoformat(),
            "po_number": "QA-PO-APPROVAL-001",
            "supplier_name": "QA Supplier",
            "item_description": "AI Development Workstation",
            "quantity": 2,
            "unit_price": 120000,
            "total_price": 240000,
            "inspection_status": "Pending",
        },
    )
    assert purchase.status_code == 200, purchase.text
    assert purchase.json()["purchase_request_id"] == request["id"]

    completed = client.get(
        f"/api/it-activity/purchase-requests/{request['id']}",
        headers=management_headers,
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "purchase_completed"
    assert completed.json()["purchase_code"] == purchase.json()["purchase_code"]
    assert completed.json()["actual_purchase_amount"] == 240000
    assert completed.json()["histories"][-1]["action"] == "purchase_completed"

    duplicate = client.post(
        "/api/it-activity/purchases",
        headers=it_headers,
        json={
            "reporting_month": month,
            "purchase_request_id": request["id"],
            "purchase_date": datetime.now().date().isoformat(),
            "supplier_name": "Another Supplier",
            "item_description": "Duplicate conversion",
            "quantity": 1,
            "total_price": 1,
        },
    )
    assert duplicate.status_code == 409

    sent_back_request = client.post(
        "/api/it-activity/purchase-requests",
        headers=it_headers,
        json={
            "reporting_month": month,
            "requesting_department": "Civil",
            "requested_employee": "QA Civil Employee",
            "item_type": "software",
            "item_name": "GIS Desktop License",
            "quantity": 1,
            "estimated_total_amount": 50000,
            "business_reason": "Required for project delivery",
            "priority": "medium",
        },
    )
    assert sent_back_request.status_code == 200
    sent_back_id = sent_back_request.json()["id"]

    missing_remarks = client.post(
        f"/api/it-activity/purchase-requests/{sent_back_id}/decision",
        headers=management_headers,
        json={"action": "send_back"},
    )
    assert missing_remarks.status_code == 400

    sent_back = client.post(
        f"/api/it-activity/purchase-requests/{sent_back_id}/decision",
        headers=management_headers,
        json={"action": "send_back", "management_remarks": "Clarify the license duration"},
    )
    assert sent_back.status_code == 200
    assert sent_back.json()["status"] == "sent_back"
    sent_back_code = sent_back.json()["request_code"]
    _approval_notification(
        client,
        it_headers,
        event_type="approval.purchase_request.sent_back",
        record_code=sent_back_code,
        target_prefix="/it/purchase-requests",
    )

    resubmitted = client.put(
        f"/api/it-activity/purchase-requests/{sent_back_id}/resubmit",
        headers=it_headers,
        json={
            "reporting_month": month,
            "requesting_department": "Civil",
            "requested_employee": "QA Civil Employee",
            "item_type": "software",
            "item_name": "GIS Desktop License - Annual",
            "quantity": 1,
            "estimated_total_amount": 50000,
            "business_reason": "Annual license required for project delivery",
            "priority": "medium",
            "it_remarks": "License duration clarified as one year",
        },
    )
    assert resubmitted.status_code == 200, resubmitted.text
    assert resubmitted.json()["status"] == "pending_approval"
    assert resubmitted.json()["histories"][-1]["action"] == "resubmitted"
    _approval_notification(
        client,
        management_headers,
        event_type="approval.purchase_request.resubmitted",
        record_code=sent_back_code,
        target_prefix="/it/purchase-requests",
    )

    rejected_request = client.post(
        "/api/it-activity/purchase-requests",
        headers=it_headers,
        json={
            "reporting_month": month,
            "requesting_department": "IT",
            "requested_employee": "QA IT Employee",
            "item_type": "hardware",
            "item_name": "Unnecessary Test Hardware",
            "quantity": 1,
            "estimated_total_amount": 1000,
            "business_reason": "Regression test for management rejection",
            "priority": "low",
        },
    )
    assert rejected_request.status_code == 200, rejected_request.text
    rejected_id = rejected_request.json()["id"]
    purchase_reject_without_remarks = client.post(
        f"/api/it-activity/purchase-requests/{rejected_id}/decision",
        headers=management_headers,
        json={"action": "reject"},
    )
    assert purchase_reject_without_remarks.status_code == 400
    purchase_rejected = client.post(
        f"/api/it-activity/purchase-requests/{rejected_id}/decision",
        headers=management_headers,
        json={"action": "reject", "management_remarks": "Business justification is insufficient"},
    )
    assert purchase_rejected.status_code == 200, purchase_rejected.text
    assert purchase_rejected.json()["status"] == "rejected"
    _approval_notification(
        client,
        it_headers,
        event_type="approval.purchase_request.rejected",
        record_code=rejected_request.json()["request_code"],
        target_prefix="/it/purchase-requests",
    )

    summary = client.get(
        f"/api/it-activity/purchase-requests/summary?month={month}",
        headers=management_headers,
    )
    assert summary.status_code == 200
    assert summary.json()["purchase_completed"] >= 1

    export = client.get(
        f"/api/it-activity/purchase-requests.xlsx?month={month}",
        headers=management_headers,
    )
    assert export.status_code == 200, export.text
    workbook = load_workbook(BytesIO(export.content), read_only=True)
    assert "Approval Summary" in workbook.sheetnames
    assert "Purchase Requests" in workbook.sheetnames
    assert "Approval History" in workbook.sheetnames


def test_role_permissions(client: TestClient) -> None:
    drone_headers = login(client, "drone", "drone@nakshatech.com", "Drone@123")
    assert client.get("/api/drones", headers=drone_headers).status_code == 200
    assert client.get("/api/dashboard/it", headers=drone_headers).status_code == 403


def test_manual_asset_validation_assignment_return_edit_and_cleanup(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    before_total = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]

    invalid_available = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Computer",
            "status": "available",
            "used_by": "QA Test Employee",
            "department": "IT",
            "cpu_asset_tag": "QA-INVALID-AVAILABLE",
            "system_name": "QA-INVALID-AVAILABLE",
        },
    )
    assert invalid_available.status_code == 400
    assert "cannot have an employee" in invalid_available.json()["detail"]

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Computer",
            "status": "available",
            "cpu_asset_tag": "QA-PC-UNIQUE-001",
            "system_name": "QA-PC-UNIQUE-001",
            "processor": "Intel Core i5",
            "memory_gb": "16 GB",
            "ssd": "512 GB",
            "hdd": "1 TB",
            "monitor_asset_tags": "QA-MON-001",
            "mouse_asset_tag": "QA-MOUSE-001",
            "keyboard_asset_tag": "QA-KB-001",
            "network_type": "STATIC",
            "ip_address": "192.168.250.10",
            "mac_address": "AA:BB:CC:DD:EE:01",
            "operating_system": "Windows 11 Pro",
            "antivirus": "Enabled",
            "graphics_card": "Integrated",
            "price": 50000,
            "location": "Head Office",
            "remarks": "Automated QA lifecycle test",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()
    assert asset["status"] == "available"
    assert asset["performed_by"] == "IT Department"

    after_create = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]
    assert after_create["total"] == before_total + 1

    duplicate = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Computer",
            "status": "available",
            "cpu_asset_tag": "qa-pc-unique-001",
            "system_name": "QA-PC-DUPLICATE",
        },
    )
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]

    assigned = client.post(
        f"/api/assets/{asset['id']}/assign",
        headers=it_headers,
        json={
            "used_by": "QA Test Employee",
            "department": "IT",
            "workstation_no": "QA-WS-01",
            "location": "3rd Floor",
            "work_mode": "office",
            "remarks": "Assignment test",
        },
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["status"] == "assigned"
    assert assigned.json()["used_by"] == "QA Test Employee"

    edited = client.patch(
        f"/api/assets/{asset['id']}",
        headers=it_headers,
        json={
            "monitor_asset_tags": "QA-MON-NEW-001",
            "graphics_card": "NVIDIA Test GPU",
            "approved_by": "QA Management",
            "audit_reason": "QA asset edit verification",
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["monitor_asset_tags"] == "QA-MON-NEW-001"

    returned = client.post(
        f"/api/assets/{asset['id']}/return",
        headers=it_headers,
        json={
            "final_status": "available",
            "condition": "working",
            "all_components_returned": True,
            "remarks": "Return test",
        },
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["status"] == "available"
    assert returned.json()["used_by"] is None
    assert returned.json()["workstation_no"] is None

    export = client.get("/api/reports/nakshatech-assets.xlsx", headers=it_headers)
    assert export.status_code == 200
    exported_book = load_workbook(BytesIO(export.content), read_only=True, data_only=True)
    exported_sheet = exported_book[exported_book.sheetnames[0]]
    qa_rows = [
        row for row in exported_sheet.iter_rows(min_row=2, values_only=True)
        if len(row) >= 5 and row[4] == "QA-PC-UNIQUE-001"
    ]
    assert len(qa_rows) == 1
    assert qa_rows[0][5] == "QA-MON-NEW-001"
    assert qa_rows[0][14] == "192.168.250.10"
    assert qa_rows[0][15] == "AA:BB:CC:DD:EE:01"
    assert qa_rows[0][20] == "IT Department"

    detail = client.get(f"/api/assets/{asset['id']}", headers=it_headers)
    assert detail.status_code == 200
    actions = [item["action"] for item in detail.json()["history"]]
    assert "Asset created" in actions
    assert "Asset assigned / transferred" in actions
    assert "Asset details updated" in actions
    assert "Asset returned" in actions
    assert detail.json()["can_delete_test_record"] is True

    deleted = client.delete(f"/api/assets/{asset['id']}", headers=it_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/assets/{asset['id']}", headers=it_headers).status_code == 404


def test_asset_edit_allows_optional_monthly_text_and_preserves_audit(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    cpu_tag = f"QA-OPTIONAL-AUDIT-{uuid.uuid4().hex[:8].upper()}"
    office_location = (
        "Naksha Tech Pvt. Ltd., R.K. Chambers, 4th Floor, 5th Main, "
        "Chamarajpet, Bengaluru, Karnataka, India – 560018"
    )

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Laptop",
            "status": "available",
            "cpu_asset_tag": cpu_tag,
            "department": "Finance - Management",
            "location": "Head Office",
            "system_name": "QA-OPTIONAL-AUDIT-LAPTOP",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()

    edited = client.patch(
        f"/api/assets/{asset['id']}",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "location": office_location,
            "department": "Software Development",
        },
    )
    assert edited.status_code == 200, edited.text
    edited_asset = edited.json()
    assert edited_asset["cpu_asset_tag"] == cpu_tag
    assert edited_asset["location"] == office_location
    assert edited_asset["department"] == "Software Development"

    detail = client.get(f"/api/assets/{asset['id']}", headers=it_headers)
    assert detail.status_code == 200, detail.text
    edit_history = [
        item for item in detail.json()["history"]
        if item.get("change_type") == "full_edit"
    ]
    assert edit_history
    latest = edit_history[0]
    assert latest["reason"] is None
    assert latest["reporting_month"] == "2026-08"
    assert latest["field_count"] == 2
    assert '"location"' in latest["old_value"]
    assert '"department"' in latest["old_value"]
    assert '"location"' in latest["new_value"]
    assert '"department"' in latest["new_value"]

    deleted = client.delete(f"/api/assets/{asset['id']}", headers=it_headers)
    assert deleted.status_code == 204


def test_component_change_updates_live_register_and_separate_history_excel(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Computer",
            "status": "available",
            "cpu_asset_tag": "QA-COMPONENT-CPU-001",
            "workstation_no": "QA-NW-001",
            "system_name": "QA-COMPONENT-PC",
            "department": "IT",
            "mouse_asset_tag": None,
            "keyboard_asset_tag": "QA-KB-OLD-001",
            "monitor_asset_tags": "QA-MON-OLD-001, QA-MON-SECOND-001",
            "processor": "Intel Core i5",
            "memory_gb": "8 GB",
            "network_type": "DHCP",
            "location": "Head Office",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()
    assert asset["workstation_no"] == "QA-NW-001"

    mouse_change = client.post(
        "/api/component-replacements",
        headers=it_headers,
        json={
            "asset_id": asset["id"],
            "component_type": "Mouse",
            "new_value": "QA-MOUSE-NEW-001",
            "reason": "Old mouse tag was not previously recorded and mouse stopped working",
            "old_condition": "Not working",
            "technician": "IT Department",
            "replacement_date": "2026-07-30",
        },
    )
    assert mouse_change.status_code == 200, mouse_change.text
    mouse_record = mouse_change.json()
    assert mouse_record["old_value"] == "Not Previously Recorded"
    assert mouse_record["new_value"] == "QA-MOUSE-NEW-001"
    assert mouse_record["cpu_asset_tag"] == "QA-COMPONENT-CPU-001"
    assert mouse_record["workstation_no"] == "QA-NW-001"
    assert mouse_record["work_code"].startswith("ITW-")

    keyboard_change = client.post(
        "/api/component-replacements",
        headers=it_headers,
        json={
            "asset_id": asset["id"],
            "component_type": "Keyboard",
            "new_value": "QA-KB-NEW-001",
            "reason": "Keys not working",
            "old_condition": "Damaged",
        },
    )
    assert keyboard_change.status_code == 200, keyboard_change.text
    assert keyboard_change.json()["old_value"] == "QA-KB-OLD-001"

    monitor_change = client.post(
        "/api/component-replacements",
        headers=it_headers,
        json={
            "asset_id": asset["id"],
            "component_type": "Monitor",
            "old_value": "QA-MON-OLD-001",
            "new_value": "QA-MON-NEW-001",
            "reason": "Display panel failed",
        },
    )
    assert monitor_change.status_code == 200, monitor_change.text

    memory_change = client.post(
        "/api/component-replacements",
        headers=it_headers,
        json={
            "asset_id": asset["id"],
            "component_type": "Memory",
            "new_value": "16 GB",
            "reason": "RAM upgrade",
        },
    )
    assert memory_change.status_code == 200, memory_change.text
    assert memory_change.json()["old_value"] == "8 GB"

    refreshed = client.get(f"/api/assets/{asset['id']}", headers=it_headers)
    assert refreshed.status_code == 200
    detail = refreshed.json()
    assert detail["mouse_asset_tag"] == "QA-MOUSE-NEW-001"
    assert detail["keyboard_asset_tag"] == "QA-KB-NEW-001"
    assert detail["monitor_asset_tags"] == "QA-MON-NEW-001, QA-MON-SECOND-001"
    assert detail["memory_gb"] == "16 GB"
    assert len(detail["component_replacements"]) == 4
    assert any(item["action"] == "Component / configuration changed" for item in detail["history"])

    asset_export = client.get("/api/reports/nakshatech-assets.xlsx", headers=it_headers)
    assert asset_export.status_code == 200
    asset_book = load_workbook(BytesIO(asset_export.content), read_only=True, data_only=True)
    asset_sheet = asset_book[asset_book.sheetnames[0]]
    rows = [row for row in asset_sheet.iter_rows(min_row=2, values_only=True) if len(row) >= 8 and row[4] == "QA-COMPONENT-CPU-001"]
    assert len(rows) == 1
    assert rows[0][5] == "QA-MON-NEW-001, QA-MON-SECOND-001"
    assert rows[0][6] == "QA-MOUSE-NEW-001"
    assert rows[0][7] == "QA-KB-NEW-001"
    assert rows[0][11] == "16 GB"

    history_export = client.get("/api/reports/replacement-history.xlsx", headers=it_headers)
    assert history_export.status_code == 200, history_export.text
    history_book = load_workbook(BytesIO(history_export.content), read_only=True, data_only=True)
    assert history_book.sheetnames == [
        "Replacement Summary", "Component Replacements", "Complete Asset Replacements"
    ]
    component_sheet = history_book["Component Replacements"]
    component_rows = list(component_sheet.iter_rows(min_row=2, values_only=True))
    assert any(row[1] == "QA-COMPONENT-CPU-001" and row[4] == "Mouse" and row[5] == "Not Previously Recorded" and row[6] == "QA-MOUSE-NEW-001" for row in component_rows)
    assert any(row[1] == "QA-COMPONENT-CPU-001" and row[4] == "Keyboard" and row[5] == "QA-KB-OLD-001" and row[6] == "QA-KB-NEW-001" for row in component_rows)

    deleted = client.delete(f"/api/assets/{asset['id']}", headers=it_headers)
    assert deleted.status_code == 204, deleted.text


def test_multi_item_change_batch_and_monthly_reports(client: TestClient) -> None:
    from datetime import datetime

    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    month_key = datetime.now().strftime("%Y-%m")

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Computer",
            "status": "available",
            "cpu_asset_tag": "QA-BATCH-CPU-001",
            "workstation_no": "QA-NW-BATCH-001",
            "system_name": "QA-BATCH-PC",
            "monitor_asset_tags": "QA-BATCH-MON-OLD",
            "mouse_asset_tag": "QA-BATCH-MOUSE-OLD",
            "keyboard_asset_tag": "QA-BATCH-KB-OLD",
            "processor": "Intel Core i5",
            "memory_gb": "8 GB",
            "ssd": "256 GB",
            "hdd": "1 TB",
            "network_type": "DHCP",
            "location": "Head Office",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()

    batch = client.post(
        "/api/component-replacements/batch",
        headers=it_headers,
        json={
            "asset_id": asset["id"],
            "change_type": "upgrade_replacement",
            "technician": "IT Department",
            "replacement_date": datetime.now().date().isoformat(),
            "approved_by": "QA Approver",
            "remarks": "One work activity with multiple component changes",
            "items": [
                {
                    "component_type": "Mouse",
                    "change_type": "replacement",
                    "old_value": "QA-BATCH-MOUSE-OLD",
                    "new_value": "QA-BATCH-MOUSE-NEW",
                    "reason": "Mouse button failed",
                    "old_condition": "Damaged",
                },
                {
                    "component_type": "Memory",
                    "change_type": "upgrade",
                    "old_value": "8 GB",
                    "new_value": "16 GB",
                    "reason": "Performance upgrade",
                    "old_condition": "Working",
                },
                {
                    "component_type": "SSD",
                    "change_type": "upgrade_replacement",
                    "old_value": "256 GB",
                    "new_value": "512 GB",
                    "reason": "Old drive failed and capacity increased",
                    "old_condition": "Failed",
                },
            ],
        },
    )
    assert batch.status_code == 200, batch.text
    result = batch.json()
    assert result["batch_code"].startswith("CHG-")
    assert result["work_code"].startswith("ITW-")
    assert len(result["records"]) == 3
    assert {row["change_type"] for row in result["records"]} == {
        "replacement", "upgrade", "upgrade_replacement"
    }
    assert len({row["batch_code"] for row in result["records"]}) == 1
    assert len({row["work_code"] for row in result["records"]}) == 1

    detail = client.get(f"/api/assets/{asset['id']}", headers=it_headers)
    assert detail.status_code == 200, detail.text
    updated = detail.json()
    assert updated["mouse_asset_tag"] == "QA-BATCH-MOUSE-NEW"
    assert updated["memory_gb"] == "16 GB"
    assert updated["ssd"] == "512 GB"
    assert len(updated["component_replacements"]) == 3
    assert any(item["action"] == "Upgrade and Replacement" for item in updated["history"])

    months = client.get("/api/reports/months", headers=it_headers)
    assert months.status_code == 200, months.text
    current_month = next(item for item in months.json() if item["key"] == month_key)
    assert current_month["status"] in {"live", "finalized"}

    monthly_assets = client.get(
        f"/api/reports/monthly-assets.xlsx?month={month_key}", headers=it_headers
    )
    assert monthly_assets.status_code == 200, monthly_assets.text
    register_book = load_workbook(BytesIO(monthly_assets.content), read_only=True, data_only=True)
    assert len(register_book.sheetnames) == 1
    register_sheet = register_book[register_book.sheetnames[0]]
    rows = [
        row for row in register_sheet.iter_rows(min_row=2, values_only=True)
        if len(row) >= 13 and row[4] == "QA-BATCH-CPU-001"
    ]
    assert len(rows) == 1
    assert rows[0][6] == "QA-BATCH-MOUSE-NEW"
    assert rows[0][11] == "16 GB"
    assert rows[0][12] == "512 GB"

    monthly_changes = client.get(
        f"/api/reports/monthly-changes.xlsx?month={month_key}", headers=it_headers
    )
    assert monthly_changes.status_code == 200, monthly_changes.text
    change_book = load_workbook(BytesIO(monthly_changes.content), read_only=True, data_only=True)
    assert "Component Changes" in change_book.sheetnames
    change_rows = list(change_book["Component Changes"].iter_rows(min_row=2, values_only=True))
    matching = [row for row in change_rows if row[4] == "QA-BATCH-CPU-001"]
    assert len(matching) == 3
    assert {row[6] for row in matching} == {"Replacement", "Upgrade", "Upgrade Replacement"}

    monthly_summary = client.get(
        f"/api/reports/monthly-summary.xlsx?month={month_key}", headers=it_headers
    )
    assert monthly_summary.status_code == 200, monthly_summary.text
    summary_book = load_workbook(BytesIO(monthly_summary.content), read_only=True, data_only=True)
    metrics = {
        row[0]: row[1]
        for row in summary_book["Monthly Asset Summary"].iter_rows(min_row=5, values_only=True)
        if row[0]
    }
    assert metrics["New Assets Added"] >= 1
    assert metrics["Component Upgrades"] >= 1
    assert metrics["Component Replacements"] >= 1
    assert metrics["Upgrade + Replacement Items"] >= 1

    finalized = client.post(
        f"/api/monthly-snapshots/finalize?month={month_key}", headers=admin_headers
    )
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["closing_count"] >= 184
    months_after = client.get("/api/reports/months", headers=it_headers).json()
    finalized_month = next(item for item in months_after if item["key"] == month_key)
    assert finalized_month["status"] == "finalized"

    deleted = client.delete(f"/api/assets/{asset['id']}", headers=it_headers)
    assert deleted.status_code == 204, deleted.text


def test_historical_abbreviated_months_are_selectable(client: TestClient) -> None:
    headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    months = client.get("/api/reports/months", headers=headers)
    assert months.status_code == 200, months.text
    month_keys = {item["key"] for item in months.json()}
    assert "2025-10" in month_keys
    assert "2024-05" in month_keys

    historical = client.get("/api/reports/monthly-assets.xlsx?month=2025-10", headers=headers)
    assert historical.status_code == 200, historical.text
    book = load_workbook(BytesIO(historical.content), read_only=True, data_only=True)
    assert book.sheetnames == ["October 2025"]
    assert book["October 2025"]["A1"].value == "SL"


def test_month_dashboard_and_historical_register_are_connected(client: TestClient) -> None:
    from datetime import datetime

    headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    current_key = datetime.now().strftime("%Y-%m")

    current = client.get(f"/api/dashboard/it?month={current_key}", headers=headers)
    assert current.status_code == 200, current.text
    assert current.json()["month"]["key"] == current_key
    assert current.json()["month"]["is_live"] is True
    assert current.json()["month"]["read_only"] is False

    months = client.get("/api/reports/months", headers=headers)
    assert months.status_code == 200, months.text
    current_option = next(item for item in months.json() if item["key"] == current_key)
    assert current_option["is_current"] is True

    historical_month = "2025-10"
    dashboard = client.get(f"/api/dashboard/it?month={historical_month}", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    payload = dashboard.json()
    assert payload["month"]["key"] == historical_month
    assert payload["month"]["is_live"] is False
    assert payload["month"]["read_only"] is True
    assert payload["month"]["source"] == "template"
    assert payload["kpis"]["total"] > 0

    assets = client.get(f"/api/assets?month={historical_month}&limit=2000", headers=headers)
    assert assets.status_code == 200, assets.text
    rows = assets.json()
    assert len(rows) == payload["kpis"]["total"]
    assert all(row["source_sheet"] for row in rows)
    assert all(row["id"] < 0 for row in rows)

    sample = next((row for row in rows if row.get("cpu_asset_tag") and row.get("workstation_no")), rows[0])
    search_term = sample.get("cpu_asset_tag") or sample.get("workstation_no")
    filtered = client.get(
        f"/api/assets?month={historical_month}&search={search_term}&limit=2000",
        headers=headers,
    )
    assert filtered.status_code == 200, filtered.text
    assert any(row["asset_code"] == sample["asset_code"] for row in filtered.json())


def test_drone_workbook_preview_preserves_all_source_structures(client: TestClient) -> None:
    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    workbook_path = Path(__file__).resolve().parents[1] / "app" / "data" / "drone_hardware_inventory_template.xlsx"
    with workbook_path.open("rb") as workbook_file:
        response = client.post(
            "/api/drone/import/preview?reporting_month=2026-05",
            headers=admin_headers,
            files={
                "file": (
                    workbook_path.name,
                    workbook_file,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
    assert response.status_code == 200, response.text
    preview = response.json()
    summary = preview["summary"]
    assert summary["named_source_attributes"] == 52
    assert summary["main_inventory_records"] == 66
    assert summary["telecom_connections"] == 2
    assert summary["uin_registrations"] == 3
    assert summary["trinity_components"] == 39
    assert summary["trinity_kits"] == 2
    assert summary["amrut_assignment_records"] == 18
    assert summary["hdd_delivery_transactions"] == 7
    assert summary["issue_counts"]["multiple_serial_numbers_require_split"] == 5
    assert summary["issue_counts"]["duplicate_imported_equipment_id"] == 10

    attribute_response = client.get("/api/drone/attributes", headers=admin_headers)
    assert attribute_response.status_code == 200
    assert attribute_response.json()["count"] == 52


def test_drone_import_commit_is_separate_from_it_assets(client: TestClient) -> None:
    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    batches = client.get("/api/drone/import/batches", headers=admin_headers).json()
    batch = batches[0]
    before_it_total = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]
    commit = client.post(
        f"/api/drone/import/{batch['batch_id']}/commit",
        headers=admin_headers,
        json={"allow_warnings": True},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["created_assets"] == 123
    assert commit.json()["created_kits"] == 2
    assert commit.json()["created_projects"] == 1

    drone_assets = client.get("/api/drone/assets?limit=500", headers=admin_headers)
    assert drone_assets.status_code == 200
    assert drone_assets.json()["total"] == 123
    assert len(client.get("/api/drone/kits", headers=admin_headers).json()) == 2
    assert len(client.get("/api/drone/projects", headers=admin_headers).json()) == 1

    after_it_total = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]
    assert after_it_total == before_it_total == 183


def test_drone_permissions_and_legacy_telemetry_remain_compatible(client: TestClient) -> None:
    drone_headers = login(client, "drone", "drone@nakshatech.com", "Drone@123")
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    assert client.get("/api/drone/dashboard", headers=drone_headers).status_code == 200
    assert client.get("/api/drone/assets", headers=drone_headers).status_code == 200
    assert client.get("/api/drone/dashboard", headers=it_headers).status_code == 403
    assert client.get("/api/drone/operations", headers=it_headers).status_code == 403
    assert client.get("/api/drone/work-records", headers=it_headers).status_code == 403
    assert client.get("/api/drones", headers=drone_headers).status_code == 200


def test_drone_phase2_dispatch_partial_return_transfer_and_work_records(client: TestClient) -> None:
    drone_headers = login(client, "drone", "drone@nakshatech.com", "Drone@123")
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    before_it_total = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]

    project_one = client.post(
        "/api/drone/projects",
        headers=drone_headers,
        json={
            "project_name": "QA Drone Operations Project A",
            "client": "QA Client",
            "project_manager": "QA Manager",
            "start_date": "2026-08-01",
            "expected_end_date": "2026-09-30",
            "status": "active",
            "financial_year": "2026-27",
            "location": "Davangere",
        },
    )
    assert project_one.status_code == 200, project_one.text
    project_a = project_one.json()

    project_two = client.post(
        "/api/drone/projects",
        headers=drone_headers,
        json={
            "project_name": "QA Drone Operations Project B",
            "status": "active",
            "location": "Bengaluru",
        },
    )
    assert project_two.status_code == 200, project_two.text
    project_b = project_two.json()

    drone_asset = client.post(
        "/api/drone/assets",
        headers=drone_headers,
        json={
            "asset_name": "QA DJI M350 RTK",
            "category": "Drone",
            "manufacturer": "DJI",
            "model_number": "M350 RTK",
            "serial_number": "QA-M350-PHASE2-001",
            "quantity": 1,
            "tracking_type": "serialized_asset",
            "current_status": "available",
            "working_condition": "working",
            "current_location": "Head Office",
        },
    )
    assert drone_asset.status_code == 200, drone_asset.text
    drone = drone_asset.json()

    battery_asset = client.post(
        "/api/drone/assets",
        headers=drone_headers,
        json={
            "asset_name": "QA Battery Batch",
            "category": "Battery",
            "quantity": 5,
            "tracking_type": "quantity_managed_asset",
            "current_status": "available",
            "working_condition": "working",
            "current_location": "Head Office",
        },
    )
    assert battery_asset.status_code == 200, battery_asset.text
    battery = battery_asset.json()

    dispatch = client.post(
        "/api/drone/operations/dispatch",
        headers=drone_headers,
        json={
            "project_id": project_a["id"],
            "custodian": "QA Pilot",
            "destination": "Davangere Site",
            "dispatch_date": "2026-08-05",
            "expected_return_date": "2026-09-30",
            "purpose": "QA operational workflow",
            "condition": "flight ready",
            "approved_by": "QA Drone Manager",
            "items": [
                {"asset_id": drone["id"], "quantity": 1},
                {"asset_id": battery["id"], "quantity": 2},
            ],
        },
    )
    assert dispatch.status_code == 200, dispatch.text
    dispatched = dispatch.json()
    assert dispatched["operation_type"] == "dispatch"
    assert dispatched["status"] == "active"
    assert len(dispatched["items"]) == 2

    refreshed_drone = client.get(f"/api/drone/assets/{drone['id']}", headers=drone_headers).json()
    refreshed_battery = client.get(f"/api/drone/assets/{battery['id']}", headers=drone_headers).json()
    assert refreshed_drone["current_project_id"] == project_a["id"]
    assert refreshed_drone["current_status"] == "deployed_to_project"
    assert refreshed_battery["current_project_id"] == project_a["id"]

    project_detail = client.get(f"/api/drone/projects/{project_a['id']}", headers=drone_headers)
    assert project_detail.status_code == 200, project_detail.text
    assert project_detail.json()["summary"]["asset_count"] == 2
    assert any(item["operation_code"] == dispatched["operation_code"] for item in project_detail.json()["operations"])

    drone_item = next(item for item in dispatched["items"] if item["asset_id"] == drone["id"])
    battery_item = next(item for item in dispatched["items"] if item["asset_id"] == battery["id"])
    partial_return = client.post(
        "/api/drone/operations/return",
        headers=drone_headers,
        json={
            "dispatch_operation_id": dispatched["id"],
            "return_date": "2026-08-20",
            "receiver": "Drone Store",
            "return_location": "Head Office",
            "remarks": "Drone returned; one battery remains at project",
            "items": [
                {"operation_item_id": drone_item["id"], "quantity": 1, "condition": "working", "next_status": "available"},
                {"operation_item_id": battery_item["id"], "quantity": 1, "condition": "working", "next_status": "available"},
            ],
        },
    )
    assert partial_return.status_code == 200, partial_return.text
    assert partial_return.json()["source_operation"]["status"] == "partial"
    assert client.get(f"/api/drone/assets/{drone['id']}", headers=drone_headers).json()["current_status"] == "available"
    assert client.get(f"/api/drone/assets/{battery['id']}", headers=drone_headers).json()["current_status"] == "deployed_to_project"

    transfer = client.post(
        "/api/drone/operations/transfer",
        headers=drone_headers,
        json={
            "transfer_date": "2026-08-25",
            "to_project_id": project_b["id"],
            "to_custodian": "QA Second Pilot",
            "destination": "Bengaluru Site",
            "reason": "Project priority changed",
            "approved_by": "QA Drone Manager",
            "items": [{"asset_id": battery["id"], "quantity": 1}],
        },
    )
    assert transfer.status_code == 200, transfer.text
    moved_battery = client.get(f"/api/drone/assets/{battery['id']}", headers=drone_headers).json()
    assert moved_battery["current_project_id"] == project_b["id"]
    assert moved_battery["current_custodian"] == "QA Second Pilot"

    final_return = client.post(
        "/api/drone/operations/return",
        headers=drone_headers,
        json={
            "dispatch_operation_id": dispatched["id"],
            "return_date": "2026-09-01",
            "receiver": "Drone Store",
            "return_location": "Head Office",
            "items": [
                {"operation_item_id": battery_item["id"], "quantity": 1, "condition": "working", "next_status": "available"}
            ],
        },
    )
    assert final_return.status_code == 200, final_return.text
    assert final_return.json()["source_operation"]["status"] == "completed"
    final_battery = client.get(f"/api/drone/assets/{battery['id']}", headers=drone_headers).json()
    assert final_battery["current_status"] == "available"
    assert final_battery["current_project_id"] is None

    manual_work = client.post(
        "/api/drone/work-records",
        headers=drone_headers,
        json={
            "title": "QA pre-flight inspection",
            "work_type": "inspection",
            "project_id": project_a["id"],
            "asset_id": drone["id"],
            "assigned_to": "QA Pilot",
            "technician": "Drone Department",
            "priority": "high",
            "description": "Inspect airframe, controller and batteries",
            "initial_condition": "Available",
            "start_date": "2026-08-02",
            "expected_completion_date": "2026-08-02",
        },
    )
    assert manual_work.status_code == 200, manual_work.text
    completed_work = client.patch(
        f"/api/drone/work-records/{manual_work.json()['id']}",
        headers=drone_headers,
        json={"status": "completed", "resolution": "Inspection passed"},
    )
    assert completed_work.status_code == 200, completed_work.text
    assert completed_work.json()["status"] == "completed"

    movements = client.get(f"/api/drone/movements?asset_id={drone['id']}", headers=drone_headers)
    assert movements.status_code == 200
    assert {row["movement_type"] for row in movements.json()} >= {"dispatch", "return"}

    close_a = client.patch(
        f"/api/drone/projects/{project_a['id']}", headers=drone_headers, json={"status": "closed"}
    )
    assert close_a.status_code == 200, close_a.text
    close_b = client.patch(
        f"/api/drone/projects/{project_b['id']}", headers=drone_headers, json={"status": "closed"}
    )
    assert close_b.status_code == 200, close_b.text

    after_it_total = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]["total"]
    assert after_it_total == before_it_total == 183


def test_local_backup_agent_health_and_role_workbooks(client: TestClient) -> None:
    agent_headers = {
        "X-Naksha-Backup-Token": "test-local-backup-token-abcdefghijklmnopqrstuvwxyz-123456"
    }

    assert client.get("/api/local-backup/health").status_code == 401
    health = client.get("/api/local-backup/health", headers=agent_headers)
    assert health.status_code == 200, health.text
    assert health.json()["status"] == "healthy"
    assert health.json()["reporting_month"].count("-") == 1
    assert health.json()["roles"] == ["admin", "drone", "it", "management", "software_team"]

    expected = {
        "it": {
            "present": {"Backup Summary", "IT Asset Register", "IT Work Records"},
            "absent": {"Drone Asset Register", "System Users"},
        },
        "drone": {
            "present": {"Backup Summary", "Drone Asset Register", "Drone Projects"},
            "absent": {"IT Asset Register", "System Users"},
        },
        "management": {
            "present": {"Backup Summary", "IT Asset Register", "Drone Asset Register"},
            "absent": {"System Users"},
        },
        "admin": {
            "present": {"Backup Summary", "IT Asset Register", "Drone Asset Register", "System Users"},
            "absent": set(),
        },
        "software_team": {
            "present": {"Backup Summary", "IT Asset Register", "Drone Asset Register", "System Users"},
            "absent": set(),
        },
    }

    for role, rules in expected.items():
        response = client.get(f"/api/local-backup/export.xlsx?role={role}", headers=agent_headers)
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response.headers["x-backup-role"] == role
        assert response.headers["x-content-sha256"]
        assert response.content[:2] == b"PK"

        workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=False)
        names = set(workbook.sheetnames)
        assert rules["present"].issubset(names)
        assert not rules["absent"].intersection(names)
        summary = workbook["Backup Summary"]
        summary_values = {
            summary.cell(row, 1).value: summary.cell(row, 2).value
            for row in range(1, min(summary.max_row, 30) + 1)
        }
        expected_backup_role = "ADMIN" if role == "software_team" else role.upper()
        assert summary_values["Backup Role"] == expected_backup_role
        assert "Reporting Month" in summary_values

        if role == "admin":
            users = workbook["System Users"]
            headers = [cell.value for cell in users[1]]
            assert "Password Hash" not in headers
            assert "Email" in headers
        workbook.close()

    invalid = client.get("/api/local-backup/export.xlsx?role=unknown", headers=agent_headers)
    assert invalid.status_code == 400



def test_employee_registration_one_time_authenticator_then_password_login_and_ticket_routing(client: TestClient) -> None:
    import json
    from urllib.parse import parse_qs, urlparse

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.modules.employee_portal.models import AuditEvent
    from app.modules.employee_portal.service import totp_code

    capabilities = client.get("/api/auth/capabilities")
    assert capabilities.status_code == 200, capabilities.text
    assert capabilities.json()["authenticator_enabled"] is True

    branch_response = client.get("/api/auth/branches")
    assert branch_response.status_code == 200, branch_response.text
    branch_id = branch_response.json()[0]["id"]

    email = f"employee.portal.{uuid.uuid4().hex[:8]}@nakshatech.com"
    employee_id = f"NT-PORTAL-{uuid.uuid4().hex[:8].upper()}"
    otp_response = client.post("/api/auth/register/request-otp", json={"email": email})
    assert otp_response.status_code == 200, otp_response.text
    otp = otp_response.json().get("development_otp")
    assert otp, "Development OTP must be returned only in non-production console email mode"

    verified = client.post("/api/auth/register/verify-otp", json={"email": email, "otp": otp})
    assert verified.status_code == 200, verified.text

    completed = client.post(
        "/api/auth/register/complete",
        json={
            "registration_token": verified.json()["registration_token"],
            "full_name": "Portal Test Employee",
            "employee_id": employee_id,
            "department": "Operations",
            "designation": "Worker",
            "branch_id": branch_id,
            "password": "PortalStrong@123",
        },
    )
    assert completed.status_code == 200, completed.text
    setup = completed.json()
    assert setup["mfa_setup_token"]
    assert setup["qr_code_data_uri"].startswith("data:image/")
    secret = parse_qs(urlparse(setup["otpauth_uri"]).query)["secret"][0]

    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={"mfa_setup_token": setup["mfa_setup_token"], "code": totp_code(secret)},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["branch_selection_required"] is True
    assert confirmed.json()["user"]["mfa_enabled"] is True

    employee_headers = {"Authorization": f"Bearer {confirmed.json()['access_token']}"}
    selected = client.post(
        "/api/auth/select-branch",
        headers=employee_headers,
        json={"branch_id": branch_id},
    )
    assert selected.status_code == 200, selected.text
    employee_headers = {"Authorization": f"Bearer {selected.json()['access_token']}"}

    # Employee support accounts must remain isolated from existing department data and workflows.
    assert client.get("/api/dashboard/summary", headers=employee_headers).status_code == 403
    assert client.get("/api/dashboard/it", headers=employee_headers).status_code == 403
    assert client.get("/api/assets", headers=employee_headers).status_code == 403
    assert client.get("/api/work-records", headers=employee_headers).status_code == 403
    assert client.get("/api/backups/status", headers=employee_headers).status_code == 403

    invalid_manager = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "software_team",
            "reporting_manager_email": "manager@example.com",
            "title": "Invalid reporting manager domain",
            "description": "This request verifies organization email validation.",
        },
    )
    assert invalid_manager.status_code == 422, invalid_manager.text
    assert "@nakshatech.com" in invalid_manager.text

    missing_asset = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Portal test laptop issue",
            "description": "The test laptop cannot connect to the office network.",
            "priority": "high",
            "location": "Head Office",
        },
    )
    assert missing_asset.status_code == 422, missing_asset.text
    assert "select the affected CPU" in missing_asset.json()["detail"]

    asset_search = client.get("/api/ticket-assets?query=NT-", headers=employee_headers)
    assert asset_search.status_code == 200, asset_search.text
    assert asset_search.json(), "The employee asset selector must search current Asset Register records"
    selected_asset = asset_search.json()[0]

    invalid_problem = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Invalid classification test",
            "description": "This request verifies backend problem validation.",
            "asset_id": selected_asset["id"],
            "component": "mouse",
            "problem_code": "no_display",
            "impact": {"work_stopped": False, "alternative_available": True},
        },
    )
    assert invalid_problem.status_code == 422, invalid_problem.text

    catalog = client.get("/api/ticket-catalog", headers=employee_headers)
    assert catalog.status_code == 200, catalog.text
    assert any(item["code"] == "mouse" for item in catalog.json()["components"])

    preview = client.post(
        "/api/ticket-priority-preview",
        headers=employee_headers,
        json={
            "component": "mouse",
            "problem_code": "mouse_unusable",
            "impact": {
                "work_stopped": True,
                "alternative_available": False,
                "multiple_users_affected": False,
                "data_loss_risk": False,
                "security_risk": False,
                "client_delivery_affected": False,
                "recurring_issue": False,
                "started_when": "Today",
            },
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["priority"] == "high"

    created = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Portal test mouse issue",
            "description": "The test mouse is unusable and no replacement is available.",
            "priority": "low",
            "location": "Head Office",
            "asset_id": selected_asset["id"],
            "component": "mouse",
            "problem_code": "mouse_unusable",
            "impact": {
                "work_stopped": True,
                "alternative_available": False,
                "multiple_users_affected": False,
                "data_loss_risk": False,
                "security_risk": False,
                "client_delivery_affected": False,
                "recurring_issue": False,
                "started_when": "Today",
            },
        },
    )
    assert created.status_code == 200, created.text
    created_payload = created.json()
    assert created_payload["asset_id"] == selected_asset["id"]
    assert created_payload["asset_number"] == (selected_asset["cpu_asset_tag"] or selected_asset["asset_code"])
    assert created_payload["asset_snapshot"]["asset_code"] == selected_asset["asset_code"]
    assert created_payload["asset_snapshot"]["cpu_asset_tag"] == selected_asset["cpu_asset_tag"]
    assert created_payload["component"] == "mouse"
    assert created_payload["problem_code"] == "mouse_unusable"
    assert created_payload["problem_label"] == "Mouse completely unusable"
    assert created_payload["priority"] == "high"
    assert created_payload["priority_reason"]
    assert created_payload["sla_target_minutes"] == 120
    assert created_payload["impact_assessment"]["work_stopped"] is True
    assert created_payload["reporting_manager_email"] == "qa.manager@nakshatech.com"
    ticket_id = created_payload["id"]

    with SessionLocal() as db:
        created_email_audits = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_type == "ticket",
                    AuditEvent.target_id == str(ticket_id),
                    AuditEvent.event_type == "TICKET_EMAIL_SENT",
                    AuditEvent.details.like('%"email_event":"created"%'),
                )
            ).all()
        )
    assert len(created_email_audits) == 3
    created_email_audiences = {
        json.loads(event.details or "{}").get("audience")
        for event in created_email_audits
    }
    assert created_email_audiences == {"requester", "manager", "it"}

    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)

    low_ticket = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Low priority mouse scroll issue",
            "description": "The scroll wheel is not working but normal work can continue.",
            "asset_id": selected_asset["id"],
            "component": "mouse",
            "problem_code": "scroll_not_working",
            "impact": {
                "work_stopped": False,
                "alternative_available": True,
                "multiple_users_affected": False,
                "data_loss_risk": False,
                "security_risk": False,
                "client_delivery_affected": False,
                "recurring_issue": False,
            },
        },
    )
    assert low_ticket.status_code == 200, low_ticket.text
    assert low_ticket.json()["priority"] == "low"

    critical_ticket = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Critical account security issue",
            "description": "Suspicious account access requires immediate investigation.",
            "asset_id": selected_asset["id"],
            "component": "login_account",
            "problem_code": "suspected_account_compromise",
            "impact": {
                "work_stopped": False,
                "alternative_available": True,
                "multiple_users_affected": False,
                "data_loss_risk": False,
                "security_risk": True,
                "client_delivery_affected": False,
                "recurring_issue": False,
            },
        },
    )
    assert critical_ticket.status_code == 200, critical_ticket.text
    assert critical_ticket.json()["priority"] == "critical"

    later_high_ticket = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "Later high priority keyboard issue",
            "description": "A second high-priority ticket verifies oldest-first queue ordering.",
            "asset_id": selected_asset["id"],
            "component": "keyboard",
            "problem_code": "keyboard_unusable",
            "impact": {
                "work_stopped": True,
                "alternative_available": False,
                "multiple_users_affected": False,
                "data_loss_risk": False,
                "security_risk": False,
                "client_delivery_affected": False,
                "recurring_issue": False,
            },
        },
    )
    assert later_high_ticket.status_code == 200, later_high_ticket.text
    assert later_high_ticket.json()["priority"] == "high"

    if selected_asset["cpu_asset_tag"]:
        exact_tag_search = client.get(
            f"/api/ticket-assets?query={selected_asset['cpu_asset_tag']}",
            headers=employee_headers,
        )
        assert exact_tag_search.status_code == 200, exact_tag_search.text
        assert any(item["id"] == selected_asset["id"] for item in exact_tag_search.json())

    original_system_name = selected_asset["system_name"]
    changed_system_name = f"CHANGED-AFTER-TICKET-{uuid.uuid4().hex[:6]}"
    changed_asset = client.patch(
        f"/api/assets/{selected_asset['id']}",
        headers=it_headers,
        json={"system_name": changed_system_name},
    )
    assert changed_asset.status_code == 200, changed_asset.text
    ticket_after_asset_edit = client.get(f"/api/tickets/{ticket_id}", headers=employee_headers)
    assert ticket_after_asset_edit.status_code == 200, ticket_after_asset_edit.text
    assert ticket_after_asset_edit.json()["asset_snapshot"]["system_name"] == original_system_name

    it_queue = client.get("/api/tickets", headers=it_headers)
    assert it_queue.status_code == 200
    queue_payload = it_queue.json()
    queue_ids = [item["id"] for item in queue_payload]
    assert ticket_id in queue_ids
    assert queue_ids.index(critical_ticket.json()["id"]) < queue_ids.index(ticket_id) < queue_ids.index(low_ticket.json()["id"])
    assert queue_ids.index(ticket_id) < queue_ids.index(later_high_ticket.json()["id"])
    assert [item["queue_position"] for item in queue_payload] == list(range(1, len(queue_payload) + 1))
    selected_queue_item = next(item for item in queue_payload if item["id"] == ticket_id)
    assert selected_queue_item["created_at"]
    assert selected_queue_item["updated_at"]
    assert "resolved_at" in selected_queue_item
    assert "closed_at" in selected_queue_item

    drone_headers = login(client, "drone", settings.seed_drone_email, settings.seed_drone_password)
    drone_queue = client.get("/api/tickets", headers=drone_headers)
    assert drone_queue.status_code == 200
    assert all(item["id"] != ticket_id for item in drone_queue.json())

    software_headers = login(client, "software_team", settings.seed_admin_email, settings.seed_admin_password)

    import app.modules.employee_portal.router as employee_portal_router_module

    stored_ticket_images: dict[str, bytes] = {}
    original_store_attachment = employee_portal_router_module.store_ticket_attachment
    original_stream_attachment = employee_portal_router_module.stream_ticket_attachment
    original_delete_attachment = employee_portal_router_module.delete_ticket_attachment_object

    def fake_store_attachment(fake_ticket_id, attachment):
        storage_key = f"test-ticket-evidence/{fake_ticket_id}/{len(stored_ticket_images) + 1}.png"
        stored_ticket_images[storage_key] = attachment.data
        return storage_key

    def fake_stream_attachment(storage_key):
        if storage_key not in stored_ticket_images:
            raise FileNotFoundError(storage_key)
        return iter([stored_ticket_images[storage_key]])

    def fake_delete_attachment(storage_key):
        stored_ticket_images.pop(storage_key, None)

    employee_portal_router_module.store_ticket_attachment = fake_store_attachment
    employee_portal_router_module.stream_ticket_attachment = fake_stream_attachment
    employee_portal_router_module.delete_ticket_attachment_object = fake_delete_attachment
    try:
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"ticket-evidence-test"
        evidence_upload = client.post(
            f"/api/tickets/{ticket_id}/attachments",
            headers=employee_headers,
            files=[("files", ("mouse-error.png", png_bytes, "image/png"))],
        )
        assert evidence_upload.status_code == 201, evidence_upload.text
        uploaded_attachment = evidence_upload.json()[0]
        assert uploaded_attachment["original_filename"] == "mouse-error.png"
        assert uploaded_attachment["file_size"] == len(png_bytes)

        ticket_with_evidence = client.get(f"/api/tickets/{ticket_id}", headers=employee_headers)
        assert ticket_with_evidence.status_code == 200, ticket_with_evidence.text
        assert len(ticket_with_evidence.json()["attachments"]) == 1
        attachment_id = ticket_with_evidence.json()["attachments"][0]["id"]

        employee_content = client.get(
            f"/api/tickets/{ticket_id}/attachments/{attachment_id}/content",
            headers=employee_headers,
        )
        assert employee_content.status_code == 200, employee_content.text
        assert employee_content.content == png_bytes
        assert employee_content.headers["content-type"].startswith("image/png")

        assert client.get(
            f"/api/tickets/{ticket_id}/attachments/{attachment_id}/content",
            headers=it_headers,
        ).status_code == 200
        assert client.get(
            f"/api/tickets/{ticket_id}/attachments/{attachment_id}/content",
            headers=software_headers,
        ).status_code == 200
        assert client.get(
            f"/api/tickets/{ticket_id}/attachments/{attachment_id}/content",
            headers=drone_headers,
        ).status_code == 404

        handler_upload = client.post(
            f"/api/tickets/{ticket_id}/attachments",
            headers=it_headers,
            files=[("files", ("handler.png", png_bytes, "image/png"))],
        )
        assert handler_upload.status_code == 403

        spoofed_upload = client.post(
            f"/api/tickets/{ticket_id}/attachments",
            headers=employee_headers,
            files=[("files", ("fake.png", b"not-an-image", "image/png"))],
        )
        assert spoofed_upload.status_code == 415
    finally:
        employee_portal_router_module.store_ticket_attachment = original_store_attachment
        employee_portal_router_module.stream_ticket_attachment = original_stream_attachment
        employee_portal_router_module.delete_ticket_attachment_object = original_delete_attachment

    software_view = client.get(f"/api/tickets/{ticket_id}", headers=software_headers)
    assert software_view.status_code == 200
    software_reply = client.post(
        f"/api/tickets/{ticket_id}/messages",
        headers=software_headers,
        json={"message": "Read-only monitoring must not allow a Software Team reply to an IT ticket."},
    )
    assert software_reply.status_code == 403

    returning = client.post("/api/auth/login", json={"email": email, "password": "PortalStrong@123"})
    assert returning.status_code == 200
    assert returning.json()["requires_mfa"] is False
    assert returning.json()["mfa_setup_required"] is False
    assert returning.json()["access_token"]
    assert returning.json()["branch_selection_required"] is True



def test_pending_registration_can_resume_authenticator_but_active_login_is_password_only(client: TestClient) -> None:
    from urllib.parse import parse_qs, urlparse

    from app.modules.employee_portal.service import totp_code

    branch_id = client.get("/api/auth/branches").json()[0]["id"]
    email = f"employee.resume.{uuid.uuid4().hex[:8]}@nakshatech.com"
    password = "ResumeActivation@123"

    otp_response = client.post("/api/auth/register/request-otp", json={"email": email})
    verified = client.post(
        "/api/auth/register/verify-otp",
        json={"email": email, "otp": otp_response.json()["development_otp"]},
    )
    completed = client.post(
        "/api/auth/register/complete",
        json={
            "registration_token": verified.json()["registration_token"],
            "full_name": "Resume Activation Employee",
            "employee_id": f"NT-RES-{uuid.uuid4().hex[:8].upper()}",
            "department": "Operations",
            "branch_id": branch_id,
            "password": password,
        },
    )
    assert completed.status_code == 200, completed.text

    # Closing/refeshing the registration page must not permanently lock the user out.
    resumed = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["mfa_setup_required"] is True
    assert resumed.json()["access_token"] is None
    secret = parse_qs(urlparse(resumed.json()["otpauth_uri"]).query)["secret"][0]

    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={
            "mfa_setup_token": resumed.json()["mfa_setup_token"],
            "code": totp_code(secret),
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["access_token"]
    assert confirmed.json()["user"]["mfa_enabled"] is True

    returning = client.post("/api/auth/login", json={"email": email, "password": password})
    assert returning.status_code == 200, returning.text
    assert returning.json()["access_token"]
    assert returning.json()["requires_mfa"] is False
    assert returning.json()["mfa_setup_required"] is False

def test_employee_password_reset_and_software_ticket_handling(client: TestClient) -> None:
    from urllib.parse import parse_qs, urlparse

    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.modules.employee_portal.models import AuditEvent
    from app.modules.employee_portal.service import totp_code

    branch_id = client.get("/api/auth/branches").json()[0]["id"]
    email = f"employee.recovery.{uuid.uuid4().hex[:8]}@nakshatech.com"
    initial_password = "PortalStart@123"
    new_password = "PortalReset@456"

    otp_response = client.post("/api/auth/register/request-otp", json={"email": email})
    assert otp_response.status_code == 200, otp_response.text
    registration_otp = otp_response.json().get("development_otp")
    verified = client.post(
        "/api/auth/register/verify-otp",
        json={"email": email, "otp": registration_otp},
    )
    assert verified.status_code == 200, verified.text

    completed = client.post(
        "/api/auth/register/complete",
        json={
            "registration_token": verified.json()["registration_token"],
            "full_name": "Recovery Test Employee",
            "employee_id": f"NT-REC-{uuid.uuid4().hex[:8].upper()}",
            "department": "Operations",
            "designation": "Worker",
            "branch_id": branch_id,
            "password": initial_password,
        },
    )
    assert completed.status_code == 200, completed.text
    setup = completed.json()
    secret = parse_qs(urlparse(setup["otpauth_uri"]).query)["secret"][0]
    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={"mfa_setup_token": setup["mfa_setup_token"], "code": totp_code(secret)},
    )
    assert confirmed.status_code == 200, confirmed.text
    selected = client.post(
        "/api/auth/select-branch",
        headers={"Authorization": f"Bearer {confirmed.json()['access_token']}"},
        json={"branch_id": branch_id},
    )
    assert selected.status_code == 200, selected.text
    employee_headers = {"Authorization": f"Bearer {selected.json()['access_token']}"}

    created = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "software_team",
            "reporting_manager_email": "qa.manager@nakshatech.com",
            "title": "CRM test page is unavailable",
            "description": "The employee test account cannot open a CRM page during verification.",
            "priority": "medium",
            "location": "Head Office",
        },
    )
    assert created.status_code == 200, created.text
    assert created.json()["ticket_code"].startswith("NT-SW-")
    ticket_id = created.json()["id"]

    software_headers = login(client, "software_team", settings.seed_admin_email, settings.seed_admin_password)
    software_reply = client.post(
        f"/api/tickets/{ticket_id}/messages",
        headers=software_headers,
        json={"message": "Software Team accepted this test ticket."},
    )
    assert software_reply.status_code == 200, software_reply.text
    software_update = client.patch(
        f"/api/tickets/{ticket_id}",
        headers=software_headers,
        json={
            "assign_to_self": True,
            "status": "resolved",
            "resolution": "Test resolution recorded by Software Team.",
        },
    )
    assert software_update.status_code == 200, software_update.text
    assert software_update.json()["status"] == "resolved"
    assert software_update.json()["resolved_at"] is not None
    assert software_update.json()["closed_at"] is None

    with SessionLocal() as db:
        resolved_email_audits = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_type == "ticket",
                    AuditEvent.target_id == str(ticket_id),
                    AuditEvent.event_type == "TICKET_EMAIL_SENT",
                    AuditEvent.details.like('%"email_event":"resolved"%'),
                )
            ).all()
        )
    assert len(resolved_email_audits) == 3

    repeated_update = client.patch(
        f"/api/tickets/{ticket_id}",
        headers=software_headers,
        json={"status": "resolved", "resolution": "Resolution details confirmed without a duplicate email."},
    )
    assert repeated_update.status_code == 200, repeated_update.text
    with SessionLocal() as db:
        repeated_email_audits = list(
            db.scalars(
                select(AuditEvent).where(
                    AuditEvent.target_type == "ticket",
                    AuditEvent.target_id == str(ticket_id),
                    AuditEvent.event_type == "TICKET_EMAIL_SENT",
                    AuditEvent.details.like('%"email_event":"resolved"%'),
                )
            ).all()
        )
    assert len(repeated_email_audits) == 3

    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    assert client.get(f"/api/tickets/{ticket_id}", headers=it_headers).status_code == 404

    reset_request = client.post("/api/auth/forgot-password/request-otp", json={"email": email})
    assert reset_request.status_code == 200, reset_request.text
    reset_otp = reset_request.json().get("development_otp")
    assert reset_otp
    reset_verified = client.post(
        "/api/auth/forgot-password/verify-otp",
        json={"email": email, "otp": reset_otp},
    )
    assert reset_verified.status_code == 200, reset_verified.text
    reset = client.post(
        "/api/auth/forgot-password/reset",
        json={"reset_token": reset_verified.json()["reset_token"], "new_password": new_password},
    )
    assert reset.status_code == 200, reset.text

    assert client.post("/api/auth/login", json={"email": email, "password": initial_password}).status_code == 401
    returning = client.post("/api/auth/login", json={"email": email, "password": new_password})
    assert returning.status_code == 200, returning.text
    assert returning.json()["requires_mfa"] is False
    assert returning.json()["mfa_setup_required"] is False
    assert returning.json()["access_token"]

    users = client.get("/api/software/users", headers=software_headers)
    assert users.status_code == 200, users.text
    employee_row = next(item for item in users.json() if item["email"] == email)
    assert employee_row["mfa_enabled"] is True
    assert employee_row["email_verified"] is True

    audit = client.get(
        f"/api/software/audit?user_email={email}&limit=200",
        headers=software_headers,
    )
    assert audit.status_code == 200, audit.text
    events = {item["event_type"] for item in audit.json()}
    assert "PASSWORD_RESET_COMPLETED" in events
    assert "TICKET_CREATED" in events


def test_complete_monthly_and_yearly_excel_reporting(client: TestClient) -> None:
    from app.core.config import settings

    headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    current_month = datetime.now().strftime("%Y-%m")
    current_year = datetime.now().year

    monthly_response = client.get(
        f"/api/reports/complete-monthly.xlsx?month={current_month}",
        headers=headers,
    )
    assert monthly_response.status_code == 200, monthly_response.text
    assert "Complete IT Report" in monthly_response.headers["content-disposition"]
    monthly_book = load_workbook(BytesIO(monthly_response.content), read_only=False, data_only=False)
    required_sheets = {
        "Report Summary",
        "Monthly Asset Totals",
        "Primary IT Assets",
        "Printers",
        "External HDDs",
        "Asset Change History",
        "Work Records",
        "Component Changes",
        "Full Replacements",
        "Handovers Returns",
        "Purchases",
        "Purchase Requests",
        "Approval History",
        "Reconciliation",
    }
    assert required_sheets.issubset(set(monthly_book.sheetnames))
    monthly_totals = monthly_book["Monthly Asset Totals"]
    assert monthly_totals.max_row == 2
    headers_by_column = {
        monthly_totals.cell(1, column).value: column
        for column in range(1, monthly_totals.max_column + 1)
    }
    all_asset_rows = monthly_totals.cell(2, headers_by_column["All Asset Rows"]).value
    exported_asset_rows = (
        monthly_book["Primary IT Assets"].max_row - 1
        + monthly_book["Printers"].max_row - 1
        + monthly_book["External HDDs"].max_row - 1
    )
    assert exported_asset_rows == all_asset_rows
    assert monthly_book["Reconciliation"]["D2"].value.startswith("=IF(")
    monthly_book.close()

    yearly_response = client.get(
        f"/api/reports/complete-yearly.xlsx?year={current_year}&period=calendar",
        headers=headers,
    )
    assert yearly_response.status_code == 200, yearly_response.text
    yearly_book = load_workbook(BytesIO(yearly_response.content), read_only=False, data_only=False)
    assert required_sheets.issubset(set(yearly_book.sheetnames))
    yearly_totals = yearly_book["Monthly Asset Totals"]
    assert yearly_totals.max_row == 13
    month_keys = [yearly_totals.cell(row, 2).value for row in range(2, 14)]
    assert month_keys == [f"{current_year}-{month:02d}" for month in range(1, 13)]
    assert yearly_book["Report Summary"]["B4"].value == f"Calendar Year {current_year}"
    yearly_book.close()

    financial_response = client.get(
        f"/api/reports/complete-yearly.xlsx?year={current_year}&period=financial",
        headers=headers,
    )
    assert financial_response.status_code == 200, financial_response.text
    financial_book = load_workbook(BytesIO(financial_response.content), read_only=True, data_only=False)
    financial_totals = financial_book["Monthly Asset Totals"]
    financial_month_keys = [financial_totals.cell(row, 2).value for row in range(2, 14)]
    assert financial_month_keys[0] == f"{current_year}-04"
    assert financial_month_keys[-1] == f"{current_year + 1}-03"
    financial_book.close()

    invalid = client.get(
        f"/api/reports/complete-yearly.xlsx?year={current_year}&period=quarterly",
        headers=headers,
    )
    assert invalid.status_code == 400


def test_naksha_copilot_privacy_and_role_isolation(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_call_gemini(*, question: str, context: dict[str, object]) -> str:
        captured["question"] = question
        captured["context"] = context
        forbidden_keys = {
            "used_by", "current_holder", "serial_number", "cpu_asset_tag", "email",
            "phone_number", "remarks", "ticket_messages", "client_name", "asset_code",
        }

        def assert_safe_keys(value: object) -> None:
            if isinstance(value, dict):
                assert forbidden_keys.isdisjoint({str(key).lower() for key in value})
                for item in value.values():
                    assert_safe_keys(item)
            elif isinstance(value, list):
                for item in value:
                    assert_safe_keys(item)

        assert_safe_keys(context)
        return "Primary IT assets and activity statistics were analyzed using aggregate data only."

    monkeypatch.setattr("app.modules.naksha_copilot.router.call_gemini", fake_call_gemini)

    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    status_response = client.get("/api/naksha-copilot/status", headers=it_headers)
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["configured"] is True
    assert status_response.json()["privacy_mode"] == "Aggregated and anonymized reporting data only"

    response = client.post(
        "/api/naksha-copilot/ask",
        headers=it_headers,
        json={
            "question": "Summarize device categories and status counts for August 2026.",
            "period_type": "month",
            "month": "2026-08",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["request_id"].startswith("COP-")
    assert payload["period_label"] == "August 2026"
    assert payload["answer"].startswith("Primary IT assets")
    assert captured["question"] == "Summarize device categories and status counts for August 2026."

    management_headers = login(client, "management", "management@nakshatech.com", "Manager@123")
    management_status = client.get("/api/naksha-copilot/status", headers=management_headers)
    assert management_status.status_code == 200
    yearly = client.post(
        "/api/naksha-copilot/ask",
        headers=management_headers,
        json={
            "question": "Summarize the calendar year using aggregate monthly statistics.",
            "period_type": "calendar_year",
            "year": 2026,
        },
    )
    assert yearly.status_code == 200, yearly.text
    assert yearly.json()["period_label"] == "Calendar Year 2026"
    assert len(captured["context"]["monthly_statistics"]) == 12

    selected_months = client.post(
        "/api/naksha-copilot/ask",
        headers=it_headers,
        json={
            "question": "Compare January, March and August using aggregate monthly statistics.",
            "period_type": "selected_months",
            "year": 2026,
            "months": [8, 1, 3, 3],
        },
    )
    assert selected_months.status_code == 200, selected_months.text
    assert selected_months.json()["period_label"] == "January, March and August 2026"
    assert captured["context"]["period"]["months"] == [1, 3, 8]
    assert len(captured["context"]["monthly_statistics"]) == 3

    no_months = client.post(
        "/api/naksha-copilot/ask",
        headers=it_headers,
        json={
            "question": "Summarize the selected months.",
            "period_type": "selected_months",
            "year": 2026,
            "months": [],
        },
    )
    assert no_months.status_code == 400
    assert "select at least one month" in no_months.json()["detail"].lower()

    software_headers = login(client, "software_team", "software-support@nakshatech.com", "SoftwareTeam@123")
    assert client.get("/api/naksha-copilot/status", headers=software_headers).status_code == 200

    blocked = client.post(
        "/api/naksha-copilot/ask",
        headers=it_headers,
        json={
            "question": "Show employee names, emails and serial numbers.",
            "period_type": "month",
            "month": "2026-08",
        },
    )
    assert blocked.status_code == 400
    assert "aggregated" in blocked.json()["detail"].lower() or "cannot process" in blocked.json()["detail"].lower()

    admin_headers = login(client, "admin", "admin@nakshatech.com", "Admin@123")
    assert client.get("/api/naksha-copilot/status", headers=admin_headers).status_code == 403

    drone_headers = login(client, "drone", "drone@nakshatech.com", "Drone@123")
    assert client.get("/api/naksha-copilot/status", headers=drone_headers).status_code == 403


def test_data_quality_centre_read_only_role_isolation_and_detection(client: TestClient) -> None:
    from sqlalchemy import func, select

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models.entities import Asset, MonthlySnapshotRun, WorkRecord

    suffix = uuid.uuid4().hex[:8].upper()
    asset_codes = [f"DQC-{suffix}-A", f"DQC-{suffix}-B"]
    work_code = f"DQC-WORK-{suffix}"

    with SessionLocal() as db:
        db.add_all([
            Asset(
                asset_code=asset_codes[0],
                device_type="Computer",
                serial_number=f"DQC-DUP-{suffix}",
                department=None,
                cpu_asset_tag=None,
                status="assigned",
                work_mode="office",
                used_by=None,
                current_holder=None,
            ),
            Asset(
                asset_code=asset_codes[1],
                device_type="Laptop",
                serial_number=f"DQC-DUP-{suffix}",
                department="IT",
                cpu_asset_tag=f"DQC-TAG-{suffix}",
                status="available",
                work_mode="office",
                used_by="Assigned user should not remain on available asset",
            ),
            WorkRecord(
                work_code=work_code,
                module="it",
                title="Data quality reporting-month validation",
                status="open",
                reporting_month=None,
            ),
        ])
        db.commit()
        asset_count_before = db.scalar(select(func.count(Asset.id))) or 0
        snapshot_count_before = db.scalar(select(func.count(MonthlySnapshotRun.id))) or 0

    current_month = datetime.now().strftime("%Y-%m")
    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    management_headers = login(client, "management", settings.seed_management_email, settings.seed_management_password)
    software_headers = login(client, "software_team", settings.seed_admin_email, settings.seed_admin_password)
    admin_headers = login(client, "admin", settings.seed_organization_admin_email, settings.seed_organization_admin_password)
    drone_headers = login(client, "drone", settings.seed_drone_email, settings.seed_drone_password)

    try:
        response = client.get(f"/api/data-quality/summary?month={current_month}", headers=it_headers)
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["read_only"] is True
        assert payload["allowed_actions"] == ["view", "filter", "refresh"]
        assert payload["month"]["key"] == current_month
        assert payload["metrics"]["primary_it_assets"] > 0

        issues = {item["code"]: item for item in payload["issues"]}
        assert issues["missing_departments"]["count"] >= 1
        assert issues["duplicate_serial_numbers"]["count"] >= 2
        assert issues["missing_asset_identifiers"]["count"] >= 1
        assert issues["assigned_without_holders"]["count"] >= 1
        assert issues["invalid_status_combinations"]["count"] >= 1
        assert issues["missing_reporting_month"]["count"] >= 1

        assert client.get(f"/api/data-quality/summary?month={current_month}", headers=management_headers).status_code == 200
        assert client.get(f"/api/data-quality/summary?month={current_month}", headers=software_headers).status_code == 200
        assert client.get(f"/api/data-quality/summary?month={current_month}", headers=admin_headers).status_code == 403
        assert client.get(f"/api/data-quality/summary?month={current_month}", headers=drone_headers).status_code == 403

        assert client.post("/api/data-quality/summary", headers=it_headers).status_code == 405
        assert client.patch("/api/data-quality/summary", headers=it_headers).status_code == 405
        assert client.delete("/api/data-quality/summary", headers=it_headers).status_code == 405

        with SessionLocal() as db:
            assert (db.scalar(select(func.count(Asset.id))) or 0) == asset_count_before
            assert (db.scalar(select(func.count(MonthlySnapshotRun.id))) or 0) == snapshot_count_before
    finally:
        with SessionLocal() as db:
            work = db.scalar(select(WorkRecord).where(WorkRecord.work_code == work_code))
            if work:
                db.delete(work)
            for asset in db.scalars(select(Asset).where(Asset.asset_code.in_(asset_codes))).all():
                db.delete(asset)
            db.commit()


def test_batch3b_handover_return_consistency_and_guardrails(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    before = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]
    tag = f"QA-B3B-{uuid.uuid4().hex[:8].upper()}"

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Laptop",
            "status": "available",
            "cpu_asset_tag": tag,
            "system_name": tag,
            "department": "IT",
            "location": "3rd Floor",
            "processor": "Intel Core i5",
            "memory_gb": "16 GB",
            "ssd": "512 GB",
            "remarks": "Batch 3B custody consistency test",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()
    asset_id = asset["id"]

    after_create = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]
    assert after_create["total"] == before["total"] + 1
    assert after_create["laptops"] == before["laptops"] + 1
    assert after_create["available"] == before["available"] + 1

    handover = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian One",
            "dc_number": "QA-WS-B3B-01",
            "department": "IT",
            "work_mode": "wfh",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "handover",
            "activity_date": "2026-08-12",
            "remarks": "Batch 3B handover",
            "apply_to_asset": True,
        },
    )
    assert handover.status_code == 200, handover.text
    assert "Wfh" in (handover.json()["asset_updated_status"] or "")
    assert handover.json()["from_employee_name"] is None
    assert handover.json()["to_employee_name"] == "QA Custodian One"

    search = client.get(f"/api/assets?search={tag}&limit=10", headers=it_headers)
    assert search.status_code == 200, search.text
    live = next(item for item in search.json() if item["id"] == asset_id)
    assert live["used_by"] == "QA Custodian One"
    assert live["workstation_no"] == "QA-WS-B3B-01"
    assert live["work_mode"] == "wfh"
    assert live["status"] == "wfh"
    assert live["department"] == "IT"
    assert live["location"] == "3rd Floor"

    after_handover = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]
    assert after_handover["total"] == after_create["total"]
    assert after_handover["available"] == before["available"]
    assert after_handover["assigned"] == before["assigned"] + 1

    duplicate_handover = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian Two",
            "dc_number": "QA-WS-B3B-02",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "handover",
            "activity_date": "2026-08-12",
            "apply_to_asset": True,
        },
    )
    assert duplicate_handover.status_code == 409
    assert "use Transfer" in duplicate_handover.json()["detail"]

    transfer = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian Two",
            "dc_number": "QA-WS-B3B-02",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "transfer",
            "activity_date": "2026-08-12",
            "remarks": "Batch 3B transfer",
            "apply_to_asset": True,
        },
    )
    assert transfer.status_code == 200, transfer.text
    assert transfer.json()["from_employee_name"] == "QA Custodian One"
    assert transfer.json()["to_employee_name"] == "QA Custodian Two"

    same_custodian_transfer = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian Two",
            "dc_number": "QA-WS-B3B-02",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "transfer",
            "activity_date": "2026-08-12",
            "apply_to_asset": True,
        },
    )
    assert same_custodian_transfer.status_code == 409
    assert "different from the current custodian" in same_custodian_transfer.json()["detail"]

    returned = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian Two",
            "dc_number": "QA-WS-B3B-02",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Working",
            "action_type": "return",
            "return_status": "available",
            "activity_date": "2026-08-12",
            "remarks": "Batch 3B return",
            "apply_to_asset": True,
        },
    )
    assert returned.status_code == 200, returned.text
    assert "Available" in (returned.json()["asset_updated_status"] or "")
    assert returned.json()["from_employee_name"] == "QA Custodian Two"
    assert returned.json()["to_employee_name"] is None

    history_rows = client.get(
        f"/api/it-activity/handover-records?month=2026-08&search={tag}&limit=20",
        headers=it_headers,
    )
    assert history_rows.status_code == 200, history_rows.text
    movement_by_action = {item["action_type"]: item for item in history_rows.json()}
    assert movement_by_action["handover"]["to_employee_name"] == "QA Custodian One"
    assert movement_by_action["transfer"]["from_employee_name"] == "QA Custodian One"
    assert movement_by_action["transfer"]["to_employee_name"] == "QA Custodian Two"
    assert movement_by_action["return"]["from_employee_name"] == "QA Custodian Two"

    search = client.get(f"/api/assets?search={tag}&limit=10", headers=it_headers)
    live = next(item for item in search.json() if item["id"] == asset_id)
    assert live["status"] == "available"
    assert live["used_by"] is None
    assert live["workstation_no"] is None
    assert live["work_mode"] == "office"
    assert live["department"] == "IT"
    assert live["location"] == "3rd Floor"

    after_return = client.get("/api/dashboard/it", headers=it_headers).json()["kpis"]
    assert after_return["total"] == after_create["total"]
    assert after_return["available"] == before["available"] + 1
    assert after_return["assigned"] == before["assigned"]

    invalid_handover_return = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "",
            "dc_number": "",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "return",
            "return_status": "repair",
            "activity_date": "2026-08-12",
            "apply_to_asset": True,
        },
    )
    assert invalid_handover_return.status_code == 409
    assert "Only an assigned/in-use asset can be returned" in invalid_handover_return.json()["detail"]

    invalid_transfer_after_return = client.post(
        "/api/it-activity/handover-records",
        headers=it_headers,
        json={
            "reporting_month": "2026-08",
            "asset_id": asset_id,
            "device_category": "laptop",
            "employee_name": "QA Custodian Invalid",
            "dc_number": "QA-WS-INVALID",
            "department": "IT",
            "work_mode": "office",
            "internal_asset_no": tag,
            "condition": "Good",
            "action_type": "transfer",
            "activity_date": "2026-08-12",
            "apply_to_asset": True,
        },
    )
    assert invalid_transfer_after_return.status_code == 409
    assert "Only an assigned/in-use asset can be transferred" in invalid_transfer_after_return.json()["detail"]

    double_return = client.post(
        f"/api/assets/{asset_id}/return",
        headers=it_headers,
        json={"final_status": "available", "condition": "working", "remarks": "Should be blocked"},
    )
    assert double_return.status_code == 409
    assert "already returned" in double_return.json()["detail"]

    assigned_again = client.post(
        f"/api/assets/{asset_id}/assign",
        headers=it_headers,
        json={
            "used_by": "QA Custodian Three",
            "department": "IT",
            "workstation_no": "QA-WS-B3B-03",
            "location": "3rd Floor",
            "work_mode": "field",
            "assigned_date": "2026-08-12",
        },
    )
    assert assigned_again.status_code == 200, assigned_again.text
    assert assigned_again.json()["status"] == "field_deployment"

    register_transfer = client.post(
        f"/api/assets/{asset_id}/assign",
        headers=it_headers,
        json={
            "used_by": "QA Custodian Four",
            "department": "Software Development",
            "workstation_no": "QA-WS-B3B-04",
            "location": "3rd Floor",
            "work_mode": "office",
            "assigned_date": "2026-08-12",
            "remarks": "Asset Register transfer clarity test",
        },
    )
    assert register_transfer.status_code == 200, register_transfer.text
    assert register_transfer.json()["used_by"] == "QA Custodian Four"
    assert register_transfer.json()["department"] == "Software Development"
    assert register_transfer.json()["workstation_no"] == "QA-WS-B3B-04"

    same_register_transfer = client.post(
        f"/api/assets/{asset_id}/assign",
        headers=it_headers,
        json={
            "used_by": "QA Custodian Four",
            "department": "Software Development",
            "workstation_no": "QA-WS-B3B-04",
            "location": "3rd Floor",
            "work_mode": "office",
        },
    )
    assert same_register_transfer.status_code == 409
    assert "different from the current custodian" in same_register_transfer.json()["detail"]

    register_return = client.post(
        f"/api/assets/{asset_id}/return",
        headers=it_headers,
        json={
            "final_status": "available",
            "return_date": "2026-08-12",
            "condition": "working",
            "all_components_returned": True,
            "remarks": "Asset Register comparison return",
        },
    )
    assert register_return.status_code == 200, register_return.text
    for field, expected in {
        "status": "available",
        "used_by": None,
        "workstation_no": None,
        "work_mode": "office",
        "department": "Software Development",
        "location": "3rd Floor",
    }.items():
        assert register_return.json()[field] == expected

    repair_status = client.patch(
        f"/api/assets/{asset_id}/status",
        headers=it_headers,
        json={"status": "repair", "remarks": "Batch 3B assignment guard"},
    )
    assert repair_status.status_code == 200, repair_status.text
    blocked_assignment = client.post(
        f"/api/assets/{asset_id}/assign",
        headers=it_headers,
        json={
            "used_by": "Should Not Assign",
            "department": "IT",
            "workstation_no": "QA-BLOCKED",
            "work_mode": "office",
        },
    )
    assert blocked_assignment.status_code == 409
    assert "under repair" in blocked_assignment.json()["detail"].lower()

    detail = client.get(f"/api/assets/{asset_id}", headers=it_headers)
    assert detail.status_code == 200, detail.text
    actions = [item["action"] for item in detail.json()["history"]]
    assert "Laptop Handover" in actions
    assert "Laptop Transfer" in actions
    assert "Laptop Return" in actions
    assert "Asset returned" in actions

    deleted = client.delete(f"/api/assets/{asset_id}", headers=it_headers)
    assert deleted.status_code == 204


def test_batch3b1_asset_register_direct_assignment_and_transfer_clarity(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    tag = f"QA-B3B1-{uuid.uuid4().hex[:8].upper()}"

    created = client.post(
        "/api/assets",
        headers=it_headers,
        json={
            "device_type": "Laptop",
            "status": "assigned",
            "cpu_asset_tag": tag,
            "system_name": tag,
            "used_by": "QA Direct User One",
            "department": "IT",
            "workstation_no": "QA-B3B1-WS-01",
            "location": "3rd Floor",
            "work_mode": "office",
        },
    )
    assert created.status_code == 200, created.text
    asset = created.json()
    assert asset["status"] == "assigned"
    assert asset["used_by"] == "QA Direct User One"

    transferred = client.post(
        f"/api/assets/{asset['id']}/assign",
        headers=it_headers,
        json={
            "used_by": "QA Direct User Two",
            "department": "Software Development",
            "workstation_no": "QA-B3B1-WS-02",
            "location": "3rd Floor",
            "work_mode": "wfh",
            "remarks": "Batch 3B.1 direct Asset Register transfer",
        },
    )
    assert transferred.status_code == 200, transferred.text
    assert transferred.json()["used_by"] == "QA Direct User Two"
    assert transferred.json()["status"] == "wfh"

    detail = client.get(f"/api/assets/{asset['id']}", headers=it_headers)
    assert detail.status_code == 200, detail.text
    transfer_history = next(
        item for item in detail.json()["history"]
        if item.get("change_type") == "assignment_transfer" and "QA Direct User Two" in (item.get("new_value") or "")
    )
    assert "QA Direct User One" in (transfer_history.get("old_value") or "")
    assert transfer_history["action"] == "Asset assigned / transferred"

    returned = client.post(
        f"/api/assets/{asset['id']}/return",
        headers=it_headers,
        json={"final_status": "available", "condition": "working", "remarks": "Batch 3B.1 cleanup"},
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["used_by"] is None
    assert returned.json()["status"] == "available"

    deleted = client.delete(f"/api/assets/{asset['id']}", headers=it_headers)
    assert deleted.status_code == 204
