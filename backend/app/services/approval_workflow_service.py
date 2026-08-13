from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.entities import ApprovalDecisionHistory, User

WORKFLOW_IT_WORK = "it_work"
WORKFLOW_REPLACEMENT = "asset_replacement"
WORKFLOW_PURCHASE_REQUEST = "purchase_request"

IT_WORK_OPERATIONAL_TRANSITIONS: dict[str, set[str]] = {
    "open": {"in_progress"},
    "in_progress": {"completed"},
}


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_it_work_operational_transition(current_status: str, target_status: str) -> None:
    allowed = IT_WORK_OPERATIONAL_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Invalid IT work transition: {current_status} -> {target_status}",
        )


def record_approval_history(
    db: Session,
    *,
    workflow_type: str,
    record_id: int,
    record_code: str,
    action: str,
    from_status: str | None,
    to_status: str,
    user: User,
    remarks: str | None = None,
) -> ApprovalDecisionHistory:
    history = ApprovalDecisionHistory(
        workflow_type=workflow_type,
        record_id=record_id,
        record_code=record_code,
        action=action,
        from_status=from_status,
        to_status=to_status,
        remarks=(remarks or "").strip() or None,
        performed_by_user_id=user.id,
        performed_by_name=user.full_name,
        performed_by_email=user.email,
        performed_by_role=user.role,
        created_at=utc_now_naive(),
    )
    db.add(history)
    return history
