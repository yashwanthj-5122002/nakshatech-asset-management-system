from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.router import (
    _next_code,
    _record_history,
    _replacement_response,
    _serialise_changes,
    _work_response,
    update_work_record as legacy_update_work_record,
)
from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import Asset, ReplacementRecord, User, WorkRecord
from app.modules.batch3.common import acquire_asset_code_lock
from app.modules.batch3.replacement_workflow import (
    apply_spare_replacement,
    create_procurement_request,
    get_or_create_replacement_state,
    select_available_spare,
)
from app.modules.it_activity.approval_email import issue_purchase_approval_email, normalize_approval_email
from app.schemas.replacement import ReplacementCreate, ReplacementResubmit
from app.schemas.work import WorkRecordUpdate
from app.services.approval_workflow_service import utc_now_naive, validate_it_work_operational_transition


TERMINAL_REPLACEMENT_ASSET_STATUSES = {"replaced", "retired", "disposed", "missing"}


def _clear_replacement_approval_fields(record: ReplacementRecord) -> None:
    record.approval_status = "not_required"
    record.approved_by_user_id = None
    record.approved_by = None
    record.approved_by_email = None
    record.approved_by_role = None
    record.approved_at = None


def _approval_recipient_from_payload(payload, *, requester_email: str) -> tuple[str | None, str | None]:
    name = str(getattr(payload, "approval_recipient_name", "") or "").strip()
    email = str(getattr(payload, "approval_recipient_email", "") or "").strip()
    if not name and not email:
        # Direct service calls and historical tests remain backward compatible.
        # Live Batch 4 HTTP schemas require both values.
        return None, None
    if not name or not email:
        raise HTTPException(status_code=422, detail="Approval Recipient Name and Approval Email must both be provided")
    return name, normalize_approval_email(email, requester_email=requester_email)


def _process_replacement(
    db: Session,
    *,
    record: ReplacementRecord,
    old_asset: Asset,
    selected_new_asset_id: int | None,
    user: User,
    remarks: str | None,
    approval_recipient_name: str | None = None,
    approval_recipient_email: str | None = None,
) -> ReplacementRecord:
    state = get_or_create_replacement_state(db, record, old_asset)
    _clear_replacement_approval_fields(record)
    old_asset.status = "replacement_pending"
    purchase_request = None

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
            remarks=remarks or "IT technical replacement processed using available spare stock",
        )
        record.decision_remarks = (
            f"IT technical replacement completed using available spare {spare.asset_code}. "
            "Management approval was not required because no purchase was needed."
        )
    else:
        purchase_request = create_procurement_request(
            db,
            replacement=record,
            state=state,
            old_asset=old_asset,
        )
        # Batch 4 authority model: the technical replacement is controlled by IT;
        # Management approval applies only to the resulting expenditure request.
        purchase_request.business_reason = (
            f"IT replacement {record.replacement_code}: {record.reason}"
        )
        purchase_request.it_remarks = (
            f"Automatically linked to {record.replacement_code}. No suitable Available spare was found; "
            "Management purchase permission is required before procurement."
        )
        record.new_asset_id = None
        record.final_action = "procurement_required"
        record.decision_remarks = (
            f"No suitable spare available. Purchase Request {purchase_request.request_code} created and "
            "sent to Management for purchase approval."
        )
        _record_history(
            db,
            old_asset,
            "Replacement requires purchase approval",
            user,
            old_value="replacement_pending",
            new_value="replacement_pending",
            remarks=record.decision_remarks,
            change_type="replacement_procurement_required",
            reason=record.reason,
            batch_code=record.replacement_code,
            field_count=0,
            reporting_month=record.reporting_month,
        )

    record.updated_at = utc_now_naive()
    db.commit()
    db.refresh(record)
    if purchase_request is not None and approval_recipient_name and approval_recipient_email:
        issue_purchase_approval_email(
            db,
            purchase_request,
            approval_recipient_name,
            approval_recipient_email,
        )
    return record


def create_replacement_without_management_approval(
    db: Session,
    payload: ReplacementCreate,
    user: User,
) -> dict:
    approval_recipient_name, approval_recipient_email = _approval_recipient_from_payload(
        payload,
        requester_email=user.email,
    )
    acquire_asset_code_lock(db)
    old_asset = db.scalar(select(Asset).where(Asset.id == payload.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=404, detail="Old asset not found")
    if str(old_asset.status or "").strip().lower() in TERMINAL_REPLACEMENT_ASSET_STATUSES:
        raise HTTPException(status_code=409, detail="A finalized asset cannot enter replacement processing again")

    existing = db.scalar(
        select(ReplacementRecord.id)
        .where(
            ReplacementRecord.old_asset_id == old_asset.id,
            or_(
                ReplacementRecord.approval_status.in_(["pending", "returned"]),
                ReplacementRecord.final_action == "procurement_required",
            ),
        )
        .limit(1)
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="This asset already has an active replacement workflow")

    previous_status = old_asset.status
    values = payload.model_dump()
    values.pop("approval_recipient_name", None)
    values.pop("approval_recipient_email", None)
    values["reporting_month"] = normalize_reporting_month(values.get("reporting_month"))
    selected_new_asset_id = values.pop("new_asset_id", None)
    values["final_action"] = "replacement_pending"

    record = ReplacementRecord(
        replacement_code=_next_code(db, ReplacementRecord, ReplacementRecord.replacement_code, "RPL"),
        new_asset_id=selected_new_asset_id,
        **values,
        requested_by_user_id=user.id,
        requested_by=user.full_name,
        requested_by_email=user.email,
        requested_by_role=user.role,
        approval_status="not_required",
    )
    old_asset.status = "replacement_pending"
    db.add(record)
    db.flush()
    get_or_create_replacement_state(db, record, old_asset, previous_status=previous_status)
    _record_history(
        db,
        old_asset,
        "Replacement initiated by IT",
        user,
        old_value=previous_status,
        new_value="replacement_pending",
        remarks=payload.reason,
        change_type="replacement_requested",
        reason=payload.reason,
        batch_code=record.replacement_code,
        field_count=1,
        reporting_month=record.reporting_month,
    )
    processed = _process_replacement(
        db,
        record=record,
        old_asset=old_asset,
        selected_new_asset_id=selected_new_asset_id,
        user=user,
        remarks=payload.inspection_finding or payload.reason,
        approval_recipient_name=approval_recipient_name,
        approval_recipient_email=approval_recipient_email,
    )
    return _replacement_response(processed)


def process_legacy_replacement_without_management_approval(
    db: Session,
    replacement_id: int,
    *,
    selected_new_asset_id: int | None,
    remarks: str | None,
    user: User,
    approval_recipient_name: str | None = None,
    approval_recipient_email: str | None = None,
) -> dict:
    if approval_recipient_name or approval_recipient_email:
        if not approval_recipient_name or not approval_recipient_email:
            raise HTTPException(status_code=422, detail="Approval Recipient Name and Approval Email must both be provided")
        approval_recipient_email = normalize_approval_email(approval_recipient_email, requester_email=user.email)
    record = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == replacement_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    if record.final_action in {"replace_with_spare", "procurement_completed_replacement"}:
        raise HTTPException(status_code=409, detail="This replacement workflow is already completed")
    if record.final_action == "procurement_required":
        raise HTTPException(status_code=409, detail="This replacement already has a linked Purchase Request")
    if record.approval_status not in {"pending", "returned", "not_required"}:
        raise HTTPException(status_code=409, detail="This legacy replacement cannot be reprocessed")

    old_asset = db.scalar(select(Asset).where(Asset.id == record.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Replacement references a missing old asset")
    processed = _process_replacement(
        db,
        record=record,
        old_asset=old_asset,
        selected_new_asset_id=selected_new_asset_id,
        user=user,
        remarks=remarks or "Legacy replacement migrated to IT-controlled Batch 4 workflow",
        approval_recipient_name=approval_recipient_name,
        approval_recipient_email=approval_recipient_email,
    )
    return _replacement_response(processed)


def resubmit_legacy_replacement_as_it_controlled(
    db: Session,
    replacement_id: int,
    payload: ReplacementResubmit,
    user: User,
) -> dict:
    """Absorb the old resubmit-to-Management path into IT technical control.

    This endpoint is kept only for backward-compatible clients/bookmarks. It can
    update the returned legacy record, but it never recreates a Management
    replacement approval. The replacement is processed immediately by IT.
    """
    approval_recipient_name, approval_recipient_email = _approval_recipient_from_payload(
        payload,
        requester_email=user.email,
    )
    record = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == replacement_id)
        .with_for_update()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Replacement record not found")
    if record.approval_status not in {"pending", "returned", "not_required"}:
        raise HTTPException(status_code=409, detail="Only an active legacy replacement can be migrated")
    if record.final_action in {"replace_with_spare", "procurement_required", "procurement_completed_replacement"}:
        raise HTTPException(status_code=409, detail="This replacement workflow has already been processed")

    record.reporting_month = normalize_reporting_month(payload.reporting_month)
    record.reason = payload.reason.strip()
    record.damage_category = payload.damage_category
    record.inspection_finding = payload.inspection_finding
    record.final_action = "replacement_pending"
    record.new_asset_id = payload.new_asset_id
    record.updated_at = utc_now_naive()

    old_asset = db.scalar(select(Asset).where(Asset.id == record.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Replacement references a missing old asset")
    return _replacement_response(_process_replacement(
        db,
        record=record,
        old_asset=old_asset,
        selected_new_asset_id=payload.new_asset_id,
        user=user,
        remarks=payload.inspection_finding or payload.reason,
        approval_recipient_name=approval_recipient_name,
        approval_recipient_email=approval_recipient_email,
    ))


def update_work_without_management_approval(
    db: Session,
    work_id: int,
    payload: WorkRecordUpdate,
    user: User,
) -> dict:
    work = db.scalar(
        select(WorkRecord)
        .where(WorkRecord.id == work_id)
        .with_for_update()
    )
    if work is None:
        raise HTTPException(status_code=404, detail="Work record not found")

    # Preserve the existing Drone workflow completely; this Batch 4 authority
    # change applies only to IT work.
    if work.module != "it":
        return legacy_update_work_record(work_id, payload, db, user)
    if user.role not in {"it", "admin"}:
        raise HTTPException(status_code=403, detail="Management has read-only visibility of IT work")

    values = payload.model_dump(exclude_unset=True)
    if "approval_status" in values:
        raise HTTPException(status_code=400, detail="IT Work does not use a Management approval status")
    if "reporting_month" in values:
        values["reporting_month"] = normalize_reporting_month(values["reporting_month"])

    target_status = values.get("status")
    old_status = work.status

    # Legacy pending-approval records are normalized the first time IT touches
    # them. No Management action is required.
    if work.approval_status in {"pending", "returned"}:
        work.approval_status = "not_required"
        work.approved_by_user_id = None
        work.approved_by_name = None
        work.approved_by_email = None
        work.approved_by_role = None
        work.approved_at = None
        work.approval_comments = None

    if old_status == "completed" and target_status not in {None, "completed"}:
        raise HTTPException(status_code=409, detail="Completed IT work is final. Create a follow-up work record for additional work")

    if target_status and target_status != old_status:
        validate_it_work_operational_transition(old_status, target_status)

    changed: dict[str, dict[str, object]] = {}
    for key, value in values.items():
        old_value = getattr(work, key)
        if old_value != value:
            changed[key] = {"from": old_value, "to": value}
            setattr(work, key, value)

    if target_status == "completed" and old_status != "completed":
        now = utc_now_naive()
        work.completed_at = now
        work.approval_status = "not_required"
        work.submitted_by_user_id = user.id
        work.submitted_by_name = user.full_name
        work.submitted_by_email = user.email
        work.submitted_by_role = user.role
        work.submitted_at = now
        work.approved_by_user_id = None
        work.approved_by_name = None
        work.approved_by_email = None
        work.approved_by_role = None
        work.approved_at = None
        work.approval_comments = None
    elif target_status == "completed":
        work.completed_at = work.completed_at or utc_now_naive()
        work.approval_status = "not_required"

    if work.asset and changed:
        _record_history(
            db,
            work.asset,
            "Work record updated",
            user,
            old_value=_serialise_changes({"work_code": work.work_code, "status": old_status}),
            new_value=_serialise_changes({"work_code": work.work_code, **{k: v["to"] for k, v in changed.items()}}),
            remarks=work.resolution or work.issue_description,
            change_type="work_record_updated",
            reason=work.resolution or work.issue_description or "Work record updated",
            reporting_month=work.reporting_month,
        )

    db.commit()
    db.refresh(work)
    return _work_response(work)
