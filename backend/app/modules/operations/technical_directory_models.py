from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class TechnicalDepartmentMember(Base):
    """Real technical-team account prepared for a later production cutover.

    Phase 6 only builds and validates the production directory. Existing Phase 2-5
    demo routing stays active until a later explicit go-live phase.
    """

    __tablename__ = "ops_v720_technical_department_members"
    __table_args__ = (
        UniqueConstraint(
            "department_code",
            "user_id",
            name="uq_ops_v720_technical_department_user",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    department_code: Mapped[str] = mapped_column(String(60), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)

    pm_eligible: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    receive_sample_notifications: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    receive_handover_notifications: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    receive_completion_notifications: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
