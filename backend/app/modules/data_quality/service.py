from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    AssetHistory,
    ComponentReplacement,
    MonthlyAssetSnapshot,
    MonthlySnapshotRun,
    ReplacementRecord,
    WorkRecord,
)
from app.modules.data_quality.schemas import DataQualityIssue, DataQualityRecord, DataQualitySummaryResponse
from app.modules.it_activity.models import ITHandoverRecord, ITPurchaseRecord, ITPurchaseRequest
from app.services.monthly_snapshot_service import (
    assets_for_month,
    month_start,
    next_month,
    parse_month_key,
    template_months,
)

PRIMARY_EXCLUDED_DEVICE_TYPES = {"external hdd"}
ASSIGNED_STATUSES = {"assigned", "in_use", "wfh", "field_deployment", "issued", "permanently_issued"}
FINAL_STATUSES = {"replaced", "retired", "disposed", "missing", "returned"}
VALID_STATUSES = {
    "available", "assigned", "in_use", "wfh", "field_deployment", "under_inspection", "repair",
    "replacement_pending", "replaced", "damaged", "beyond_repair", "returned", "missing", "retired",
    "for_parts", "disposal_pending", "disposed", "issued", "permanently_issued",
}
PLACEHOLDER_SERIALS = {"", "-", "--", "na", "n/a", "nil", "none", "unknown", "not available"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalized(value: Any) -> str:
    return " ".join(_text(value).casefold().split())


def _holder(asset: Any) -> str:
    return _text(getattr(asset, "current_holder", None) or getattr(asset, "used_by", None))


def _asset_record(
    asset: Any,
    *,
    current_value: str | None = None,
    expected_value: str | None = None,
    note: str | None = None,
) -> DataQualityRecord:
    return DataQualityRecord(
        record_type="asset",
        record_id=str(getattr(asset, "id", "")),
        asset_code=_text(getattr(asset, "asset_code", None)) or None,
        device_type=_text(getattr(asset, "device_type", None)) or None,
        status=_text(getattr(asset, "status", None)) or None,
        department=_text(getattr(asset, "department", None)) or None,
        serial_number=_text(getattr(asset, "serial_number", None)) or None,
        current_value=current_value,
        expected_value=expected_value,
        note=note,
    )


def _issue(
    code: str,
    title: str,
    severity: str,
    scope: str,
    description: str,
    records: Iterable[DataQualityRecord],
    *,
    count: int | None = None,
) -> DataQualityIssue | None:
    rows = list(records)
    total = len(rows) if count is None else count
    if total <= 0:
        return None
    return DataQualityIssue(
        code=code,
        title=title,
        severity=severity,  # type: ignore[arg-type]
        scope=scope,
        description=description,
        count=total,
        records=rows,
    )


def _missing_month_filter(column):
    return or_(column.is_(None), func.trim(column) == "")


def _month_range(first: date, last: date) -> list[date]:
    values: list[date] = []
    cursor = first.replace(day=1)
    end = last.replace(day=1)
    while cursor <= end:
        values.append(cursor)
        cursor = next_month(cursor)
    return values


def _historical_missing_month_records(db: Session, selected_start: date, selected_source: str) -> list[DataQualityRecord]:
    available = {item["key"] for item in template_months()}
    available.update(
        snapshot_month.strftime("%Y-%m")
        for snapshot_month in db.scalars(select(MonthlySnapshotRun.month_start)).all()
    )
    current = month_start()
    available.add(current.strftime("%Y-%m"))

    parsed = sorted(parse_month_key(key) for key in available)
    missing: list[date] = []
    if parsed:
        missing = [item for item in _month_range(parsed[0], current) if item.strftime("%Y-%m") not in available]

    if selected_source == "missing" and selected_start not in missing:
        missing.append(selected_start)
        missing.sort()

    return [
        DataQualityRecord(
            record_type="reporting_month",
            record_id=item.strftime("%Y-%m"),
            current_value="No historical asset register or finalized snapshot",
            expected_value="Historical workbook sheet or finalized system snapshot",
            note=item.strftime("%B %Y"),
        )
        for item in missing
    ]


def _missing_reporting_month_issue(db: Session) -> DataQualityIssue | None:
    definitions = [
        (AssetHistory, AssetHistory.reporting_month, "Asset history", AssetHistory.id, AssetHistory.asset_id),
        (WorkRecord, WorkRecord.reporting_month, "IT work record", WorkRecord.id, WorkRecord.work_code),
        (ComponentReplacement, ComponentReplacement.reporting_month, "Component change", ComponentReplacement.id, ComponentReplacement.replacement_code),
        (ReplacementRecord, ReplacementRecord.reporting_month, "Full replacement", ReplacementRecord.id, ReplacementRecord.replacement_code),
        (ITHandoverRecord, ITHandoverRecord.reporting_month, "Handover / return", ITHandoverRecord.id, ITHandoverRecord.activity_code),
        (ITPurchaseRecord, ITPurchaseRecord.reporting_month, "Purchase", ITPurchaseRecord.id, ITPurchaseRecord.purchase_code),
        (ITPurchaseRequest, ITPurchaseRequest.reporting_month, "Purchase request", ITPurchaseRequest.id, ITPurchaseRequest.request_code),
    ]

    records: list[DataQualityRecord] = []
    total = 0
    for model, month_column, label, id_column, reference_column in definitions:
        filters = [_missing_month_filter(month_column)]
        if model is WorkRecord:
            filters.append(WorkRecord.module == "it")
        count = db.scalar(select(func.count(id_column)).where(*filters)) or 0
        total += int(count)
        rows = db.execute(
            select(id_column, reference_column).where(*filters).order_by(id_column).limit(100)
        ).all()
        records.extend(
            DataQualityRecord(
                record_type=label,
                record_id=str(row[0]),
                current_value="Missing",
                expected_value="YYYY-MM",
                note=f"Reference: {row[1]}" if row[1] is not None else None,
            )
            for row in rows
        )

    return _issue(
        "missing_reporting_month",
        "Records missing reporting month",
        "high",
        "all_it_records",
        "Records without an explicit reporting month can appear in the wrong monthly or yearly analysis. The centre reports them but never modifies them.",
        records,
        count=total,
    )


def build_data_quality_summary(db: Session, month_key: str) -> DataQualitySummaryResponse:
    selected_start = parse_month_key(month_key)
    selected_key = selected_start.strftime("%Y-%m")
    assets, source = assets_for_month(db, selected_start)
    is_live = selected_start == month_start()
    data_available = source != "missing"

    all_assets = list(assets)
    primary_assets = [
        asset for asset in all_assets
        if _normalized(getattr(asset, "device_type", None)) not in PRIMARY_EXCLUDED_DEVICE_TYPES
    ]
    external_hdds = [
        asset for asset in all_assets
        if _normalized(getattr(asset, "device_type", None)) in PRIMARY_EXCLUDED_DEVICE_TYPES
    ]

    issues: list[DataQualityIssue] = []

    missing_departments = [
        _asset_record(asset, current_value="Blank", expected_value="Department name")
        for asset in primary_assets
        if not _text(getattr(asset, "department", None))
    ]
    issue = _issue(
        "missing_departments",
        "Missing departments",
        "medium",
        selected_key,
        "Primary IT assets without a department reduce the accuracy of department charts and reports.",
        missing_departments,
    )
    if issue:
        issues.append(issue)

    serial_groups: dict[str, list[Any]] = defaultdict(list)
    serial_display: dict[str, str] = {}
    for asset in all_assets:
        raw = _text(getattr(asset, "serial_number", None))
        key = _normalized(raw)
        if key in PLACEHOLDER_SERIALS:
            continue
        serial_groups[key].append(asset)
        serial_display.setdefault(key, raw)
    duplicate_serial_records: list[DataQualityRecord] = []
    duplicate_group_count = 0
    for key, group in sorted(serial_groups.items()):
        if len(group) < 2:
            continue
        duplicate_group_count += 1
        duplicate_serial_records.extend(
            _asset_record(
                asset,
                current_value=serial_display[key],
                expected_value="Unique serial number",
                note=f"Used by {len(group)} asset records",
            )
            for asset in group
        )
    issue = _issue(
        "duplicate_serial_numbers",
        "Duplicate serial numbers",
        "high",
        selected_key,
        "The same non-placeholder serial number is assigned to more than one asset record.",
        duplicate_serial_records,
    )
    if issue:
        issue.description += f" Duplicate groups detected: {duplicate_group_count}."
        issues.append(issue)

    missing_identifier_records: list[DataQualityRecord] = []
    for asset in all_assets:
        asset_code = _text(getattr(asset, "asset_code", None))
        device_type = _normalized(getattr(asset, "device_type", None))
        cpu_tag = _text(getattr(asset, "cpu_asset_tag", None))
        if not asset_code:
            missing_identifier_records.append(
                _asset_record(asset, current_value="Asset code missing", expected_value="Unique asset code")
            )
            continue
        if device_type in {"computer", "laptop", "printer"} and not cpu_tag:
            missing_identifier_records.append(
                _asset_record(asset, current_value="Primary asset tag missing", expected_value="CPU / printer asset tag")
            )
    issue = _issue(
        "missing_asset_identifiers",
        "Missing asset IDs or tags",
        "high",
        selected_key,
        "Computers, laptops and printers require a usable primary asset identifier for traceability.",
        missing_identifier_records,
    )
    if issue:
        issues.append(issue)

    assigned_without_holder: list[DataQualityRecord] = []
    invalid_status_records: list[DataQualityRecord] = []
    for asset in all_assets:
        status = _normalized(getattr(asset, "status", None)) or "available"
        holder = _holder(asset)
        work_mode = _normalized(getattr(asset, "work_mode", None)) or "office"
        if status in ASSIGNED_STATUSES and not holder:
            assigned_without_holder.append(
                _asset_record(asset, current_value=f"Status: {status}; holder: blank", expected_value="Assigned holder")
            )
        reasons: list[str] = []
        if status not in VALID_STATUSES:
            reasons.append(f"Unknown status '{status}'")
        if status == "available" and holder:
            reasons.append("Available asset still has a holder")
        if status in FINAL_STATUSES and holder:
            reasons.append(f"Final status '{status}' still has a holder")
        if status == "wfh" and work_mode != "wfh":
            reasons.append("WFH status does not match work mode")
        if status == "field_deployment" and work_mode != "field":
            reasons.append("Field deployment status does not match work mode")
        if reasons:
            invalid_status_records.append(
                _asset_record(
                    asset,
                    current_value="; ".join(reasons),
                    expected_value="Consistent status, holder and work mode",
                )
            )

    issue = _issue(
        "assigned_without_holders",
        "Assigned assets without holders",
        "high",
        selected_key,
        "Assets in an assigned or deployed status must identify a current holder.",
        assigned_without_holder,
    )
    if issue:
        issues.append(issue)

    issue = _issue(
        "invalid_status_combinations",
        "Invalid status combinations",
        "medium",
        selected_key,
        "Status, holder and work-mode values contradict one another or use an unsupported status.",
        invalid_status_records,
    )
    if issue:
        issues.append(issue)

    missing_month_records = _historical_missing_month_records(db, selected_start, source)
    issue = _issue(
        "historical_months_missing_data",
        "Historical months with missing data",
        "medium",
        "historical_coverage",
        "Months without a historical workbook sheet or finalized system snapshot cannot produce a verified month-end asset position.",
        missing_month_records,
    )
    if issue:
        issues.append(issue)

    availability_records: list[DataQualityRecord] = []
    if source in {"template", "missing"}:
        reason = (
            "The historical workbook does not contain a dedicated register for this asset type."
            if source == "template"
            else "No asset register or finalized snapshot exists for the selected month."
        )
        for asset_type in ("Printer", "External HDD"):
            availability_records.append(
                DataQualityRecord(
                    record_type="asset_register",
                    record_id=f"{selected_key}:{asset_type}",
                    device_type=asset_type,
                    current_value="Data unavailable",
                    expected_value="Historical register or finalized snapshot",
                    note=reason,
                )
            )
    issue = _issue(
        "printer_hdd_data_unavailable",
        "Printer / External HDD data unavailable",
        "medium",
        selected_key,
        "A displayed zero is valid only when the selected source actually contains Printer and External HDD records.",
        availability_records,
    )
    if issue:
        issues.append(issue)

    device_counts = Counter(_text(getattr(asset, "device_type", None)) or "Not recorded" for asset in primary_assets)
    status_counts = Counter(_text(getattr(asset, "status", None)) or "Not recorded" for asset in primary_assets)
    department_counts = Counter(_text(getattr(asset, "department", None)) or "Department Not Set" for asset in primary_assets)
    dashboard_department_visible = sum(value for _, value in department_counts.most_common(12))

    reconciliation_records: list[DataQualityRecord] = []
    primary_total = len(primary_assets)
    all_total = len(all_assets)
    if sum(device_counts.values()) != primary_total:
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="device_distribution",
            current_value=str(sum(device_counts.values())),
            expected_value=str(primary_total),
            note="Device distribution must equal Total IT Assets.",
        ))
    if sum(status_counts.values()) != primary_total:
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="status_distribution",
            current_value=str(sum(status_counts.values())),
            expected_value=str(primary_total),
            note="Status distribution must equal Total IT Assets.",
        ))
    if sum(department_counts.values()) != primary_total:
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="department_distribution",
            current_value=str(sum(department_counts.values())),
            expected_value=str(primary_total),
            note="Department distribution including Department Not Set must equal Total IT Assets.",
        ))
    if dashboard_department_visible != primary_total:
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="dashboard_department_visible",
            current_value=str(dashboard_department_visible),
            expected_value=str(primary_total),
            note="The current dashboard top-12 department chart omits part of the selected asset population.",
        ))
    if primary_total + len(external_hdds) != all_total:
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="all_asset_records",
            current_value=str(primary_total + len(external_hdds)),
            expected_value=str(all_total),
            note="Primary IT Assets plus External HDDs must equal all asset records.",
        ))

    snapshot_closing_count: int | None = None
    if source == "snapshot":
        run = db.scalar(select(MonthlySnapshotRun).where(MonthlySnapshotRun.month_start == selected_start))
        if run:
            snapshot_closing_count = int(run.closing_count or 0)
            snapshot_row_count = db.scalar(
                select(func.count(MonthlyAssetSnapshot.id)).where(MonthlyAssetSnapshot.run_id == run.id)
            ) or 0
            if int(snapshot_row_count) != snapshot_closing_count:
                reconciliation_records.append(DataQualityRecord(
                    record_type="reconciliation",
                    record_id="snapshot_closing_count",
                    current_value=str(snapshot_closing_count),
                    expected_value=str(snapshot_row_count),
                    note="Snapshot metadata closing count must equal stored snapshot rows.",
                ))

    if source == "missing":
        reconciliation_records.append(DataQualityRecord(
            record_type="reconciliation",
            record_id="selected_month_source",
            current_value="No data source",
            expected_value="Live register, finalized snapshot or historical workbook",
            note="Selected-month totals cannot be reconciled without a source register.",
        ))

    issue = _issue(
        "unreconciled_totals",
        "Unreconciled totals",
        "high",
        selected_key,
        "Dashboard totals, chart distributions and snapshot metadata must reconcile to the same selected-month asset population.",
        reconciliation_records,
    )
    if issue:
        issues.append(issue)

    missing_reporting_month_issue = _missing_reporting_month_issue(db)
    if missing_reporting_month_issue:
        issues.append(missing_reporting_month_issue)

    issues.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2, "info": 3}[item.severity], item.title))
    finding_count = sum(item.count for item in issues)
    high_findings = sum(item.count for item in issues if item.severity == "high")

    return DataQualitySummaryResponse(
        checked_at=datetime.now(timezone.utc).isoformat(),
        month={
            "key": selected_key,
            "label": selected_start.strftime("%B %Y"),
            "source": source,
            "status": "live" if is_live else ("finalized" if source == "snapshot" else ("historical" if source == "template" else "missing")),
            "is_live": is_live,
            "data_available": data_available,
        },
        metrics={
            "issue_groups": len(issues),
            "findings": finding_count,
            "high_findings": high_findings,
            "primary_it_assets": primary_total,
            "printers": device_counts.get("Printer", 0),
            "external_hdds": len(external_hdds),
            "all_asset_records": all_total,
        },
        reconciliation={
            "primary_it_assets": primary_total,
            "device_distribution_total": sum(device_counts.values()),
            "status_distribution_total": sum(status_counts.values()),
            "department_distribution_total": sum(department_counts.values()),
            "dashboard_department_visible_total": dashboard_department_visible,
            "external_hdds": len(external_hdds),
            "all_asset_records": all_total,
            "snapshot_closing_count": snapshot_closing_count if snapshot_closing_count is not None else "not_applicable",
            "reconciled": len(reconciliation_records) == 0,
        },
        issues=issues,
    )
