from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class ProjectOpsMeta(Base):
    __tablename__ = "project_ops_meta"

    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), primary_key=True)
    bd_owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    project_manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_deliverables: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium", index=True)
    contract_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    po_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    wo_number: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft", index=True)
    finance_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_to_finance_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completion_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    financial_closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    financial_closure_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    members: Mapped[list["ProjectOpsMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    work_items: Mapped[list["ProjectOpsWorkItem"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectOpsApprovalEvent(Base):
    __tablename__ = "project_ops_approval_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectOpsMember(Base):
    __tablename__ = "project_ops_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id", "member_role", name="uq_project_ops_member_role"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_ops_meta.project_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_role: Mapped[str] = mapped_column(String(30), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    project: Mapped[ProjectOpsMeta] = relationship(back_populates="members")


class ProjectOpsWorkItem(Base):
    __tablename__ = "project_ops_work_items"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_project_ops_work_item_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project_ops_meta.project_id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(120), index=True)
    area_name: Mapped[str] = mapped_column(String(255), index=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(String(50), default="production_assigned", index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    project: Mapped[ProjectOpsMeta] = relationship(back_populates="work_items")
    assignees: Mapped[list["ProjectOpsWorkItemAssignee"]] = relationship(back_populates="work_item", cascade="all, delete-orphan")
    activities: Mapped[list["ProjectOpsDailyActivity"]] = relationship(back_populates="work_item", cascade="all, delete-orphan")
    reviews: Mapped[list["ProjectOpsReview"]] = relationship(back_populates="work_item", cascade="all, delete-orphan")


class ProjectOpsWorkItemAssignee(Base):
    __tablename__ = "project_ops_work_item_assignees"
    __table_args__ = (UniqueConstraint("work_item_id", "user_id", "assignment_role", name="uq_project_ops_work_assignee"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("project_ops_work_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    assignment_role: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[str] = mapped_column(String(40), default="assigned", index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    work_item: Mapped[ProjectOpsWorkItem] = relationship(back_populates="assignees")


class ProjectOpsDailyActivity(Base):
    __tablename__ = "project_ops_daily_activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("project_ops_work_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    activity_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    completed_quantity: Mapped[Decimal | None] = mapped_column(Numeric(16, 3), nullable=True)
    files_completed: Mapped[int] = mapped_column(Integer, default=0)
    working_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="in_progress", index=True)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    work_item: Mapped[ProjectOpsWorkItem] = relationship(back_populates="activities")


class ProjectOpsReview(Base):
    __tablename__ = "project_ops_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_item_id: Mapped[int] = mapped_column(ForeignKey("project_ops_work_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    review_type: Mapped[str] = mapped_column(String(10), index=True)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    work_item: Mapped[ProjectOpsWorkItem] = relationship(back_populates="reviews")
