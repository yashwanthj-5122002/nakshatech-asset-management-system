from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
import json
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import Asset, AssetHistory, ComponentReplacement, User
from app.modules.it_activity.models import (
    ITHandoverRecord,
    ITPurchaseRecord,
    ITPurchaseRequest,
    ITPurchaseRequestHistory,
)
from app.services.approval_workflow_service import (
    WORKFLOW_PURCHASE_REQUEST,
    record_approval_history,
)
from app.services.approval_notification_service import (
    notify_approval_decision,
    notify_management_approval_required,
)
from app.services.asset_lifecycle_service import (
    AssetLifecycleTransitionError,
    apply_assignment_transition,
    apply_return_transition,
    custody_state,
)
from app.modules.it_activity.schemas import (
    HandoverCreate,
    PurchaseCreate,
    PurchaseRequestCreate,
    PurchaseRequestDecision,
    PurchaseRequestResubmit,
)

IST = ZoneInfo("Asia/Kolkata")


def normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_action(value: str | None) -> str:
    text = (value or "").strip().lower()
    if not text:
        return "other"
    if "downgrade" in text or "degrade" in text:
        return "downgrade"
    if "upgrade" in text:
        return "upgrade"
    if "replace" in text:
        return "replacement"
    if "return" in text:
        return "return"
    if "transfer" in text:
        return "transfer"
    if "hire" in text or "handover" in text or "hand over" in text or "issue" in text:
        return "handover"
    return "other"


def month_bounds(month_key: str) -> tuple[date, date, datetime, datetime]:
    try:
        month_start = datetime.strptime(month_key, "%Y-%m").date().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Month must be in YYYY-MM format") from exc
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    local_start = datetime.combine(month_start, time.min, tzinfo=IST)
    local_end = datetime.combine(next_month, time.min, tzinfo=IST)
    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)
    return month_start, month_end, utc_start, utc_end


def _missing_reporting_month(column):
    return or_(column.is_(None), func.trim(column) == "")


def local_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(IST)


def make_code(prefix: str) -> str:
    local = datetime.now(IST)
    return f"{prefix}-{local.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8].upper()}"


def _json_mapping(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return {"value": value}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


def flatten_asset_history(history: AssetHistory, asset: Asset | None) -> list[dict[str, Any]]:
    old_values = _json_mapping(history.old_value)
    new_values = _json_mapping(history.new_value)
    fields = list(dict.fromkeys([*old_values.keys(), *new_values.keys()])) or ["activity"]
    local = local_datetime(history.created_at)
    rows: list[dict[str, Any]] = []
    for field in fields:
        rows.append({
            "activity_id": f"asset-history-{history.id}-{field}",
            "source_type": "asset_edit",
            "record_id": history.id,
            "asset_id": history.asset_id,
            "asset_code": asset.asset_code if asset else None,
            "cpu_asset_tag": asset.cpu_asset_tag if asset else None,
            "workstation_no": asset.workstation_no if asset else None,
            "device_category": asset.device_type if asset else None,
            "department": asset.department if asset else None,
            "action_type": history.change_type or "asset_activity",
            "action_label": history.action,
            "field_or_component": field.replace("_", " ").title(),
            "old_value": old_values.get(field),
            "new_value": new_values.get(field),
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
        })
    return rows


def component_row(record: ComponentReplacement, asset: Asset | None) -> dict[str, Any]:
    local = local_datetime(record.created_at)
    return {
        "activity_id": f"component-{record.id}",
        "source_type": "component_change",
        "record_id": record.id,
        "asset_id": record.asset_id,
        "asset_code": asset.asset_code if asset else None,
        "cpu_asset_tag": record.cpu_asset_tag or (asset.cpu_asset_tag if asset else None),
        "workstation_no": record.workstation_no or (asset.workstation_no if asset else None),
        "device_category": asset.device_type if asset else None,
        "department": asset.department if asset else None,
        "action_type": record.change_type,
        "action_label": f"{record.change_type.replace('_', ' ').title()} — {record.component_type}",
        "field_or_component": record.component_type,
        "old_value": record.old_value,
        "new_value": record.new_value,
        "reason": record.reason,
        "remarks": record.remarks,
        "performed_by": record.performed_by,
        "performed_by_email": record.performed_by_email,
        "performed_by_role": record.performed_by_role,
        "batch_code": record.batch_code or record.replacement_code,
        "reporting_month": record.reporting_month or (local.strftime("%Y-%m") if local else None),
        "system_recorded_at": local.isoformat() if local else None,
        "activity_date": local.date().isoformat() if local else (record.replacement_date.isoformat() if record.replacement_date else None),
        "activity_time": local.strftime("%I:%M:%S %p") if local else None,
        "timestamp": local.isoformat() if local else None,
        "time_recorded": True,
    }


def handover_row(record: ITHandoverRecord) -> dict[str, Any]:
    created_local = local_datetime(record.created_at)
    timestamp: datetime | None = None
    if record.activity_time is not None:
        timestamp = datetime.combine(record.activity_date, record.activity_time, tzinfo=IST)
    elif not record.imported and created_local is not None:
        timestamp = created_local
    return {
        "activity_id": f"handover-{record.id}",
        "source_type": "handover_return",
        "record_id": record.id,
        "asset_id": record.asset_id,
        "asset_code": record.asset_code_snapshot,
        "cpu_asset_tag": record.internal_asset_no,
        "workstation_no": record.dc_number,
        "device_category": record.device_category,
        "department": record.department,
        "action_type": record.action_type,
        "action_label": f"{record.device_category.title()} {record.action_type.replace('_', ' ').title()}",
        "field_or_component": "Assignment / Custody",
        "old_value": None,
        "new_value": record.employee_name or record.action_raw,
        "reason": record.remarks,
        "remarks": record.remarks,
        "performed_by": record.performed_by or record.issued_by,
        "performed_by_email": record.performed_by_email,
        "performed_by_role": record.performed_by_role,
        "batch_code": record.activity_code,
        "reporting_month": record.reporting_month or record.activity_date.strftime("%Y-%m"),
        "system_recorded_at": created_local.isoformat() if created_local else None,
        "activity_date": record.activity_date.isoformat(),
        "activity_time": timestamp.strftime("%I:%M:%S %p") if timestamp else "Not recorded",
        "timestamp": timestamp.isoformat() if timestamp else f"{record.activity_date.isoformat()}T00:00:00+05:30",
        "time_recorded": timestamp is not None,
        "condition": record.condition,
        "accessories": record.accessories_provided,
        "source_file": record.source_file,
        "source_sheet": record.source_sheet,
    }


def purchase_row(record: ITPurchaseRecord) -> dict[str, Any]:
    created_local = local_datetime(record.created_at)
    timestamp = None if record.imported else created_local
    return {
        "activity_id": f"purchase-{record.id}",
        "source_type": "purchase",
        "record_id": record.id,
        "asset_id": record.linked_asset_id,
        "asset_code": record.linked_asset_code_snapshot or record.asset_number,
        "cpu_asset_tag": record.asset_number,
        "workstation_no": None,
        "device_category": "purchase",
        "department": record.department,
        "action_type": "purchase",
        "action_label": "Purchase Recorded",
        "field_or_component": record.item_description,
        "old_value": None,
        "new_value": f"Quantity {record.quantity:g}",
        "reason": record.remarks,
        "remarks": record.remarks,
        "performed_by": record.created_by or record.approved_by,
        "performed_by_email": record.created_by_email,
        "performed_by_role": record.created_by_role,
        "batch_code": record.purchase_code,
        "reporting_month": record.reporting_month or record.purchase_date.strftime("%Y-%m"),
        "system_recorded_at": created_local.isoformat() if created_local else None,
        "activity_date": record.purchase_date.isoformat(),
        "activity_time": timestamp.strftime("%I:%M:%S %p") if timestamp else "Not recorded",
        "timestamp": timestamp.isoformat() if timestamp else f"{record.purchase_date.isoformat()}T00:00:00+05:30",
        "time_recorded": timestamp is not None,
        "supplier_name": record.supplier_name,
        "po_number": record.po_number,
        "quantity": record.quantity,
        "total_price": record.total_price,
        "source_file": record.source_file,
        "source_sheet": record.source_sheet,
    }


def _find_asset(db: Session, asset_id: int | None = None, lookup: str | None = None, *, for_update: bool = False) -> Asset | None:
    if asset_id is not None:
        query = select(Asset).where(Asset.id == asset_id)
        if for_update:
            query = query.with_for_update()
        return db.scalar(query)
    value = normalize_text(lookup)
    if not value:
        return None
    query = select(Asset).where(or_(
        func.lower(Asset.asset_code) == value.lower(),
        func.lower(Asset.cpu_asset_tag) == value.lower(),
        func.lower(Asset.system_name) == value.lower(),
        func.lower(Asset.workstation_no) == value.lower(),
    )).limit(1)
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def _record_asset_history(db: Session, asset: Asset, user: User, record: ITHandoverRecord, before: dict[str, Any], after: dict[str, Any]) -> None:
    changed = {key: {"from": before.get(key), "to": after.get(key)} for key in after if before.get(key) != after.get(key)}
    if not changed:
        return
    db.add(AssetHistory(
        asset_id=asset.id,
        action=f"{record.device_category.title()} {record.action_type.replace('_', ' ').title()}",
        change_type=f"handover_{record.action_type}",
        batch_code=record.activity_code,
        old_value=json.dumps({key: item["from"] for key, item in changed.items()}, ensure_ascii=False, default=str),
        new_value=json.dumps({key: item["to"] for key, item in changed.items()}, ensure_ascii=False, default=str),
        remarks=record.remarks,
        reason=record.remarks or record.action_raw or record.action_type,
        changed_by=user.email,
        changed_by_name=user.full_name,
        changed_by_role=user.role,
        field_count=len(changed),
        reporting_month=record.reporting_month,
    ))


def hydrate_handover_custody_movements(
    db: Session, records: list[ITHandoverRecord]
) -> list[ITHandoverRecord]:
    """Attach non-persistent From/To custody snapshots for API serialization.

    Batch 3B already records every live custody mutation in ``AssetHistory``
    using the handover activity code as ``batch_code``. Reusing that audit data
    avoids a database migration while still letting the UI show an exact
    custodian movement for Handover, Transfer and Return.
    """
    if not records:
        return records

    codes = [record.activity_code for record in records if record.activity_code]
    history_by_code: dict[str, AssetHistory] = {}
    if codes:
        histories = db.scalars(
            select(AssetHistory)
            .where(
                AssetHistory.batch_code.in_(codes),
                AssetHistory.change_type.like("handover_%"),
            )
            .order_by(AssetHistory.id.desc())
        ).all()
        for history in histories:
            if history.batch_code and history.batch_code not in history_by_code:
                history_by_code[history.batch_code] = history

    for record in records:
        from_employee: str | None = None
        to_employee: str | None = None
        history = history_by_code.get(record.activity_code)
        if history is not None:
            old_values = _json_mapping(history.old_value)
            new_values = _json_mapping(history.new_value)
            from_employee = normalize_text(old_values.get("used_by"))
            to_employee = normalize_text(new_values.get("used_by"))
        elif record.action_type == "handover":
            to_employee = normalize_text(record.employee_name)
        elif record.action_type == "transfer":
            # Historical imports may not contain the previous custodian. Never
            # invent one; expose the known destination only.
            to_employee = normalize_text(record.employee_name)
        elif record.action_type == "return":
            from_employee = normalize_text(record.employee_name)

        setattr(record, "from_employee_name", from_employee)
        setattr(record, "to_employee_name", to_employee)

    return records


def create_handover_record(db: Session, payload: HandoverCreate, user: User) -> ITHandoverRecord:
    action_type = normalize_action(payload.action_type)
    asset = _find_asset(db, payload.asset_id, payload.internal_asset_no, for_update=payload.apply_to_asset)
    if payload.asset_id is not None and asset is None:
        raise HTTPException(status_code=404, detail="Selected asset was not found")
    now_local = datetime.now(IST)
    record = ITHandoverRecord(
        activity_code=make_code("ITHR"),
        asset_id=asset.id if asset else None,
        asset_code_snapshot=asset.asset_code if asset else None,
        device_category=payload.device_category,
        employee_name=normalize_text(payload.employee_name),
        dc_number=normalize_text(payload.dc_number),
        department=normalize_text(payload.department),
        work_mode=normalize_text(payload.work_mode),
        internal_asset_no=normalize_text(payload.internal_asset_no) or (asset.cpu_asset_tag if asset else None),
        specification=normalize_text(payload.specification),
        serial_number=normalize_text(payload.serial_number),
        accessories_provided=normalize_text(payload.accessories_provided),
        condition=normalize_text(payload.condition),
        action_type=action_type,
        action_raw=payload.action_type.strip(),
        activity_date=payload.activity_date,
        activity_time=now_local.time().replace(microsecond=0),
        issued_by=normalize_text(payload.issued_by) or user.full_name,
        remarks=normalize_text(payload.remarks),
        asset_updated_status=normalize_text(payload.asset_updated_status),
        imported=False,
        performed_by=user.full_name,
        performed_by_email=user.email,
        performed_by_role=user.role,
        reporting_month=normalize_reporting_month(payload.reporting_month),
    )
    db.add(record)
    db.flush()

    if asset and payload.apply_to_asset and action_type in {"handover", "return", "transfer"}:
        before = custody_state(asset)
        try:
            if action_type in {"handover", "transfer"}:
                apply_assignment_transition(
                    asset,
                    used_by=payload.employee_name,
                    department=payload.department,
                    workstation_no=payload.dc_number,
                    location=asset.location,
                    work_mode=payload.work_mode or asset.work_mode or "office",
                    transition_date=payload.activity_date,
                    action=action_type,
                )
            else:
                apply_return_transition(
                    asset,
                    final_status=payload.return_status,
                    transition_date=payload.activity_date,
                    require_active_custodian=True,
                )
        except AssetLifecycleTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        asset.performed_by = user.full_name
        asset.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        after = custody_state(asset)
        _record_asset_history(db, asset, user, record, before, after)
        record.asset_updated_status = f"Asset Register updated: {asset.status.replace('_', ' ').title()}"

    db.commit()
    db.refresh(record)
    return record


PURCHASE_REQUEST_STATUSES = {
    "pending_approval",
    "approved",
    "rejected",
    "sent_back",
    "purchase_completed",
}


def _purchase_request_total(
    quantity: float,
    unit_price: float | None,
    explicit_total: float | None,
) -> float | None:
    if explicit_total is not None:
        return round(float(explicit_total), 2)
    if unit_price is not None:
        return round(float(unit_price) * float(quantity), 2)
    return None


def _record_purchase_request_history(
    db: Session,
    request: ITPurchaseRequest,
    user: User,
    *,
    action: str,
    from_status: str | None,
    to_status: str,
    remarks: str | None = None,
) -> ITPurchaseRequestHistory:
    history = ITPurchaseRequestHistory(
        request=request,
        action=action,
        from_status=from_status,
        to_status=to_status,
        remarks=normalize_text(remarks),
        performed_by_user_id=user.id,
        performed_by_name=user.full_name,
        performed_by_email=user.email,
        performed_by_role=user.role,
    )
    db.add(history)
    return history


def purchase_request_to_dict(
    request: ITPurchaseRequest,
    *,
    include_history: bool = False,
) -> dict[str, Any]:
    purchase = request.purchase_record
    payload = {
        "id": request.id,
        "request_code": request.request_code,
        "reporting_month": request.reporting_month,
        "requesting_department": request.requesting_department,
        "requested_employee": request.requested_employee,
        "item_type": request.item_type,
        "item_name": request.item_name,
        "item_description": request.item_description,
        "quantity": request.quantity,
        "estimated_unit_price": request.estimated_unit_price,
        "estimated_total_amount": request.estimated_total_amount,
        "business_reason": request.business_reason,
        "required_by_date": request.required_by_date,
        "priority": request.priority,
        "it_remarks": request.it_remarks,
        "status": request.status,
        "branch": request.branch,
        "requested_by_name": request.requested_by_name,
        "requested_by_email": request.requested_by_email,
        "requested_by_role": request.requested_by_role,
        "requested_at": request.requested_at,
        "approved_amount": request.approved_amount,
        "management_remarks": request.management_remarks,
        "decided_by_name": request.decided_by_name,
        "decided_by_email": request.decided_by_email,
        "decided_by_role": request.decided_by_role,
        "decided_at": request.decided_at,
        "purchase_completed_at": request.purchase_completed_at,
        "updated_at": request.updated_at,
        "purchase_record_id": purchase.id if purchase else None,
        "purchase_code": purchase.purchase_code if purchase else None,
        "actual_purchase_amount": purchase.total_price if purchase else None,
        "purchase_date": purchase.purchase_date if purchase else None,
        "histories": list(request.histories) if include_history else [],
    }
    return payload


def create_purchase_request(
    db: Session,
    payload: PurchaseRequestCreate,
    user: User,
) -> ITPurchaseRequest:
    estimated_total = _purchase_request_total(
        payload.quantity,
        payload.estimated_unit_price,
        payload.estimated_total_amount,
    )
    request = ITPurchaseRequest(
        request_code=make_code("ITPR"),
        reporting_month=normalize_reporting_month(payload.reporting_month),
        requesting_department=payload.requesting_department.strip(),
        requested_employee=payload.requested_employee.strip(),
        item_type=payload.item_type,
        item_name=payload.item_name.strip(),
        item_description=normalize_text(payload.item_description),
        quantity=payload.quantity,
        estimated_unit_price=payload.estimated_unit_price,
        estimated_total_amount=estimated_total,
        business_reason=payload.business_reason.strip(),
        required_by_date=payload.required_by_date,
        priority=payload.priority,
        it_remarks=normalize_text(payload.it_remarks),
        status="pending_approval",
        branch=normalize_text(user.branch),
        requested_by_user_id=user.id,
        requested_by_name=user.full_name,
        requested_by_email=user.email,
        requested_by_role=user.role,
    )
    db.add(request)
    db.flush()
    _record_purchase_request_history(
        db,
        request,
        user,
        action="submitted",
        from_status=None,
        to_status="pending_approval",
        remarks=payload.it_remarks,
    )
    record_approval_history(
        db,
        workflow_type=WORKFLOW_PURCHASE_REQUEST,
        record_id=request.id,
        record_code=request.request_code,
        action="submitted",
        from_status=None,
        to_status="pending_approval",
        user=user,
        remarks=payload.it_remarks,
    )
    notify_management_approval_required(
        db,
        workflow="purchase_request",
        record_id=request.id,
        record_code=request.request_code,
        reporting_month=request.reporting_month,
        submitted_by_name=user.full_name,
        event_token=request.requested_at,
    )
    db.commit()
    db.refresh(request)
    return request


def resubmit_purchase_request(
    db: Session,
    request_id: int,
    payload: PurchaseRequestResubmit,
    user: User,
) -> ITPurchaseRequest:
    request = db.scalar(
        select(ITPurchaseRequest)
        .where(ITPurchaseRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    if request.status != "sent_back":
        raise HTTPException(status_code=409, detail="Only sent-back requests can be edited and resubmitted")

    previous_status = request.status
    request.reporting_month = normalize_reporting_month(payload.reporting_month)
    request.requesting_department = payload.requesting_department.strip()
    request.requested_employee = payload.requested_employee.strip()
    request.item_type = payload.item_type
    request.item_name = payload.item_name.strip()
    request.item_description = normalize_text(payload.item_description)
    request.quantity = payload.quantity
    request.estimated_unit_price = payload.estimated_unit_price
    request.estimated_total_amount = _purchase_request_total(
        payload.quantity,
        payload.estimated_unit_price,
        payload.estimated_total_amount,
    )
    request.business_reason = payload.business_reason.strip()
    request.required_by_date = payload.required_by_date
    request.priority = payload.priority
    request.it_remarks = normalize_text(payload.it_remarks)
    request.status = "pending_approval"
    request.approved_amount = None
    request.management_remarks = None
    request.decided_by_user_id = None
    request.decided_by_name = None
    request.decided_by_email = None
    request.decided_by_role = None
    request.decided_at = None
    request.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    _record_purchase_request_history(
        db,
        request,
        user,
        action="resubmitted",
        from_status=previous_status,
        to_status="pending_approval",
        remarks=payload.it_remarks,
    )
    record_approval_history(
        db,
        workflow_type=WORKFLOW_PURCHASE_REQUEST,
        record_id=request.id,
        record_code=request.request_code,
        action="resubmitted",
        from_status=previous_status,
        to_status="pending_approval",
        user=user,
        remarks=payload.it_remarks,
    )
    notify_management_approval_required(
        db,
        workflow="purchase_request",
        record_id=request.id,
        record_code=request.request_code,
        reporting_month=request.reporting_month,
        submitted_by_name=user.full_name,
        event_token=request.updated_at,
        resubmitted=True,
    )
    db.commit()
    db.refresh(request)
    return request


def decide_purchase_request(
    db: Session,
    request_id: int,
    payload: PurchaseRequestDecision,
    user: User,
) -> ITPurchaseRequest:
    request = db.scalar(
        select(ITPurchaseRequest)
        .where(ITPurchaseRequest.id == request_id)
        .with_for_update()
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Purchase request was not found")
    if request.status != "pending_approval":
        raise HTTPException(status_code=409, detail="Only pending requests can receive a management decision")
    if request.requested_by_user_id is not None and request.requested_by_user_id == user.id:
        raise HTTPException(status_code=409, detail="A user cannot decide their own purchase request")

    remarks = normalize_text(payload.management_remarks)
    if payload.action in {"reject", "send_back"} and not remarks:
        raise HTTPException(status_code=400, detail="Management remarks are required for rejection or send back")

    status_by_action = {
        "approve": "approved",
        "reject": "rejected",
        "send_back": "sent_back",
    }
    next_status = status_by_action[payload.action]
    approved_amount = None
    if payload.action == "approve":
        approved_amount = payload.approved_amount
        if approved_amount is None:
            approved_amount = request.estimated_total_amount

    request.status = next_status
    request.approved_amount = approved_amount
    request.management_remarks = remarks
    request.decided_by_user_id = user.id
    request.decided_by_name = user.full_name
    request.decided_by_email = user.email
    request.decided_by_role = user.role
    request.decided_at = datetime.now(timezone.utc).replace(tzinfo=None)
    request.updated_at = request.decided_at
    _record_purchase_request_history(
        db,
        request,
        user,
        action=payload.action,
        from_status="pending_approval",
        to_status=next_status,
        remarks=remarks,
    )
    record_approval_history(
        db,
        workflow_type=WORKFLOW_PURCHASE_REQUEST,
        record_id=request.id,
        record_code=request.request_code,
        action={"approve": "approved", "reject": "rejected", "send_back": "returned"}[payload.action],
        from_status="pending_approval",
        to_status=next_status,
        user=user,
        remarks=remarks,
    )
    notify_approval_decision(
        db,
        workflow="purchase_request",
        record_id=request.id,
        record_code=request.request_code,
        reporting_month=request.reporting_month,
        outcome=next_status,
        decided_by_name=user.full_name,
        remarks=remarks,
        event_token=request.decided_at,
        recipient_user_id=request.requested_by_user_id,
    )
    db.commit()
    db.refresh(request)
    return request


def purchase_request_query(
    month: str | None = None,
    *,
    status: str | None = None,
    department: str | None = None,
    priority: str | None = None,
    search: str | None = None,
):
    query = select(ITPurchaseRequest)
    if month:
        _start, _end, utc_start, utc_end = month_bounds(month)
        query = query.where(or_(
            ITPurchaseRequest.reporting_month == month,
            and_(
                ITPurchaseRequest.reporting_month.is_(None),
                ITPurchaseRequest.requested_at >= utc_start,
                ITPurchaseRequest.requested_at < utc_end,
            ),
        ))
    if status and status != "all":
        if status not in PURCHASE_REQUEST_STATUSES:
            raise HTTPException(status_code=400, detail="Invalid purchase request status")
        query = query.where(ITPurchaseRequest.status == status)
    if department:
        query = query.where(func.lower(ITPurchaseRequest.requesting_department) == department.strip().lower())
    if priority:
        query = query.where(ITPurchaseRequest.priority == priority.strip().lower())
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(
            ITPurchaseRequest.request_code.ilike(pattern),
            ITPurchaseRequest.requesting_department.ilike(pattern),
            ITPurchaseRequest.requested_employee.ilike(pattern),
            ITPurchaseRequest.item_name.ilike(pattern),
            ITPurchaseRequest.item_description.ilike(pattern),
            ITPurchaseRequest.business_reason.ilike(pattern),
            ITPurchaseRequest.requested_by_name.ilike(pattern),
            ITPurchaseRequest.requested_by_email.ilike(pattern),
            ITPurchaseRequest.decided_by_name.ilike(pattern),
        ))
    return query


def purchase_request_summary(
    db: Session,
    month: str | None = None,
    *,
    department: str | None = None,
    priority: str | None = None,
    search: str | None = None,
) -> dict[str, Any]:
    records = list(db.scalars(
        purchase_request_query(
            month,
            department=department,
            priority=priority,
            search=search,
        )
    ).all())
    counts = Counter(record.status for record in records)
    return {
        "total": len(records),
        "pending_approval": counts.get("pending_approval", 0),
        "approved": counts.get("approved", 0),
        "rejected": counts.get("rejected", 0),
        "sent_back": counts.get("sent_back", 0),
        "purchase_completed": counts.get("purchase_completed", 0),
        "estimated_value": round(sum(float(record.estimated_total_amount or 0) for record in records), 2),
        "approved_value": round(sum(float(record.approved_amount or 0) for record in records), 2),
        "departments": sorted({record.requesting_department for record in records}),
    }


def create_purchase_record(db: Session, payload: PurchaseCreate, user: User) -> ITPurchaseRecord:
    asset = _find_asset(db, payload.linked_asset_id)
    if payload.linked_asset_id is not None and asset is None:
        raise HTTPException(status_code=404, detail="Linked asset was not found")

    purchase_request: ITPurchaseRequest | None = None
    if payload.purchase_request_id is not None:
        purchase_request = db.scalar(
            select(ITPurchaseRequest)
            .where(ITPurchaseRequest.id == payload.purchase_request_id)
            .with_for_update()
        )
        if purchase_request is None:
            raise HTTPException(status_code=404, detail="Purchase approval request was not found")
        if purchase_request.status != "approved":
            raise HTTPException(status_code=409, detail="Management approval is required before creating a purchase record")
        if purchase_request.purchase_record is not None:
            raise HTTPException(status_code=409, detail="This approved request already has a purchase record")
    elif user.role == "it":
        raise HTTPException(status_code=400, detail="Select an approved purchase request before creating a purchase record")

    total = payload.total_price
    if total is None and payload.unit_price is not None:
        total = payload.unit_price * payload.quantity

    approved_by = normalize_text(payload.approved_by)
    department = normalize_text(payload.department)
    if purchase_request is not None:
        approved_by = approved_by or purchase_request.decided_by_name
        department = department or purchase_request.requesting_department

    record = ITPurchaseRecord(
        purchase_code=make_code("ITPO"),
        purchase_request_id=purchase_request.id if purchase_request else None,
        linked_asset_id=asset.id if asset else None,
        linked_asset_code_snapshot=asset.asset_code if asset else None,
        purchase_date=payload.purchase_date,
        po_number=normalize_text(payload.po_number),
        asset_number=normalize_text(payload.asset_number),
        supplier_name=payload.supplier_name.strip(),
        supplier_contact=normalize_text(payload.supplier_contact),
        item_description=payload.item_description.strip(),
        warranty_number=normalize_text(payload.warranty_number),
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        total_price=total,
        received_date=payload.received_date,
        inspection_status=normalize_text(payload.inspection_status),
        approved_by=approved_by,
        department=department,
        remarks=normalize_text(payload.remarks),
        imported=False,
        created_by=user.full_name,
        created_by_email=user.email,
        created_by_role=user.role,
        reporting_month=normalize_reporting_month(payload.reporting_month),
    )
    db.add(record)
    db.flush()

    if purchase_request is not None:
        previous_status = purchase_request.status
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        purchase_request.status = "purchase_completed"
        purchase_request.purchase_completed_at = now
        purchase_request.updated_at = now
        _record_purchase_request_history(
            db,
            purchase_request,
            user,
            action="purchase_completed",
            from_status=previous_status,
            to_status="purchase_completed",
            remarks=f"Purchase record {record.purchase_code} created",
        )

    db.commit()
    db.refresh(record)
    return record



def monthly_activity_data(
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
    start_date, end_date, utc_start, utc_end = month_bounds(month_key)

    histories = list(db.scalars(
        select(AssetHistory)
        .where(
            or_(
                AssetHistory.reporting_month == month_key,
                and_(_missing_reporting_month(AssetHistory.reporting_month), AssetHistory.created_at >= utc_start, AssetHistory.created_at < utc_end),
            ),
            AssetHistory.change_type != "asset_created",
            ~AssetHistory.change_type.like("component_%"),
            ~AssetHistory.change_type.like("handover_%"),
        )
        .order_by(AssetHistory.created_at.desc(), AssetHistory.id.desc())
    ).all())
    history_asset_ids = {row.asset_id for row in histories}

    components = list(db.scalars(
        select(ComponentReplacement)
        .where(or_(
            ComponentReplacement.reporting_month == month_key,
            and_(
                _missing_reporting_month(ComponentReplacement.reporting_month),
                or_(
                    and_(
                        ComponentReplacement.replacement_date.is_not(None),
                        ComponentReplacement.replacement_date >= start_date,
                        ComponentReplacement.replacement_date <= end_date,
                    ),
                    and_(
                        ComponentReplacement.replacement_date.is_(None),
                        ComponentReplacement.created_at >= utc_start,
                        ComponentReplacement.created_at < utc_end,
                    ),
                ),
            ),
        ))
        .order_by(ComponentReplacement.created_at.desc(), ComponentReplacement.id.desc())
    ).all())
    component_asset_ids = {row.asset_id for row in components}

    handovers = list(db.scalars(
        select(ITHandoverRecord)
        .where(or_(
            ITHandoverRecord.reporting_month == month_key,
            and_(_missing_reporting_month(ITHandoverRecord.reporting_month), ITHandoverRecord.activity_date >= start_date, ITHandoverRecord.activity_date <= end_date),
        ))
        .order_by(ITHandoverRecord.activity_date.desc(), ITHandoverRecord.activity_time.desc(), ITHandoverRecord.id.desc())
    ).all())
    purchases = list(db.scalars(
        select(ITPurchaseRecord)
        .where(or_(
            ITPurchaseRecord.reporting_month == month_key,
            and_(_missing_reporting_month(ITPurchaseRecord.reporting_month), ITPurchaseRecord.purchase_date >= start_date, ITPurchaseRecord.purchase_date <= end_date),
        ))
        .order_by(ITPurchaseRecord.purchase_date.desc(), ITPurchaseRecord.id.desc())
    ).all())

    asset_ids = history_asset_ids | component_asset_ids | {row.asset_id for row in handovers if row.asset_id} | {row.linked_asset_id for row in purchases if row.linked_asset_id}
    assets = {asset.id: asset for asset in db.scalars(select(Asset).where(Asset.id.in_(asset_ids))).all()} if asset_ids else {}

    rows: list[dict[str, Any]] = []
    for history in histories:
        rows.extend(flatten_asset_history(history, assets.get(history.asset_id)))
    rows.extend(component_row(record, assets.get(record.asset_id)) for record in components)
    rows.extend(handover_row(record) for record in handovers)
    rows.extend(purchase_row(record) for record in purchases)

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
                "action_label", "field_or_component", "old_value", "new_value", "reason",
            )).lower()
            if search_key not in haystack:
                return False
        return True

    filtered = [row for row in rows if matches(row)]
    filtered.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)

    full_edit_histories = [row for row in histories if row.change_type == "full_edit"]
    handover_count = sum(row.action_type in {"handover", "transfer"} for row in handovers)
    return_count = sum(row.action_type == "return" for row in handovers)
    component_counts = Counter(record.change_type for record in components)
    total_operations = (
        len(full_edit_histories)
        + len(components)
        + handover_count
        + return_count
        + len(purchases)
    )
    user_counts = Counter(str(row.get("performed_by") or "Unknown") for row in filtered)
    source_counts = Counter(str(row.get("source_type") or "other") for row in filtered)

    return {
        "month": {
            "key": month_key,
            "label": start_date.strftime("%B %Y"),
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "timezone": "Asia/Kolkata",
        },
        "summary": {
            "assets_edited": len({row.asset_id for row in full_edit_histories}),
            "asset_edit_operations": len(full_edit_histories),
            "component_changes": len(components),
            "upgrades": component_counts.get("upgrade", 0),
            "replacements": component_counts.get("replacement", 0),
            "downgrades": component_counts.get("downgrade", 0),
            "combined_changes": component_counts.get("upgrade_replacement", 0),
            "laptop_handovers": sum(row.device_category == "laptop" and row.action_type in {"handover", "transfer"} for row in handovers),
            "desktop_handovers": sum(row.device_category == "desktop" and row.action_type in {"handover", "transfer"} for row in handovers),
            "handover_operations": handover_count,
            "return_operations": return_count,
            "purchases_recorded": len(purchases),
            "purchase_value": round(sum(float(row.total_price or 0) for row in purchases), 2),
            "total_activities": total_operations,
        },
        "visual_summary": [{"name": key.replace("_", " ").title(), "value": value} for key, value in source_counts.items()],
        "user_activity": [{"name": key, "value": value} for key, value in user_counts.most_common()],
        "timeline": filtered[:25],
        "items": filtered[:limit],
        "total": len(filtered),
        "filters": {
            "departments": sorted({str(row.get("department")) for row in rows if row.get("department")}),
            "users": sorted({str(row.get("performed_by")) for row in rows if row.get("performed_by")}),
            "device_categories": sorted({str(row.get("device_category")) for row in rows if row.get("device_category")}),
            "action_types": sorted({str(row.get("action_type")) for row in rows if row.get("action_type")}),
        },
    }
