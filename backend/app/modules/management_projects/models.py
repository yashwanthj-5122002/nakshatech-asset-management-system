from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.entities import utc_now


class ManagementProjectLink(Base):
    """Provenance link: management intake -> shared operational FinanceProject.

    The authoritative invoice, production and payment records remain in their
    existing tables; this table never duplicates those records.
    """

    __tablename__ = "management_project_links"

    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), primary_key=True)
    management_client_id: Mapped[int] = mapped_column(ForeignKey("management_client_intakes.id", ondelete="RESTRICT"), index=True)
    finance_client_id: Mapped[int] = mapped_column(ForeignKey("finance_clients.id", ondelete="RESTRICT"), index=True)
    source_person_name: Mapped[str] = mapped_column(String(255))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
