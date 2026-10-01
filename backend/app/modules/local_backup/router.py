from __future__ import annotations

from hmac import compare_digest
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.entities import Asset
from app.modules.drone.models import DroneSurveyAsset
from app.modules.local_backup.service import (
    EXCEL_MIME,
    VALID_BACKUP_ROLES,
    build_current_month_workbook,
    content_sha256,
    current_month_period,
    local_now,
)


router = APIRouter(prefix="/local-backup", tags=["local-backup"])
TOKEN_HEADER = "X-Naksha-Backup-Token"


def require_backup_agent_token(
    x_naksha_backup_token: str | None = Header(default=None, alias=TOKEN_HEADER),
) -> None:
    if not settings.local_backup_agent_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local backup agent endpoint is disabled",
        )
    configured = settings.local_backup_agent_token.strip()
    supplied = (x_naksha_backup_token or "").strip()
    if len(configured) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local backup agent token is not configured securely",
        )
    if not supplied or not compare_digest(configured, supplied):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid backup agent token")


def _require_permitted_backup_role(role: str) -> str:
    """Reject any export scope this shared agent secret is not configured for.

    The agent proves who it is with one shared token, so the requested role must be
    pinned server-side (LOCAL_BACKUP_AGENT_ROLES) instead of being taken from the
    query string. Without this, a leaked agent token is enough to ask for the
    full-access "admin" workbook, which includes the System Users sheet.
    """
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_BACKUP_ROLES:
        raise HTTPException(status_code=400, detail="Role must be software_team, admin, management, it or drone")
    if normalized_role not in settings.local_backup_agent_role_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This backup agent is not permitted to export the requested role scope",
        )
    return normalized_role


@router.get("/health", dependencies=[Depends(require_backup_agent_token)])
def local_backup_health(db: Session = Depends(get_db)) -> dict:
    # Force a real database round-trip so the Windows agent can distinguish an API
    # process from a healthy application/database connection.
    db.execute(text("SELECT 1"))
    period = current_month_period()
    return {
        "status": "healthy",
        "service": "NakshaTech Local Backup Export",
        "server_time": local_now().isoformat(),
        "reporting_month": period.key,
        "it_assets": db.scalar(select(func.count(Asset.id))) or 0,
        "drone_assets": db.scalar(select(func.count(DroneSurveyAsset.id))) or 0,
        "roles": sorted(set(settings.local_backup_agent_role_list) & VALID_BACKUP_ROLES),
        "schedule": {
            "health_check_minutes": 5,
            "current_excel_refresh": "hourly at minute 55",
            "month_close": "local current file is frozen at the month boundary",
        },
    }


@router.get("/export.xlsx", dependencies=[Depends(require_backup_agent_token)])
def export_local_backup(
    role: str = Query(..., description="software_team, admin, management, it or drone"),
    db: Session = Depends(get_db),
) -> Response:
    normalized_role = _require_permitted_backup_role(role)

    data, period, row_counts = build_current_month_workbook(db, normalized_role)
    checksum = content_sha256(data)
    filename = f"NakshaTech_{normalized_role.title()}_Current_{period.key}.xlsx"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Content-SHA256": checksum,
        "X-Backup-Month": period.key,
        "X-Backup-Role": normalized_role,
        "X-Generated-At": local_now().isoformat(),
        "X-Row-Counts": json.dumps(row_counts, separators=(",", ":")),
        "ETag": f'"{checksum}"',
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    }
    return Response(content=data, media_type=EXCEL_MIME, headers=headers)
