from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ReplacementWorkflowState(Base):
    """Durable Batch 3 link between replacement, spare stock and procurement.

    The existing replacement/purchase tables remain untouched. This companion
    record preserves the exact pre-request lifecycle state and enforces a single
    procurement request per replacement without destructive schema changes.
    """

    __tablename__ = "batch3_replacement_workflow_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    replacement_record_id: Mapped[int] = mapped_column(
        ForeignKey("replacement_records.id"), unique=True, index=True
    )
    previous_asset_status: Mapped[str] = mapped_column(String(50))
    procurement_mode: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    spare_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id"), nullable=True, index=True
    )
    purchase_request_id: Mapped[int | None] = mapped_column(
        ForeignKey("it_purchase_requests.id"), nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
