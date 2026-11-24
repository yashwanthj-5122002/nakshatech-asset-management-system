from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ManagementClientIntake(Base):
    """Isolated client register; not a FinanceProject or a BD-owned client."""

    __tablename__ = "management_client_intakes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    client_name: Mapped[str] = mapped_column(String(255), index=True)
    client_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str] = mapped_column(String(100), default="India")
    gst_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_person_name: Mapped[str] = mapped_column(String(255))
    contact_person_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_person_phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    work_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_person_name: Mapped[str] = mapped_column(String(255), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ManagementAdditionalProjectRequest(Base):
    """Persistent source-owned request. No duplicate client or project is created here."""

    __tablename__ = "management_additional_project_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    management_client_id: Mapped[int] = mapped_column(ForeignKey("management_client_intakes.id", ondelete="RESTRICT"), index=True)
    requested_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str] = mapped_column(String(16), nullable=False, default="regular")
    pilot_payment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_start_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    created_project_id: Mapped[int | None] = mapped_column(ForeignKey("finance_projects.id", ondelete="RESTRICT"), nullable=True, unique=True)
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class ManagementProjectClassification(Base):
    """Permanent classification for a Finance-created Management project."""

    __tablename__ = "management_project_classifications"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("finance_projects.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    project_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="regular"
    )
    pilot_payment_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now
    )
