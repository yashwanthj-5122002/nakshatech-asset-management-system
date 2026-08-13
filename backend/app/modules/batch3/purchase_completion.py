from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lib.reporting_month import normalize_reporting_month
from app.models.entities import ApprovalDecisionHistory, Asset, ReplacementRecord, User
from app.modules.batch3.models import ReplacementWorkflowState
from app.modules.batch3.replacement_workflow import apply_spare_replacement
from app.modules.it_activity.models import ITPurchaseRecord, ITPurchaseRequest, ITPurchaseRequestHistory
from app.modules.it_activity.schemas import PurchaseCreate
from app.modules.it_activity.service import make_code
from app.services.approval_workflow_service import WORKFLOW_PURCHASE_REQUEST, utc_now_naive
from app.services.asset_lifecycle_service import canonical_device_type, lifecycle_bucket

def _finalize_procured_replacement(
    db: Session,
    *,
    state: ReplacementWorkflowState,
    purchase_request: ITPurchaseRequest,
    new_asset: Asset,
    user: User,
) -> None:
    replacement = db.scalar(
        select(ReplacementRecord)
        .where(ReplacementRecord.id == state.replacement_record_id)
        .with_for_update()
    )
    if replacement is None:
        raise HTTPException(status_code=409, detail="Linked replacement record no longer exists")
    old_asset = db.scalar(select(Asset).where(Asset.id == replacement.old_asset_id).with_for_update())
    if old_asset is None:
        raise HTTPException(status_code=409, detail="Linked old asset no longer exists")
    if canonical_device_type(new_asset.device_type) != canonical_device_type(old_asset.device_type):
        raise HTTPException(status_code=409, detail="Purchased replacement asset must use the same device type as the old asset")
    if lifecycle_bucket(new_asset.status) != "available" or str(new_asset.used_by or "").strip():
        raise HTTPException(status_code=409, detail="Purchased replacement asset must be available before allocation")

    apply_spare_replacement(
        db,
        replacement=replacement,
        state=state,
        old_asset=old_asset,
        spare=new_asset,
        user=user,
        remarks=f"Procurement completed through {purchase_request.request_code}",
    )
    replacement.final_action = "procurement_completed_replacement"
    state.procurement_mode = "purchase"
    state.spare_asset_id = new_asset.id
    state.updated_at = utc_now_naive()


def create_purchase_record_batch3(
    db: Session,
    payload: PurchaseCreate,
    user: User,
) -> ITPurchaseRecord:
    asset = None
    if payload.linked_asset_id is not None:
        asset = db.scalar(select(Asset).where(Asset.id == payload.linked_asset_id).with_for_update())
        if asset is None:
            raise HTTPException(status_code=404, detail="Linked asset was not found")

    purchase_request = None
    state = None
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
        state = db.scalar(
            select(ReplacementWorkflowState)
            .where(ReplacementWorkflowState.purchase_request_id == purchase_request.id)
            .with_for_update()
        )
        if state is not None and asset is None:
            raise HTTPException(
                status_code=400,
                detail="Link the received replacement asset before completing procurement for this replacement request",
            )
        if state is not None and asset is not None:
            replacement = db.get(ReplacementRecord, state.replacement_record_id)
            old_asset = db.get(Asset, replacement.old_asset_id) if replacement else None
            if old_asset is None:
                raise HTTPException(status_code=409, detail="Linked replacement asset record is incomplete")
            if canonical_device_type(asset.device_type) != canonical_device_type(old_asset.device_type):
                raise HTTPException(status_code=409, detail="Linked purchased asset must match the replacement device type")
            if lifecycle_bucket(asset.status) != "available" or str(asset.used_by or "").strip():
                raise HTTPException(status_code=409, detail="Linked purchased asset must be Available and unassigned")
    elif user.role == "it":
        raise HTTPException(status_code=400, detail="Select an approved purchase request before creating a purchase record")

    total = payload.total_price
    if total is None and payload.unit_price is not None:
        total = payload.unit_price * payload.quantity
    approved_by = (payload.approved_by or "").strip() or None
    department = (payload.department or "").strip() or None
    if purchase_request is not None:
        approved_by = approved_by or purchase_request.decided_by_name
        department = department or purchase_request.requesting_department

    record = ITPurchaseRecord(
        purchase_code=make_code("ITPO"),
        purchase_request_id=purchase_request.id if purchase_request else None,
        linked_asset_id=asset.id if asset else None,
        linked_asset_code_snapshot=asset.asset_code if asset else None,
        purchase_date=payload.purchase_date,
        po_number=(payload.po_number or "").strip() or None,
        asset_number=(payload.asset_number or "").strip() or None,
        supplier_name=payload.supplier_name.strip(),
        supplier_contact=(payload.supplier_contact or "").strip() or None,
        item_description=payload.item_description.strip(),
        warranty_number=(payload.warranty_number or "").strip() or None,
        quantity=payload.quantity,
        unit_price=payload.unit_price,
        total_price=total,
        received_date=payload.received_date,
        inspection_status=(payload.inspection_status or "").strip() or None,
        approved_by=approved_by,
        department=department,
        remarks=(payload.remarks or "").strip() or None,
        imported=False,
        created_by=user.full_name,
        created_by_email=user.email,
        created_by_role=user.role,
        reporting_month=normalize_reporting_month(payload.reporting_month),
    )
    if purchase_request is not None:
        # Keep the bidirectional SQLAlchemy relationship synchronized in the
        # current Session as soon as procurement creates the purchase record.
        # Setting only purchase_request_id writes the correct FK, but an already
        # loaded request.purchase_record could otherwise remain cached as None
        # until a new Session/explicit expiry.
        record.purchase_request = purchase_request
    db.add(record)
    db.flush()

    if purchase_request is not None:
        previous_status = purchase_request.status
        now = utc_now_naive()
        purchase_request.status = "purchase_completed"
        purchase_request.purchase_completed_at = now
        purchase_request.updated_at = now
        db.add(ITPurchaseRequestHistory(
            request_id=purchase_request.id,
            action="purchase_completed",
            from_status=previous_status,
            to_status="purchase_completed",
            remarks=f"Purchase record {record.purchase_code} created",
            performed_by_user_id=user.id,
            performed_by_name=user.full_name,
            performed_by_email=user.email,
            performed_by_role=user.role,
            created_at=now,
        ))
        db.add(ApprovalDecisionHistory(
            workflow_type=WORKFLOW_PURCHASE_REQUEST,
            record_id=purchase_request.id,
            record_code=purchase_request.request_code,
            action="purchase_completed",
            from_status=previous_status,
            to_status="purchase_completed",
            remarks=f"Purchase record {record.purchase_code} created",
            performed_by_user_id=user.id,
            performed_by_name=user.full_name,
            performed_by_email=user.email,
            performed_by_role=user.role,
            created_at=now,
        ))
        if state is not None and asset is not None:
            _finalize_procured_replacement(
                db,
                state=state,
                purchase_request=purchase_request,
                new_asset=asset,
                user=user,
            )

    db.commit()
    db.refresh(record)
    return record
