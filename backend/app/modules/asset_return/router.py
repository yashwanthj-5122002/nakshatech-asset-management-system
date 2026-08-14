from __future__ import annotations

from collections import Counter
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.api.router import (
    _asset_response,
    create_component_change_batch as base_create_component_change_batch,
    dashboard_summary as base_dashboard_summary,
    it_dashboard as base_it_dashboard,
    list_assets as base_list_assets,
)
from app.core.database import get_db
from app.models.entities import Asset, User
from app.modules.asset_return.component_spares import stage_spare_monitor_component_change
from app.modules.asset_return.reporting import (
    EXCEL_MIME,
    build_active_asset_report,
    build_active_complete_period_report,
    build_active_dashboard_report,
    build_active_monthly_asset_report,
    build_active_monthly_summary_report,
    build_asset_drilldown_workbook,
    build_vendor_return_workbook,
    query_active_asset_drilldown,
)
from app.modules.asset_return.schemas import AssetVendorReturnCreate
from app.modules.asset_return.service import (
    active_inventory_assets,
    list_spares,
    list_vendor_returns,
    perform_vendor_return,
)
from app.schemas.component_replacement import ComponentChangeBatchCreate
from app.services.asset_lifecycle_service import (
    device_distribution as canonical_device_distribution,
    inventory_integrity,
    inventory_summary,
    is_primary_device_type,
    lifecycle_status_distribution,
)
from app.services.monthly_snapshot_service import assets_for_month, available_months, month_start, parse_month_key
from app.services.periodic_reporting_service import monthly_period, yearly_period


router = APIRouter(tags=["Rental Asset Returns"])


@router.get("/assets")
def list_active_assets(
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    work_mode: str | None = None,
    month: str | None = Query(default=None, description="Asset register month in YYYY-MM format"),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    rows = base_list_assets(
        search=search,
        department=department,
        device_type=device_type,
        status=status,
        work_mode=work_mode,
        month=month,
        limit=limit,
        db=db,
        user=user,
    )
    return [row for row in rows if str(row.get("status") or "").strip().lower() != "returned_to_vendor"]


@router.get("/dashboard/summary")
def active_dashboard_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it", "drone")),
) -> dict:
    result = base_dashboard_summary(db=db, user=user)
    assets = active_inventory_assets(list(db.scalars(select(Asset)).all()))
    primary_assets = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    summary = inventory_summary(primary_assets)
    result["assets_total"] = summary["total"]
    result["available_assets"] = summary["available"]
    result["repair_assets"] = summary["repair"]
    return result


@router.get("/dashboard/it")
def active_it_dashboard(
    month: str | None = Query(default=None, description="Dashboard month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    result = base_it_dashboard(month=month, db=db, user=user)
    selected_start = parse_month_key(month) if month else month_start()
    assets, source = assets_for_month(db, selected_start)
    if source == "missing":
        raise HTTPException(status_code=404, detail="No asset register is available for the selected month")
    assets = active_inventory_assets(list(assets))
    primary_assets = [asset for asset in assets if is_primary_device_type(asset.device_type)]
    primary_summary = inventory_summary(primary_assets)
    all_summary = inventory_summary(assets)
    result["kpis"].update({
        "total": primary_summary["total"],
        "computers": primary_summary["computers"],
        "laptops": primary_summary["laptops"],
        "smartphones": primary_summary["smartphones"],
        "printers": primary_summary["printers"],
        "external_hdds": all_summary["external_hdds"],
        "assigned": primary_summary["assigned"],
        "available": primary_summary["available"],
        "repair": primary_summary["repair"],
        "replacement_pending": primary_summary["replacement_pending"],
        "wfh": primary_summary["wfh"],
        "field": primary_summary["field"],
        "returned": primary_summary["returned"],
        "damaged": primary_summary["damaged"],
        "servers": primary_summary["servers"],
        "network_devices": primary_summary["network_devices"],
        "other_primary": primary_summary["other"],
        "terminal": primary_summary["terminal"],
    })
    result["device_distribution"] = canonical_device_distribution(primary_assets)
    result["status_distribution"] = lifecycle_status_distribution(primary_assets)
    result["inventory_integrity"] = inventory_integrity(primary_assets, assets)
    result["department_distribution"] = [
        {"name": key, "value": value}
        for key, value in Counter(asset.department or "Unassigned" for asset in primary_assets).most_common(12)
    ]
    result["location_distribution"] = [
        {"name": key, "value": value}
        for key, value in Counter(asset.location or "Unknown" for asset in primary_assets).most_common(8)
    ]
    result["memory_distribution"] = [
        {"name": key, "value": value}
        for key, value in Counter(asset.memory_gb or "Not recorded" for asset in primary_assets).most_common(8)
    ]
    result["os_distribution"] = [
        {"name": key, "value": value}
        for key, value in Counter(asset.operating_system or "Not recorded" for asset in primary_assets).most_common(8)
    ]
    ip_counts = Counter(
        asset.ip_address
        for asset in primary_assets
        if asset.ip_address and asset.ip_address not in {"-", "Dynamic"}
    )
    duplicate_ips = sorted(ip for ip, count in ip_counts.items() if count > 1)
    approval_alerts = [item for item in result.get("alerts", []) if item.get("filter") == "approval_pending"]
    asset_alerts = [
        {"severity": "high", "title": "Replacement pending", "count": primary_summary["replacement_pending"], "filter": "replacement_pending"},
        {"severity": "high", "title": "Assets under repair", "count": primary_summary["repair"], "filter": "repair"},
        {"severity": "medium", "title": "Missing employee assignment", "count": sum(not asset.used_by for asset in primary_assets), "filter": "unassigned"},
        {"severity": "medium", "title": "MAC address not recorded", "count": sum(not asset.mac_address for asset in primary_assets), "filter": "missing_mac"},
        {"severity": "high", "title": "Duplicate IP addresses", "count": len(duplicate_ips), "details": duplicate_ips},
    ]
    result["alerts"] = [item for item in [*asset_alerts, *approval_alerts] if item.get("count", 0) > 0]
    return result


@router.get("/dashboard/it/assets")
def active_it_dashboard_asset_drilldown(
    month: str = Query(..., description="Reporting month in YYYY-MM format"),
    scope: str = Query(default="all", description="all, primary, device, status or department"),
    scope_value: str | None = None,
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    location: str | None = None,
    work_mode: str | None = None,
    ownership: str | None = None,
    client_name: str | None = None,
    project_id: str | None = None,
    current_holder: str | None = None,
    brand: str | None = None,
    capacity: str | None = None,
    sort_by: str = "asset_code",
    sort_dir: str = "asc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> dict:
    try:
        result = query_active_asset_drilldown(
            db,
            month_key=month,
            scope=scope,
            scope_value=scope_value,
            search=search,
            department=department,
            device_type=device_type,
            status=status,
            location=location,
            work_mode=work_mode,
            ownership=ownership,
            client_name=client_name,
            project_id=project_id,
            current_holder=current_holder,
            brand=brand,
            capacity=capacity,
            sort_by=sort_by,
            sort_dir=sort_dir,
            page=page,
            page_size=page_size,
        )
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if "No asset register" in detail else 400, detail=detail) from exc
    result["assets"] = [_asset_response(asset) for asset in result["assets"]]
    result.pop("all_filtered_assets", None)
    return result


@router.post("/assets/{asset_id}/vendor-return")
def return_rental_asset_to_vendor(
    asset_id: int,
    payload: AssetVendorReturnCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    return perform_vendor_return(db, asset_id, payload, user)


@router.get("/asset-vendor-returns")
def vendor_return_register(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    return list_vendor_returns(db)


@router.get("/spare-monitors")
def spare_monitor_register(
    status: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    return list_spares(db, status)


@router.post("/component-replacements/batch")
def create_component_change_batch_with_spares(
    payload: ComponentChangeBatchCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    try:
        stage_spare_monitor_component_change(db, payload, user)
        # The existing endpoint performs all normal validation/history creation
        # and commits the same Session, including the staged spare-monitor state.
        return base_create_component_change_batch(payload=payload, db=db, user=user)
    except Exception:
        db.rollback()
        raise


@router.get("/reports/returned-assets.xlsx")
def returned_assets_excel(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_vendor_return_workbook(db)
    return StreamingResponse(
        stream,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": 'attachment; filename="NakshaTech Returned Rental Assets.xlsx"'},
    )


@router.get("/reports/it-dashboard-assets.xlsx")
def active_it_dashboard_asset_excel(
    month: str = Query(...),
    scope: str = "all",
    scope_value: str | None = None,
    search: str | None = None,
    department: str | None = None,
    device_type: str | None = None,
    status: str | None = None,
    location: str | None = None,
    work_mode: str | None = None,
    ownership: str | None = None,
    client_name: str | None = None,
    project_id: str | None = None,
    current_holder: str | None = None,
    brand: str | None = None,
    capacity: str | None = None,
    sort_by: str = "asset_code",
    sort_dir: str = "asc",
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    try:
        result = query_active_asset_drilldown(
            db, month_key=month, scope=scope, scope_value=scope_value, search=search,
            department=department, device_type=device_type, status=status, location=location,
            work_mode=work_mode, ownership=ownership, client_name=client_name, project_id=project_id,
            current_holder=current_holder, brand=brand, capacity=capacity, sort_by=sort_by, sort_dir=sort_dir,
            page=1, page_size=100,
        )
        stream = build_asset_drilldown_workbook(result)
    except ValueError as exc:
        detail = str(exc)
        raise HTTPException(status_code=404 if "No asset register" in detail else 400, detail=detail) from exc
    filename = f"NakshaTech Active {result['scope']['label']} - {result['month']['label']}.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/monthly-assets.xlsx")
def active_monthly_assets_excel(
    month: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    start = parse_month_key(month)
    stream = build_active_monthly_asset_report(db, month)
    filename = f"NakshaTech Asset Register - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/monthly-summary.xlsx")
def active_monthly_summary_excel(
    month: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    start = parse_month_key(month)
    stream = build_active_monthly_summary_report(db, month)
    filename = f"NakshaTech Monthly Asset Summary - {start.strftime('%B %Y')}.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/nakshatech-assets.xlsx")
def active_master_asset_excel(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_active_asset_report(db)
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": 'attachment; filename="NakshaTech Active Asset Details.xlsx"'})


@router.get("/reports/assets.xlsx")
def active_legacy_asset_excel(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    return active_master_asset_excel(db=db, user=user)


@router.get("/reports/dashboard.xlsx")
def active_dashboard_excel(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    stream = build_active_dashboard_report(db)
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": 'attachment; filename="NakshaTech Active IT Dashboard.xlsx"'})


@router.get("/reports/complete-monthly.xlsx")
def active_complete_monthly_excel(
    month: str = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    period = monthly_period(month)
    stream = build_active_complete_period_report(db, period)
    filename = f"NakshaTech Complete IT Report - {period.label}.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/complete-yearly.xlsx")
def active_complete_yearly_excel(
    year: int = Query(..., ge=2000, le=2100),
    period_type: str = Query(default="calendar", alias="period"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> StreamingResponse:
    period = yearly_period(year, period_type)
    stream = build_active_complete_period_report(db, period)
    filename = f"NakshaTech Complete IT Report - {period.label}.xlsx"
    return StreamingResponse(stream, media_type=EXCEL_MIME, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/reports/months")
def active_report_months(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it")),
) -> list[dict]:
    rows = available_months(db)
    for row in rows:
        if row.get("source") != "system_snapshot":
            continue
        try:
            start = parse_month_key(row["key"])
            assets, source = assets_for_month(db, start)
            if source != "missing":
                row["closing_count"] = len(active_inventory_assets(list(assets)))
            previous = (start - timedelta(days=1)).replace(day=1)
            previous_assets, previous_source = assets_for_month(db, previous)
            if previous_source != "missing":
                row["opening_count"] = len(active_inventory_assets(list(previous_assets)))
        except ValueError:
            continue
    return rows
