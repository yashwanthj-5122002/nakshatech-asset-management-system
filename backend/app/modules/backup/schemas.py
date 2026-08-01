from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class BackupRunResponse(BaseModel):
    id: int
    backup_code: str
    backup_type: str
    scope: str
    status: str
    period_start: date | None = None
    period_end: date | None = None
    excel_filename: str | None = None
    database_filename: str | None = None
    minio_filename: str | None = None
    manifest_filename: str | None = None
    excel_size_bytes: int | None = None
    database_size_bytes: int | None = None
    minio_size_bytes: int | None = None
    checksums: dict | None = None
    row_counts: dict | None = None
    message: str | None = None
    created_by: str | None = None
    created_at: datetime
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class BackupStatusResponse(BaseModel):
    root_configured: bool
    storage_root: str | None
    storage_writable: bool
    last_success: BackupRunResponse | None
    last_attempt: BackupRunResponse | None
    scheduled_mode: str
    timezone: str
    pg_dump_available: bool
    database_backup_enabled: bool
    minio_backup_enabled: bool
    notes: list[str]
