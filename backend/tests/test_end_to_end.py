from __future__ import annotations

from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

TEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_asset_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"
os.environ["JWT_SECRET"] = "test-secret-only-change-me-32-characters"
os.environ["LOCAL_BACKUP_AGENT_ENABLED"] = "true"
os.environ["LOCAL_BACKUP_AGENT_TOKEN"] = "test-local-backup-token-abcdefghijklmnopqrstuvwxyz-123456"
os.environ["BACKUP_TIMEZONE"] = "Asia/Kolkata"

from app.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client
    TEST_DB.unlink(missing_ok=True)


def login(client: TestClient, role: str, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"role": role, "email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["role"] == role
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


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


def test_work_and_replacement_workflows(client: TestClient) -> None:
    it_headers = login(client, "it", "it@nakshatech.com", "IT@123456")
    management_headers = login(client, "management", "management@nakshatech.com", "Manager@123")
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
    assert client.patch(f"/api/work-records/{work_id}", headers=it_headers, json={"status": "in_progress"}).status_code == 200
    completed = client.patch(
        f"/api/work-records/{work_id}",
        headers=it_headers,
        json={"status": "completed", "approval_status": "pending", "resolution": "Inspection completed"},
    )
    assert completed.status_code == 200
    closed = client.patch(
        f"/api/work-records/{work_id}",
        headers=management_headers,
        json={"status": "closed", "approval_status": "approved"},
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["approval_status"] == "approved"

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
    assert replacement.json()["approval_status"] == "pending"
    approved = client.patch(
        f"/api/replacements/{replacement.json()['id']}",
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



def test_employee_registration_authenticator_branch_and_ticket_routing(client: TestClient) -> None:
    from urllib.parse import parse_qs, urlparse

    from app.core.config import settings
    from app.modules.employee_portal.service import totp_code

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
    secret = parse_qs(urlparse(setup["otpauth_uri"]).query)["secret"][0]

    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={"mfa_setup_token": setup["mfa_setup_token"], "code": totp_code(secret)},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["branch_selection_required"] is True

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

    created = client.post(
        "/api/tickets",
        headers=employee_headers,
        json={
            "department": "it",
            "title": "Portal test laptop issue",
            "description": "The test laptop cannot connect to the office network.",
            "priority": "high",
            "location": "Head Office",
        },
    )
    assert created.status_code == 200, created.text
    ticket_id = created.json()["id"]

    it_headers = login(client, "it", settings.seed_it_email, settings.seed_it_password)
    it_queue = client.get("/api/tickets", headers=it_headers)
    assert it_queue.status_code == 200
    assert any(item["id"] == ticket_id for item in it_queue.json())

    drone_headers = login(client, "drone", settings.seed_drone_email, settings.seed_drone_password)
    drone_queue = client.get("/api/tickets", headers=drone_headers)
    assert drone_queue.status_code == 200
    assert all(item["id"] != ticket_id for item in drone_queue.json())

    software_headers = login(client, "software_team", settings.seed_admin_email, settings.seed_admin_password)
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
    assert returning.json()["requires_mfa"] is True
    verified_login = client.post(
        "/api/auth/mfa/verify-login",
        json={"pre_auth_token": returning.json()["pre_auth_token"], "code": totp_code(secret)},
    )
    assert verified_login.status_code == 200
    assert verified_login.json()["branch_selection_required"] is True


def test_employee_password_reset_and_software_ticket_handling(client: TestClient) -> None:
    from urllib.parse import parse_qs, urlparse

    from app.core.config import settings
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
    secret = parse_qs(urlparse(completed.json()["otpauth_uri"]).query)["secret"][0]
    confirmed = client.post(
        "/api/auth/mfa/confirm",
        json={
            "mfa_setup_token": completed.json()["mfa_setup_token"],
            "code": totp_code(secret),
        },
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
    assert returning.json()["requires_mfa"] is True
    verified_login = client.post(
        "/api/auth/mfa/verify-login",
        json={"pre_auth_token": returning.json()["pre_auth_token"], "code": totp_code(secret)},
    )
    assert verified_login.status_code == 200, verified_login.text

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
