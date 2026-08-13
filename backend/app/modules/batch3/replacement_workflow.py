from __future__ import annotations

from datetime import date
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.entities import ApprovalDecisionHistory, Asset, AssetHistory, ReplacementRecord, User
from app.modules.batch3.models import ReplacementWorkflowState
from app.modules.it_activity.models import ITPurchaseRequest, ITPurchaseRequestHistory
from app.modules.it_activity.service import make_code
from app.services.approval_notification_service import notify_approval_decision, notify_management_approval_required
from app.services.approval_workflow_service import (
    WORKFLOW_PURCHASE_REQUEST,
    WORKFLOW_REPLACEMENT,
    record_approval_history,
    utc_now_naive,
)
from app.services.asset_lifecycle_service import (
    AssetLifecycleTransitionError,
    apply_assignment_transition,
    canonical_device_type,
    custody_state,
    lifecycle_bucket,
)

def get_or_create_replacement_state(
    db: Session,
    record: ReplacementRecord,
    old_asset: Asset,
    *,
    previous_status: str | None = None,
) -> ReplacementWorkflowState:
    state = db.scalar(
        select(ReplacementWorkflowState)
        .where(ReplacementWorkflowState.replacement_record_id == record.id)
        .with_for_update()
    )
    if state is not None:
        return state
    inferred = previous_status
    if not inferred:
        inferred = "assigned" if (old_asset.used_by or old_asset.workstation_no) else "available"
    state = ReplacementWorkflowState(
        replacement_record_id=record.id,
        previous_asset_status=inferred,
    )
    db.add(state)
    db.flush()
    return state


def _candidate_spare_query(old_asset: Asset):
    canonical = canonical_device_type(old_asset.device_type)
    candidates = select(Asset).where(
        Asset.id != old_asset.id,
        func.lower(Asset.status) == "available",
        or_(Asset.used_by.is_(None), func.trim(Asset.used_by) == ""),
    )
    return candidates.order_by(Asset.asset_date.asc().nulls_last(), Asset.id.asc()), canonical


def select_available_spare(
    db: Session,
    old_asset: Asset,
    explicit_asset_id: int | None = None,
) -> Asset | None:
    if explicit_asset_id is not None:
        candidate = db.scalar(
            select(Asset).where(Asset.id == explicit_asset_id).with_for_update()
        )
        if candidate is None:
            raise HTTPException(status_code=404, detail="Replacement asset not found")
        if candidate.id == old_asset.id:
            raise HTTPException(status_code=400, detail="Old asset and replacement asset cannot be the same")
        if canonical_device_type(candidate.device_type) != canonical_device_type(old_asset.device_type):
            raise HTTPException(status_code=400, detail="Replacement asset must use the same device type as the old asset")
        if lifecycle_bucket(candidate.status) != "available" or str(candidate.used_by or "").strip():
            raise HTTPException(status_code=409, detail="Replacement asset is no longer available")
        return candidate

    query, canonical = _candidate_spare_query(old_asset)
    for candidate in db.scalars(query.with_for_update()).all():
        if canonical_device_type(candidate.device_type) == canonical:
            return candidate
    return None


def _replacement_history(
    db: Session,
    *,
    asset: Asset,
    action: str,
    change_type: str,
    record: ReplacementRecord,
    user: User,
    old_value: Any,
    new_value: Any,
    remarks: str | None,
    field_count: int = 1,
) -> None:
    db.add(AssetHistory(
        asset_id=asset.id,
        action=action,
        change_type=change_type,
        batch_code=record.replacement_code,
        old_value=json.dumps(old_value, default=str, ensure_ascii=False) if isinstance(old_value, (dict, list)) else str(old_value) if old_value is not None else None,
        new_value=json.dumps(new_value, default=str, ensure_ascii=False) if isinstance(new_value, (dict, list)) else str(new_value) if new_value is not None else None,
        remarks=remarks,
        reason=remarks or record.reason,
        changed_by=user.email,
        changed_by_name=user.full_name,
        changed_by_role=user.role,
        field_count=field_count,
        reporting_month=record.reporting_month,
    ))


def create_procurement_request(
    db: Session,
    *,
    replacement: ReplacementRecord,
    state: ReplacementWorkflowState,
    old_asset: Asset,
) -> ITPurchaseRequest:
    if state.purchase_request_id is not None:
        existing = db.get(ITPurchaseRequest, state.purchase_request_id)
        if existing is not None:
            return existing

    requester = None
    if replacement.requested_by_user_id is not None:
        requester = db.get(User, replacement.requested_by_user_id)
    if requester is None and replacement.requested_by_email:
        requester = db.scalar(select(User).where(func.lower(User.email) == replacement.requested_by_email.lower()))

    requested_by_name = replacement.requested_by or (requester.full_name if requester else "IT Department")
    requested_by_email = replacement.requested_by_email or (requester.email if requester else "it@nakshatech.com")
    requested_by_role = replacement.requested_by_role or (requester.role if requester else "it")
    requested_by_user_id = replacement.requested_by_user_id or (requester.id if requester else None)
    now = utc_now_naive()
    device_label = canonical_device_type(old_asset.device_type)
    request = ITPurchaseRequest(
        request_code=make_code("ITPR"),
        reporting_month=replacement.reporting_month,
        requesting_department=old_asset.department or "IT",
        requested_employee=old_asset.used_by or "IT / Company",
        item_type="hardware",
        item_name=f"{device_label} replacement",
        item_description=(
            f"Replacement for {old_asset.asset_code}"
            + (f" · {old_asset.brand}" if old_asset.brand else "")
            + (f" {old_asset.model}" if old_asset.model else "")
        ),
        quantity=1,
        estimated_unit_price=None,
        estimated_total_amount=None,
        business_reason=f"Approved replacement {replacement.replacement_code}: {replacement.reason}",
        required_by_date=None,
        priority="high",
        it_remarks="Automatically linked by Batch 3 because no suitable available spare stock was found.",
        status="pending_approval",
        branch=requester.branch if requester else None,
        requested_by_user_id=requested_by_user_id,
        requested_by_name=requested_by_name,
        requested_by_email=requested_by_email,
        requested_by_role=requested_by_role,
        requested_at=now,
        updated_at=now,
    )
    db.add(request)
    db.flush()
    db.add(ITPurchaseRequestHistory(
        request_id=request.id,
        action="submitted",
        from_status=None,
        to_status="pending_approval",
        remarks=f"Created for replacement {replacement.replacement_code}; no suitable spare available",
        performed_by_user_id=requested_by_user_id,
        performed_by_name=requested_by_name,
        performed_by_email=requested_by_email,
        performed_by_role=requested_by_role,
        created_at=now,
    ))
    db.add(ApprovalDecisionHistory(
        workflow_type=WORKFLOW_PURCHASE_REQUEST,
        record_id=request.id,
        record_code=request.request_code,
        action="submitted",
        from_status=None,
        to_status="pending_approval",
        remarks=f"Linked replacement {replacement.replacement_code}",
        performed_by_user_id=requested_by_user_id,
        performed_by_name=requested_by_name,
        performed_by_email=requested_by_email,
        performed_by_role=requested_by_role,
        created_at=now,
    ))
    notify_management_approval_required(
        db,
        workflow="purchase_request",
        record_id=request.id,
        record_code=request.request_code,
        reporting_month=request.reporting_month,
        submitted_by_name=requested_by_name,
        event_token=now,
    )
    state.purchase_request_id = request.id
    state.procurement_mode = "purchase"
    state.updated_at = now
    return request


def apply_spare_replacement(
    db: Session,
    *,
    replacement: ReplacementRecord,
    state: ReplacementWorkflowState,
    old_asset: Asset,
    spare: Asset,
    user: User,
    remarks: str | None,
) -> None:
    old_before = custody_state(old_asset)
    spare_before = custody_state(spare)
    had_live_custodian = bool(str(old_asset.used_by or "").strip())

    if had_live_custodian:
        try:
            apply_assignment_transition(
                spare,
                used_by=old_asset.used_by,
                department=old_asset.department,
                workstation_no=old_asset.workstation_no,
                location=old_asset.location,
                work_mode=old_asset.work_mode or "office",
                transition_date=date.today(),
                action="handover",
            )
        except AssetLifecycleTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    old_asset.status = "replaced"
    old_asset.used_by = None
    old_asset.workstation_no = None
    old_asset.work_mode = "office"
    old_asset.performed_by = user.full_name
    old_asset.updated_at = utc_now_naive()
    spare.performed_by = user.full_name
    spare.updated_at = utc_now_naive()

    replacement.new_asset_id = spare.id
    replacement.final_action = "replace_with_spare"
    state.procurement_mode = "spare"
    state.spare_asset_id = spare.id
    state.purchase_request_id = None
    state.updated_at = utc_now_naive()

    _replacement_history(
        db,
        asset=old_asset,
        action="Replacement completed with available spare",
        change_type="replacement_completed_spare",
        record=replacement,
        user=user,
        old_value=old_before,
        new_value=custody_state(old_asset),
        remarks=remarks or f"Replaced by available spare {spare.asset_code}",
        field_count=4,
    )
    _replacement_history(
        db,
        asset=spare,
        action="Allocated as replacement asset",
        change_type="replacement_spare_allocated",
        record=replacement,
        user=user,
        old_value=spare_before,
        new_value=custody_state(spare),
        remarks=f"Allocated for {old_asset.asset_code}",
        field_count=4 if had_live_custodian else 0,
    )


def approve_replacement_batch3(
    db: Session,
    *,
    replacement_id: int,
    approval_status: str,
    selected_new_asset_id: int | None,
    final_action: str | None,
    remarks: str | None,
    user: User,
) -> ReplacementRecord:
    record = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == replacement_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    if record.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending replacement requests can receive a Management decision")
    if record.requested_by_user_id is not None and record.requested_by_user_id == user.id:
        raise HTTPException(status_code=409, detail="A user cannot decide their own replacement request")

    clean_remarks = (remarks or "").strip() or None
    if approval_status in {"rejected", "returned"} and not clean_remarks:
        raise HTTPException(status_code=400, detail="Management remarks are required for rejection or return")

    old_asset = db.scalar(select(Asset).where(Asset.id == record.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Replacement request references a missing old asset")
    state = get_or_create_replacement_state(db, record, old_asset)
    now = utc_now_naive()
    record.approval_status = approval_status
    record.approved_by_user_id = user.id
    record.approved_by = user.full_name
    record.approved_by_email = user.email
    record.approved_by_role = user.role
    record.approved_at = now
    record.updated_at = now
    if final_action:
        record.final_action = final_action

    history_action = approval_status
    if approval_status == "approved":
        spare = select_available_spare(
            db,
            old_asset,
            explicit_asset_id=selected_new_asset_id or record.new_asset_id,
        )
        if spare is not None:
            apply_spare_replacement(
                db,
                replacement=record,
                state=state,
                old_asset=old_asset,
                spare=spare,
                user=user,
                remarks=clean_remarks,
            )
            record.decision_remarks = clean_remarks or f"Approved; available spare {spare.asset_code} allocated"
        else:
            purchase_request = create_procurement_request(
                db,
                replacement=record,
                state=state,
                old_asset=old_asset,
            )
            old_asset.status = "replacement_pending"
            record.new_asset_id = None
            record.final_action = "procurement_required"
            link_note = f"No suitable spare available; purchase request {purchase_request.request_code} created"
            record.decision_remarks = f"{clean_remarks}; {link_note}" if clean_remarks else link_note
            _replacement_history(
                db,
                asset=old_asset,
                action="Replacement approved - procurement required",
                change_type="replacement_procurement_required",
                record=record,
                user=user,
                old_value="replacement_pending",
                new_value="replacement_pending",
                remarks=record.decision_remarks,
                field_count=0,
            )
        history_action = "approved"
    elif approval_status == "rejected":
        previous = state.previous_asset_status or ("assigned" if old_asset.used_by else "available")
        old_before = old_asset.status
        old_asset.status = previous
        record.decision_remarks = clean_remarks
        _replacement_history(
            db,
            asset=old_asset,
            action="Replacement rejected",
            change_type="replacement_rejected",
            record=record,
            user=user,
            old_value=old_before,
            new_value=previous,
            remarks=clean_remarks,
        )
    else:
        old_asset.status = "replacement_pending"
        record.decision_remarks = clean_remarks
        _replacement_history(
            db,
            asset=old_asset,
            action="Replacement returned to IT",
            change_type="replacement_returned",
            record=record,
            user=user,
            old_value="replacement_pending",
            new_value="replacement_pending",
            remarks=clean_remarks,
            field_count=0,
        )
        history_action = "returned"

    record_approval_history(
        db,
        workflow_type=WORKFLOW_REPLACEMENT,
        record_id=record.id,
        record_code=record.replacement_code,
        action=history_action,
        from_status="pending",
        to_status=approval_status,
        user=user,
        remarks=record.decision_remarks,
    )
    notify_approval_decision(
        db,
        workflow="replacement",
        record_id=record.id,
        record_code=record.replacement_code,
        reporting_month=record.reporting_month,
        outcome=approval_status,
        decided_by_name=user.full_name,
        remarks=record.decision_remarks,
        event_token=record.approved_at,
        recipient_user_id=record.requested_by_user_id,
    )
    db.commit()
    db.refresh(record)
    return record
