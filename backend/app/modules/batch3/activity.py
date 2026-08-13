from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ApprovalDecisionHistory, Asset, AssetHistory, ReplacementRecord, WorkRecord
from app.modules.it_activity.models import ITPurchaseRequest
from app.modules.it_activity.service import local_datetime, month_bounds, monthly_activity_data
from app.services.approval_workflow_service import WORKFLOW_IT_WORK, WORKFLOW_PURCHASE_REQUEST, WORKFLOW_REPLACEMENT

def _approval_row(
    history: ApprovalDecisionHistory,
    *,
    reporting_month: str,
    label: str,
    asset: Asset | None = None,
) -> dict[str, Any]:
    local = local_datetime(history.created_at)
    return {
        "activity_id": f"approval-{history.id}",
        "source_type": "approval",
        "record_id": history.id,
        "asset_id": asset.id if asset else None,
        "asset_code": asset.asset_code if asset else None,
        "cpu_asset_tag": asset.cpu_asset_tag if asset else None,
        "workstation_no": asset.workstation_no if asset else None,
        "device_category": asset.device_type if asset else "workflow",
        "department": asset.department if asset else None,
        "action_type": f"{history.workflow_type}_{history.action}",
        "action_label": f"{label} · {history.action.replace('_', ' ').title()}",
        "field_or_component": "Approval Workflow",
        "old_value": history.from_status,
        "new_value": history.to_status,
        "reason": history.remarks,
        "remarks": history.remarks,
        "performed_by": history.performed_by_name,
        "performed_by_email": history.performed_by_email,
        "performed_by_role": history.performed_by_role,
        "batch_code": history.record_code,
        "reporting_month": reporting_month,
        "system_recorded_at": local.isoformat() if local else None,
        "activity_date": local.date().isoformat() if local else None,
        "activity_time": local.strftime("%I:%M:%S %p") if local else None,
        "timestamp": local.isoformat() if local else None,
        "time_recorded": True,
    }


def _asset_created_row(history: AssetHistory, asset: Asset | None) -> dict[str, Any]:
    local = local_datetime(history.created_at)
    return {
        "activity_id": f"asset-created-{history.id}",
        "source_type": "asset_created",
        "record_id": history.id,
        "asset_id": history.asset_id,
        "asset_code": asset.asset_code if asset else None,
        "cpu_asset_tag": asset.cpu_asset_tag if asset else None,
        "workstation_no": asset.workstation_no if asset else None,
        "device_category": asset.device_type if asset else None,
        "department": asset.department if asset else None,
        "action_type": "asset_created",
        "action_label": history.action or "Asset Created",
        "field_or_component": "Asset Register",
        "old_value": None,
        "new_value": history.new_value,
        "reason": history.reason,
        "remarks": history.remarks,
        "performed_by": history.changed_by_name or history.changed_by,
        "performed_by_email": history.changed_by,
        "performed_by_role": history.changed_by_role,
        "batch_code": history.batch_code,
        "reporting_month": history.reporting_month or (local.strftime("%Y-%m") if local else None),
        "system_recorded_at": local.isoformat() if local else None,
        "activity_date": local.date().isoformat() if local else None,
        "activity_time": local.strftime("%I:%M:%S %p") if local else None,
        "timestamp": local.isoformat() if local else None,
        "time_recorded": True,
    }


def _unlinked_work_row(work: WorkRecord, reporting_month: str) -> dict[str, Any]:
    local = local_datetime(work.created_at)
    return {
        "activity_id": f"it-work-{work.id}",
        "source_type": "it_work",
        "record_id": work.id,
        "asset_id": None,
        "asset_code": None,
        "cpu_asset_tag": None,
        "workstation_no": None,
        "device_category": "IT Work",
        "department": None,
        "action_type": "it_work_record",
        "action_label": f"IT Work · {work.status.replace('_', ' ').title()}",
        "field_or_component": work.work_type,
        "old_value": None,
        "new_value": work.title,
        "reason": work.issue_description or work.details,
        "remarks": work.resolution,
        "performed_by": work.submitted_by_name or work.technician or work.assigned_to,
        "performed_by_email": work.submitted_by_email,
        "performed_by_role": work.submitted_by_role,
        "batch_code": work.work_code,
        "reporting_month": reporting_month,
        "system_recorded_at": local.isoformat() if local else None,
        "activity_date": local.date().isoformat() if local else None,
        "activity_time": local.strftime("%I:%M:%S %p") if local else None,
        "timestamp": local.isoformat() if local else None,
        "time_recorded": True,
    }


def complete_monthly_activity_data(
    db: Session,
    month_key: str,
    *,
    department: str | None = None,
    device_category: str | None = None,
    changed_by: str | None = None,
    action_type: str | None = None,
    search: str | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    base = monthly_activity_data(db, month_key, limit=5000)
    _start_date, _end_date, utc_start, utc_end = month_bounds(month_key)

    created_histories = list(db.scalars(
        select(AssetHistory).where(
            AssetHistory.change_type == "asset_created",
            or_(
                AssetHistory.reporting_month == month_key,
                and_(
                    or_(AssetHistory.reporting_month.is_(None), func.trim(AssetHistory.reporting_month) == ""),
                    AssetHistory.created_at >= utc_start,
                    AssetHistory.created_at < utc_end,
                ),
            ),
        )
    ).all())
    asset_ids = {row.asset_id for row in created_histories}
    assets = {asset.id: asset for asset in db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}
    extras = [_asset_created_row(row, assets.get(row.asset_id)) for row in created_histories]

    work_records = list(db.scalars(select(WorkRecord).where(
        WorkRecord.module == "it",
        or_(
            WorkRecord.reporting_month == month_key,
            and_(WorkRecord.reporting_month.is_(None), WorkRecord.created_at >= utc_start, WorkRecord.created_at < utc_end),
        ),
    )).all())
    replacements = list(db.scalars(select(ReplacementRecord).where(or_(
        ReplacementRecord.reporting_month == month_key,
        and_(ReplacementRecord.reporting_month.is_(None), ReplacementRecord.created_at >= utc_start, ReplacementRecord.created_at < utc_end),
    ))).all())
    purchase_requests = list(db.scalars(select(ITPurchaseRequest).where(or_(
        ITPurchaseRequest.reporting_month == month_key,
        and_(ITPurchaseRequest.reporting_month.is_(None), ITPurchaseRequest.requested_at >= utc_start, ITPurchaseRequest.requested_at < utc_end),
    ))).all())

    work_map = {row.id: row for row in work_records}
    replacement_map = {row.id: row for row in replacements}
    purchase_map = {row.id: row for row in purchase_requests}
    approval_groups = (
        (WORKFLOW_IT_WORK, work_map, "IT Work"),
        (WORKFLOW_REPLACEMENT, replacement_map, "Replacement"),
        (WORKFLOW_PURCHASE_REQUEST, purchase_map, "Purchase Request"),
    )
    for workflow_type, records, label in approval_groups:
        if not records:
            continue
        histories = db.scalars(select(ApprovalDecisionHistory).where(
            ApprovalDecisionHistory.workflow_type == workflow_type,
            ApprovalDecisionHistory.record_id.in_(list(records)),
        )).all()
        for history in histories:
            record = records.get(history.record_id)
            asset = None
            if workflow_type == WORKFLOW_IT_WORK and record and record.asset_id:
                asset = db.get(Asset, record.asset_id)
            elif workflow_type == WORKFLOW_REPLACEMENT and record:
                asset = db.get(Asset, record.old_asset_id)
            extras.append(_approval_row(history, reporting_month=month_key, label=label, asset=asset))

    for work in work_records:
        if work.asset_id is None:
            extras.append(_unlinked_work_row(work, month_key))

    rows = [*base.get("items", []), *extras]
    department_key = (department or "").strip().lower()
    device_key = (device_category or "").strip().lower()
    user_key = (changed_by or "").strip().lower()
    action_key = (action_type or "").strip().lower()
    search_key = (search or "").strip().lower()

    def matches(row: dict[str, Any]) -> bool:
        if department_key and str(row.get("department") or "").lower() != department_key:
            return False
        if device_key and str(row.get("device_category") or "").lower() != device_key:
            return False
        if user_key and user_key not in " ".join(str(row.get(key) or "").lower() for key in ("performed_by", "performed_by_email")):
            return False
        if action_key and action_key != str(row.get("action_type") or "").lower():
            return False
        if search_key:
            haystack = " ".join(str(row.get(key) or "") for key in (
                "asset_code", "cpu_asset_tag", "workstation_no", "performed_by", "department",
                "action_label", "field_or_component", "old_value", "new_value", "reason", "batch_code",
            )).lower()
            if search_key not in haystack:
                return False
        return True

    filtered = [row for row in rows if matches(row)]
    unique: dict[str, dict[str, Any]] = {}
    for row in filtered:
        unique[str(row.get("activity_id"))] = row
    filtered = list(unique.values())
    filtered.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)

    base["items"] = filtered[:limit]
    base["timeline"] = filtered[:25]
    base["total"] = len(filtered)
    base["summary"] = dict(base.get("summary", {}))
    base["summary"]["total_activities"] = len(filtered)
    base["summary"]["new_assets"] = len(created_histories)
    base["visual_summary"] = [
        {"name": name.replace("_", " ").title(), "value": count}
        for name, count in sorted(
            {
                source: sum(1 for row in filtered if row.get("source_type") == source)
                for source in {str(row.get("source_type") or "other") for row in filtered}
            }.items()
        )
    ]
    users = {}
    for row in filtered:
        name = str(row.get("performed_by") or "Unknown")
        users[name] = users.get(name, 0) + 1
    base["user_activity"] = [
        {"name": name, "value": value}
        for name, value in sorted(users.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]
    base["filters"] = {
        "departments": sorted({str(row.get("department")) for row in rows if row.get("department")}),
        "users": sorted({str(row.get("performed_by")) for row in rows if row.get("performed_by")}),
        "device_categories": sorted({str(row.get("device_category")) for row in rows if row.get("device_category")}),
        "action_types": sorted({str(row.get("action_type")) for row in rows if row.get("action_type")}),
    }
    base["traceability"] = {
        "asset_creation": True,
        "asset_edits": True,
        "excel_imports": True,
        "custody": True,
        "component_changes": True,
        "replacement_approvals": True,
        "purchase_approvals": True,
        "it_work_approvals": True,
    }
    return base
