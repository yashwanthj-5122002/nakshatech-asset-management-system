
import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User
from app.modules.employee_portal.service import record_audit
from app.modules.naksha_copilot.service import enforce_rate_limit

from app.modules.bd_ai.schemas import (
    BDAIAnalysis,
    BDAIContext,
    BDAIRefineRequest,
)
from app.modules.bd_ai.service import generate_analysis


router = APIRouter(
    prefix="/bd-ai",
    tags=["BD AI"],
)

AUTHORIZED_MANAGEMENT_EMAILS = {
    "vinod@nakshatech.com",
    "chethan@nakshatech.com",
}


def require_bd_ai_user(
    user: User = Depends(require_roles("bd", "management")),
) -> User:
    role = str(user.role or "").strip().lower()
    email = str(user.email or "").strip().lower()

    if role == "bd":
        return user

    if (
        role == "management"
        and email in AUTHORIZED_MANAGEMENT_EMAILS
    ):
        return user

    raise HTTPException(
        status_code=403,
        detail="BD AI access denied.",
    )


@router.get("/status")
def bd_ai_status(
    user: User = Depends(require_bd_ai_user),
):
    return {
        "configured": bool(settings.gemini_api_key.strip()),
        "model": settings.gemini_model,
        "requests_per_hour": settings.naksha_copilot_requests_per_hour,
    }


async def _run_analysis(
    *,
    context: BDAIContext,
    stage: str,
    request: Request,
    db: Session,
    user: User,
    previous: BDAIAnalysis | None = None,
    answers=None,
) -> BDAIAnalysis:

    # Reuse the existing limiter. This currently shares
    # the per-user quota with Naksha Copilot.
    enforce_rate_limit(user.id)

    fingerprint = hashlib.sha256(
        context.requirements.encode("utf-8")
    ).hexdigest()

    try:
        result = await generate_analysis(
            context,
            previous=previous,
            answers=answers,
        )
    except HTTPException as exc:
        record_audit(
            db,
            request=request,
            user=user,
            event_type="bd_ai_analysis",
            result="failed",
            module="bd_ai",
            target_type="requirement_draft",
            target_id="unsaved",
            details={
                "stage": stage,
                "input_sha256": fingerprint,
                "error_status": exc.status_code,
            },
        )
        db.commit()
        raise

    record_audit(
        db,
        request=request,
        user=user,
        event_type="bd_ai_analysis",
        result="success",
        module="bd_ai",
        target_type="requirement_draft",
        target_id="unsaved",
        details={
            "stage": stage,
            "input_sha256": fingerprint,
            "model": settings.gemini_model,
        },
    )
    db.commit()
    return result


@router.post(
    "/summarize",
    response_model=BDAIAnalysis,
)
async def summarize_requirements(
    payload: BDAIContext,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_bd_ai_user),
):
    return await _run_analysis(
        context=payload,
        stage="summarize",
        request=request,
        db=db,
        user=user,
    )


@router.post(
    "/refine",
    response_model=BDAIAnalysis,
)
async def refine_requirements(
    payload: BDAIRefineRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_bd_ai_user),
):
    return await _run_analysis(
        context=payload.context,
        previous=payload.previous,
        answers=payload.answers,
        stage="refine",
        request=request,
        db=db,
        user=user,
    )
