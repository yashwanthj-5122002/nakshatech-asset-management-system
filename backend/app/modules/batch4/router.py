from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import Asset, ReplacementRecord, User
from app.modules.asset_return.analytics_compat import install_asset_return_compatibility
from app.modules.asset_return.mutation_guards import router as asset_return_guard_router
from app.modules.asset_return.router import router as asset_return_router
from app.modules.asset_return.service import active_inventory_assets
from app.modules.batch4.it_control import (
    create_replacement_without_management_approval,
    process_legacy_replacement_without_management_approval,
    resubmit_legacy_replacement_as_it_controlled,
    update_work_without_management_approval,
)
from app.modules.batch4.schemas import (
    ITReplacementCreate,
    ITReplacementProcess,
    ITReplacementResubmit,
    ManagementPurchaseDecision,
)
from app.modules.batch4.service import build_management_control_workbook, management_control_center
from app.modules.it_activity.approval_email import (
    channel_for_request,
    consume_channel_for_application_decision,
    enrich_purchase_request_payload,
    notify_requester_of_decision,
)
from app.modules.it_activity.schemas import PurchaseRequestDecision, PurchaseRequestResponse
from app.modules.it_activity.service import decide_purchase_request, purchase_request_to_dict
from app.schemas.work import WorkApprovalDecision, WorkRecordUpdate
from app.services.asset_lifecycle_service import inventory_summary, is_primary_device_type


router = APIRouter(tags=["Batch 4 Management Control"])
install_asset_return_compatibility()


def _assert_replacement_asset_active(db: Session, asset_id: int | None) -> None:
    if asset_id is None:
        return
    asset = db.get(Asset, asset_id)
    if asset is not None and str(asset.status or "").strip().lower() == "returned_to_vendor":
        raise HTTPException(
            status_code=409,
            detail="This asset has been returned to the vendor and cannot enter replacement processing",
        )


def _assert_replacement_record_active(db: Session, replacement_id: int) -> None:
    record = db.get(ReplacementRecord, replacement_id)
    if record is None:
        return
    _assert_replacement_asset_active(db, record.old_asset_id)
    _assert_replacement_asset_active(db, record.new_asset_id)


def _active_management_control_center(db: Session, month: str | None) -> dict:
    data = management_control_center(db, month)
    all_assets = active_inventory_assets(list(db.scalars(select(Asset)).all()))
    primary_assets = [asset for asset in all_assets if is_primary_device_type(asset.device_type)]
    summary = inventory_summary(primary_assets)
    executive = data.setdefault("executive", {})
    executive.update({
        "primary_assets": summary["total"],
        "assigned_assets": summary["assigned"],
        "available_assets": summary["available"],
        "repair_assets": summary["repair"],
        "replacement_pending_assets": summary["replacement_pending"],
    })
    return data


@router.get("/management/control-center")
def management_control_center_endpoint(
    month: str | None = Query(default=None, description="Optional reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management", "admin")),
) -> dict:
    return _active_management_control_center(db, month)


@router.get("/management/control-center.xlsx")
def management_control_center_excel(
    month: str | None = Query(default=None, description="Optional reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management", "admin")),
):
    data = _active_management_control_center(db, month)
    content = build_management_control_workbook(data)
    suffix = month or "current"
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="NakshaTech_Management_Control_{suffix}.xlsx"'},
    )


@router.post(
    "/management/approvals/{workflow}/{record_id}/decision",
    response_model=PurchaseRequestResponse,
)
def management_purchase_approval_decision(
    workflow: str,
    record_id: int,
    payload: ManagementPurchaseDecision,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management")),
) -> dict:
    if user.role != "management":
        raise HTTPException(status_code=403, detail="Only Management can decide a Purchase Request")
    normalized = workflow.strip().lower()
    if normalized != "purchase_request":
        raise HTTPException(
            status_code=403,
            detail="Management approval is required only for Purchase Requests. IT Work and Asset Replacement are operational IT workflows.",
        )
    request = decide_purchase_request(
        db,
        record_id,
        PurchaseRequestDecision(
            action=payload.action,
            approved_amount=payload.approved_amount,
            management_remarks=payload.remarks,
        ),
        user,
    )
    if channel_for_request(db, request.id) is not None:
        consume_channel_for_application_decision(db, request)
        notify_requester_of_decision(db, request, source="Asset Management System")

    # Keep the post-commit response JSON-safe. The email-channel enrichment is
    # also validated through PurchaseRequestResponse before FastAPI returns it.
    response = PurchaseRequestResponse.model_validate(
        enrich_purchase_request_payload(
            db,
            request,
            purchase_request_to_dict(request, include_history=True),
            include_email_activity=True,
        )
    )
    return response.model_dump(mode="json")


@router.post("/replacements")
def create_replacement_batch4(
    payload: ITReplacementCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    _assert_replacement_asset_active(db, payload.old_asset_id)
    _assert_replacement_asset_active(db, payload.new_asset_id)
    return create_replacement_without_management_approval(db, payload, user)


@router.patch("/replacements/{replacement_id}")
def process_legacy_replacement_batch4(
    replacement_id: int,
    payload: ITReplacementProcess,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    _assert_replacement_record_active(db, replacement_id)
    _assert_replacement_asset_active(db, payload.new_asset_id)
    return process_legacy_replacement_without_management_approval(
        db,
        replacement_id,
        selected_new_asset_id=payload.new_asset_id,
        remarks=payload.remarks,
        user=user,
        approval_recipient_name=payload.approval_recipient_name,
        approval_recipient_email=payload.approval_recipient_email,
    )


@router.put("/replacements/{replacement_id}/resubmit")
def resubmit_legacy_replacement_batch4(
    replacement_id: int,
    payload: ITReplacementResubmit,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
    _assert_replacement_record_active(db, replacement_id)
    return resubmit_legacy_replacement_as_it_controlled(db, replacement_id, payload, user)


@router.patch("/work-records/{work_id}")
def update_work_record_batch4(
    work_id: int,
    payload: WorkRecordUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it", "drone")),
) -> dict:
    return update_work_without_management_approval(db, work_id, payload, user)


@router.post("/work-records/{work_id}/decision")
def disabled_it_work_management_decision(
    work_id: int,
    payload: WorkApprovalDecision,
    user: User = Depends(require_roles("management")),
) -> dict:
    raise HTTPException(
        status_code=410,
        detail="Management approval for IT Work has been removed. Management has read-only oversight; IT completes its own operational work.",
    )


# Guard routes are included first so a stale mutation request is rejected before
# it can reach an older compatible route. The return module then supplies the
# read models, active-inventory dashboard/report overrides and spare monitor
# integration. Unrelated legacy and Batch 3 endpoints remain unchanged.
router.include_router(asset_return_guard_router)
router.include_router(asset_return_router)
