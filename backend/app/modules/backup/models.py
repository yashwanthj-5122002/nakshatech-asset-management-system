from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class BackupRun(Base):
    __tablename__ = "backup_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    backup_code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    backup_type: Mapped[str] = mapped_column(String(40), index=True)
    scope: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    excel_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    database_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    minio_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    manifest_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    excel_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    database_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    minio_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    checksums: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    row_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
