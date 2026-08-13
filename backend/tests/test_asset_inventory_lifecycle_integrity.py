from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import app.services.asset_drilldown_service as drilldown_service
from app.services.asset_lifecycle_service import (
    canonical_device_type,
    device_distribution,
    inventory_integrity,
    inventory_summary,
    is_primary_device_type,
    lifecycle_status_distribution,
    status_matches,
)
from app.services.excel_import_service import _device_type
from app.services.periodic_reporting_service import _asset_summary_row


def _asset(device_type: str, status: str, *, asset_code: str, ownership: str | None = None):
    return SimpleNamespace(
        id=1,
        asset_code=asset_code,
        device_type=device_type,
        status=status,
        ownership=ownership,
        department="IT",
        location="Head Office",
        work_mode="office",
    )


def _sample_assets():
    return [
        _asset("Desktop", "wfh", asset_code="A-01"),
        _asset("Computer", "available", asset_code="A-02"),
        _asset("Notebook", "field_deployment", asset_code="A-03"),
        _asset("Printer", "under_inspection", asset_code="A-04"),
        _asset("Server", "replacement_pending", asset_code="A-05"),
        _asset("Network Equipment", "retired", asset_code="A-06"),
        _asset("Legacy Peripheral", "disposed", asset_code="A-07"),
        _asset("External Hard Drive", "issued", asset_code="H-01", ownership="NakshaTech"),
    ]


def test_authoritative_device_and_lifecycle_counts_reconcile() -> None:
    assets = _sample_assets()
    primary = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    summary = inventory_summary(primary)
    integrity = inventory_integrity(primary, assets)

    assert canonical_device_type("desktop") == "Computer"
    assert canonical_device_type("notebook") == "Laptop"
    assert canonical_device_type("network equipment") == "Network Device"
    assert canonical_device_type("Legacy Peripheral") == "Other"
    assert _device_type("Desktop PC") == "Computer"
    assert _device_type("External Hard Disk") == "External HDD"

    assert summary["total"] == 7
    assert summary["computers"] == 2
    assert summary["laptops"] == 1
    assert summary["printers"] == 1
    assert summary["servers"] == 1
    assert summary["network_devices"] == 1
    assert summary["other"] == 1
    assert summary["assigned"] == 2
    assert summary["available"] == 1
    assert summary["repair"] == 1
    assert summary["replacement_pending"] == 1
    assert summary["terminal"] == 2

    assert integrity["tracked_records"] == 8
    assert integrity["primary_records"] == 7
    assert integrity["external_hdd_records"] == 1
    assert integrity["device_breakdown_total"] == 7
    assert integrity["lifecycle_breakdown_total"] == 7
    assert integrity["device_reconciled"] is True
    assert integrity["lifecycle_reconciled"] is True

    assert status_matches("wfh", "assigned") is True
    assert status_matches("field_deployment", "assigned") is True
    assert status_matches("under_inspection", "repair") is True


def test_dashboard_distribution_and_drilldown_use_the_same_classification(monkeypatch) -> None:
    assets = _sample_assets()
    current_key = drilldown_service.month_start().strftime("%Y-%m")
    monkeypatch.setattr(drilldown_service, "assets_for_month", lambda db, start: (assets, "live"))

    primary = drilldown_service.query_asset_drilldown(
        object(), month_key=current_key, scope="primary", page=1, page_size=100
    )
    computer = drilldown_service.query_asset_drilldown(
        object(), month_key=current_key, scope="device", scope_value="Computer", page=1, page_size=100
    )
    repair = drilldown_service.query_asset_drilldown(
        object(), month_key=current_key, scope="status", scope_value="repair", page=1, page_size=100
    )

    assert primary["scope_total"] == 7
    assert primary["summary"]["total"] == 7
    assert primary["summary"]["computers"] == 2
    assert sum(item["value"] for item in primary["visuals"]["device_distribution"]) == 7
    assert sum(item["value"] for item in primary["visuals"]["status_distribution"]) == 7
    assert computer["scope_total"] == 2
    assert {asset.asset_code for asset in computer["all_filtered_assets"]} == {"A-01", "A-02"}
    assert repair["scope_total"] == 1
    assert repair["all_filtered_assets"][0].asset_code == "A-04"


def test_periodic_report_monthly_totals_match_authoritative_inventory() -> None:
    assets = _sample_assets()
    row = _asset_summary_row(date(2026, 8, 1), assets, "live")

    assert row["Primary IT Assets"] == 7
    assert row["Computers"] == 2
    assert row["Laptops"] == 1
    assert row["Printers"] == 1
    assert row["External HDDs"] == 1
    assert row["Assigned / In Use"] == 2
    assert row["Available"] == 1
    assert row["Under Repair"] == 1
    assert row["Replacement Pending"] == 1
    assert row["All Asset Rows"] == 8


def test_distributions_do_not_drop_unknown_devices_or_legacy_statuses() -> None:
    assets = _sample_assets() + [_asset("Computer", "legacy_hold", asset_code="A-08")]
    primary = [asset for asset in assets if is_primary_device_type(asset.device_type)]

    devices = device_distribution(primary)
    statuses = lifecycle_status_distribution(primary)

    assert sum(item["value"] for item in devices) == len(primary)
    assert sum(item["value"] for item in statuses) == len(primary)
    assert next(item for item in devices if item["name"] == "Other")["value"] == 1
    assert next(item for item in statuses if item["key"] == "other")["value"] == 1
