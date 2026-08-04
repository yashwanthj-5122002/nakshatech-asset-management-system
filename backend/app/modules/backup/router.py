from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.core.roles import is_admin_equivalent
from app.models.entities import User
from app.modules.backup.models import BackupRun
from app.modules.backup.schemas import BackupRunResponse, BackupStatusResponse
from app.modules.backup.service import (
    EXCEL_MIME,
    VALID_BACKUP_TYPES,
    VALID_SCOPES,
    backup_root,
    build_backup_workbook,
    create_backup,
    pg_dump_available,
    resolve_backup_file,
    resolve_period,
    storage_writable,
)

router = APIRouter(tags=["backups"])


def _allowed_scope(user: User, requested: str | None) -> str:
    if is_admin_equivalent(user.role) or user.role == "management":
        scope = requested or "all"
        if scope not in VALID_SCOPES:
            raise HTTPException(status_code=400, detail="Scope must be all, it or drone")
        return scope
    if user.role == "it":
        if requested and requested != "it":
            raise HTTPException(status_code=403, detail="IT users can export IT data only")
        return "it"
    if user.role == "drone":
        if requested and requested != "drone":
            raise HTTPException(status_code=403, detail="Drone users can export Drone data only")
        return "drone"
    raise HTTPException(status_code=403, detail="Insufficient permission")


def _can_access_run(user: User, run: BackupRun) -> bool:
    if is_admin_equivalent(user.role) or user.role == "management":
        return True
    return run.scope == user.role


@router.get("/status", response_model=BackupStatusResponse)
def backup_status(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin", "management", "it", "drone")),
) -> BackupStatusResponse:
    last_attempt = db.scalar(select(BackupRun).order_by(desc(BackupRun.created_at)).limit(1))
    last_success = db.scalar(
        select(BackupRun)
        .where(BackupRun.status.in_(["completed", "completed_with_warnings"]))
        .order_by(desc(BackupRun.completed_at))
        .limit(1)
    )
    notes = [
        "Automatic backups are created by the server cron job; they do not depend on an open browser.",
        "Excel files are readable operational copies. The database dump is required for full restoration.",
    ]
    if not pg_dump_available() and settings.backup_database_enabled:
        notes.append("pg_dump is not currently available in this runtime; configure PG_DUMP_BIN on the production server.")
    return BackupStatusResponse(
        root_configured=bool(settings.backup_root),
        storage_root=str(backup_root()) if is_admin_equivalent(user.role) else None,
        storage_writable=storage_writable(),
        last_success=BackupRunResponse.model_validate(last_success) if last_success else None,
        last_attempt=BackupRunResponse.model_validate(last_attempt) if last_attempt else None,
        scheduled_mode="Daily cron: daily DB + Excel + current-month Excel; month/year/FY files at boundaries",
        timezone=settings.backup_timezone,
        pg_dump_available=pg_dump_available(),
        database_backup_enabled=settings.backup_database_enabled,
        minio_backup_enabled=settings.backup_minio_enabled,
        notes=notes,
    )


@router.get("/history", response_model=list[BackupRunResponse])
def backup_history(
    limit: int = Query(default=50, ge=1, le=250),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[BackupRunResponse]:
    allowed_scope = _allowed_scope(user, scope)
    query = select(BackupRun).order_by(desc(BackupRun.created_at)).limit(limit)
    if not (is_admin_equivalent(user.role) or user.role == "management") or allowed_scope != "all":
        query = query.where(BackupRun.scope == allowed_scope)
    rows = db.scalars(query).all()
    return [BackupRunResponse.model_validate(row) for row in rows]


@router.get("/export.xlsx")
def export_backup_excel(
    backup_type: str = Query(default="current_month"),
    period: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if backup_type not in VALID_BACKUP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid backup type")
    allowed_scope = _allowed_scope(user, scope)
    try:
        stream, resolved, _counts, _warnings = build_backup_workbook(
            db,
            backup_type,
            allowed_scope,
            period,
            user.email,
            include_admin_data=is_admin_equivalent(user.role) and allowed_scope == "all",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"NakshaTech {allowed_scope.upper()} {resolved.label.replace('—', '-')}.xlsx"
    safe_name = filename.replace("/", "-").replace("\\", "-")
    return StreamingResponse(
        stream,
        media_type=EXCEL_MIME,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


@router.post("/run", response_model=BackupRunResponse)
def run_backup_now(
    backup_type: str = Query(default="daily"),
    period: str | None = Query(default=None),
    scope: str = Query(default="all"),
    include_database: bool = Query(default=True),
    include_minio: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
) -> BackupRunResponse:
    if backup_type not in VALID_BACKUP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid backup type")
    if scope not in VALID_SCOPES:
        raise HTTPException(status_code=400, detail="Invalid scope")
    try:
        resolve_period(backup_type, period)
        run = create_backup(
            db,
            backup_type,
            scope,
            period,
            user.email,
            include_database=include_database,
            include_minio=include_minio,
            include_admin_data=scope == "all",
        )
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=409 if "already running" in str(exc).lower() else 400, detail=str(exc)) from exc
    return BackupRunResponse.model_validate(run)


@router.get("/files/{run_id}/{file_type}")
def download_saved_backup(
    run_id: int,
    file_type: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    run = db.get(BackupRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Backup record not found")
    if not _can_access_run(user, run):
        raise HTTPException(status_code=403, detail="Insufficient permission")
    if file_type in {"database", "minio", "manifest"} and not is_admin_equivalent(user.role):
        raise HTTPException(status_code=403, detail="Only Admin or Software Team can download disaster-recovery files")
    try:
        path = resolve_backup_file(run, file_type)
    except (FileNotFoundError, PermissionError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media_type = EXCEL_MIME if path.suffix.lower() == ".xlsx" else "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)
