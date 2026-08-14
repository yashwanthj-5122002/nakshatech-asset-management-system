from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.entities import User
from app.modules.asset_return.router import router as asset_return_router
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


router = APIRouter(tags=["Batch 4 Management Control"])


@router.get("/management/control-center")
def management_control_center_endpoint(
    month: str | None = Query(default=None, description="Optional reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management", "admin")),
) -> dict:
    return management_control_center(db, month)


@router.get("/management/control-center.xlsx")
def management_control_center_excel(
    month: str | None = Query(default=None, description="Optional reporting month in YYYY-MM format"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("management", "admin")),
):
    data = management_control_center(db, month)
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
    return create_replacement_without_management_approval(db, payload, user)


@router.patch("/replacements/{replacement_id}")
def process_legacy_replacement_batch4(
    replacement_id: int,
    payload: ITReplacementProcess,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "it")),
) -> dict:
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


# The rental/vendor-return module is additive. Its few exact endpoint overrides
# (Asset list/dashboard/report reads and Component Changes) are intentionally
# included through the existing Batch 4 route replacement mechanism so unrelated
# legacy and Batch 3 operations remain untouched.
router.include_router(asset_return_router)
