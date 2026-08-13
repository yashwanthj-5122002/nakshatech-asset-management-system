from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import User
from app.modules.employee_portal.service import record_audit
from app.modules.naksha_copilot.schemas import CopilotAnswerResponse, CopilotAskRequest, CopilotStatusResponse
from app.modules.naksha_copilot.service import (
    ALLOWED_ROLES,
    PRIVACY_MODE,
    build_sanitized_context,
    call_gemini,
    copilot_configured,
    enforce_rate_limit,
    request_reference,
    validate_privacy_question,
)

router = APIRouter(prefix="/naksha-copilot", tags=["Naksha Copilot"])


@router.get("/status", response_model=CopilotStatusResponse)
def copilot_status(
    user: User = Depends(require_roles("it", "management", "software_team")),
) -> CopilotStatusResponse:
    return CopilotStatusResponse(
        enabled=settings.naksha_copilot_enabled,
        configured=copilot_configured(),
        model=settings.gemini_model,
        privacy_mode=PRIVACY_MODE,
        allowed_roles=ALLOWED_ROLES,
        requests_per_hour=settings.naksha_copilot_requests_per_hour,
    )


@router.post("/ask", response_model=CopilotAnswerResponse)
async def ask_copilot(
    payload: CopilotAskRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("it", "management", "software_team")),
) -> CopilotAnswerResponse:
    if not settings.naksha_copilot_enabled:
        raise HTTPException(status_code=503, detail="Naksha Copilot is disabled. Normal software features remain available.")
    if not copilot_configured():
        raise HTTPException(status_code=503, detail="Naksha Copilot is enabled but the Gemini API key is not configured.")

    question = validate_privacy_question(payload.question)
    enforce_rate_limit(user.id)
    try:
        context, period_label, sources = build_sanitized_context(
            db,
            period_type=payload.period_type,
            month=payload.month,
            months=payload.months,
            year=payload.year,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request_id, question_hash = request_reference(question)
    try:
        answer = await call_gemini(question=question, context=context)
    except HTTPException as exc:
        record_audit(
            db,
            request=request,
            user=user,
            event_type="naksha_copilot_request",
            result="failed",
            module="naksha_copilot",
            target_type="reporting_period",
            target_id=period_label,
            details={
                "request_id": request_id,
                "question_sha256": question_hash,
                "period_type": payload.period_type,
                "period_label": period_label,
                "model": settings.gemini_model,
                "privacy_mode": PRIVACY_MODE,
                "error_status": exc.status_code,
            },
        )
        db.commit()
        raise

    record_audit(
        db,
        request=request,
        user=user,
        event_type="naksha_copilot_request",
        result="success",
        module="naksha_copilot",
        target_type="reporting_period",
        target_id=period_label,
        details={
            "request_id": request_id,
            "question_sha256": question_hash,
            "period_type": payload.period_type,
            "period_label": period_label,
            "model": settings.gemini_model,
            "privacy_mode": PRIVACY_MODE,
            "sources": sources,
        },
    )
    db.commit()
    return CopilotAnswerResponse(
        request_id=request_id,
        answer=answer,
        period_label=period_label,
        period_type=payload.period_type,
        model=settings.gemini_model,
        privacy_mode=PRIVACY_MODE,
        sources=sources,
    )
