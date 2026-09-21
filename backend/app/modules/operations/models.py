from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.entities import utc_now


class BDOpportunity(Base):
    __tablename__ = "ops_v701_bd_opportunities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_code: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("finance_clients.id", ondelete="SET NULL"), nullable=True, index=True)
    client_name_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    requirement: Mapped[str] = mapped_column(Text)
    service_type: Mapped[str] = mapped_column(String(80), default="ortho_lidar", index=True)
    priority: Mapped[str] = mapped_column(String(30), default="medium", index=True)
    stage: Mapped[str] = mapped_column(String(40), default="opportunity", index=True)
    technical_sample_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    expected_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    expected_delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    linked_project_id: Mapped[int | None] = mapped_column(ForeignKey("finance_projects.id", ondelete="SET NULL"), nullable=True, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_handoff_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    events: Mapped[list["BDOpportunityEvent"]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", order_by="BDOpportunityEvent.id"
    )


class BDOpportunityEvent(Base):
    __tablename__ = "ops_v701_bd_opportunity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_bd_opportunities.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(80), index=True)
    from_stage: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(40), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    opportunity: Mapped[BDOpportunity] = relationship(back_populates="events")


class OrthoProjectProfile(Base):
    __tablename__ = "ops_v701_ortho_project_profiles"

    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("ops_v701_bd_opportunities.id", ondelete="SET NULL"), nullable=True, index=True)
    total_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    area_unit: Mapped[str] = mapped_column(String(30), default="ha")
    scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    project_manager_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    final_delivery_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    final_delivery_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    final_delivery_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    members: Mapped[list["OrthoProjectMember"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="OrthoProjectMember.id"
    )
    work_packages: Mapped[list["OrthoWorkPackage"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="OrthoWorkPackage.id"
    )
    deliveries: Mapped[list["OrthoDelivery"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan", order_by="OrthoDelivery.id"
    )


class OrthoProjectMember(Base):
    __tablename__ = "ops_v701_ortho_project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", "member_role", name="uq_ops_v701_project_member_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_project_profiles.project_id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    member_role: Mapped[str] = mapped_column(String(40), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    profile: Mapped[OrthoProjectProfile] = relationship(back_populates="members")


class OrthoWorkPackage(Base):
    __tablename__ = "ops_v701_ortho_work_packages"
    __table_args__ = (
        # Original work packages: one Code per project (unchanged rule). A rework package is a NEW record that carries its
        # source package's Code forward, so a Code only has to be unique within its own rework cycle.
        Index("uq_ops_v701_project_package_code_orig", "project_id", "package_code", unique=True,
              postgresql_where=text("rework_cycle_id IS NULL"), sqlite_where=text("rework_cycle_id IS NULL")),
        Index("uq_ops_v701_project_package_code_rework", "project_id", "package_code", "rework_cycle_id", unique=True,
              postgresql_where=text("rework_cycle_id IS NOT NULL"), sqlite_where=text("rework_cycle_id IS NOT NULL")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_project_profiles.project_id", ondelete="CASCADE"), index=True)
    package_code: Mapped[str] = mapped_column(String(120), index=True)
    package_name: Mapped[str] = mapped_column(String(255))
    area: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    area_unit: Mapped[str] = mapped_column(String(30), default="ha")
    target_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_stage: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    production_state: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    qc_state: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    qa_state: Mapped[str] = mapped_column(String(40), default="not_started", index=True)
    rework_source: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    # Client / change-request rework linkage (V8.1 lifecycle). NULL for original work packages, which a
    # rework cycle never modifies: rework work is always a distinct package linked back to its cycle and,
    # optionally, to the original package it relates to.
    rework_cycle_id: Mapped[int | None] = mapped_column(ForeignKey("project_rework_cycles.id", ondelete="SET NULL"), nullable=True, index=True)
    rework_of_package_id: Mapped[int | None] = mapped_column(ForeignKey("ops_v701_ortho_work_packages.id", ondelete="SET NULL"), nullable=True, index=True)
    team_leader_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    production_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    qc_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    qa_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    production_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    qc_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    qa_submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    delivery_ready_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)

    profile: Mapped[OrthoProjectProfile] = relationship(back_populates="work_packages")
    sessions: Mapped[list["OrthoWorkSession"]] = relationship(
        back_populates="work_package", cascade="all, delete-orphan", order_by="OrthoWorkSession.id"
    )
    reviews: Mapped[list["OrthoReview"]] = relationship(
        back_populates="work_package", cascade="all, delete-orphan", order_by="OrthoReview.id"
    )
    daily_updates: Mapped[list["OrthoDailyUpdate"]] = relationship(
        back_populates="work_package", cascade="all, delete-orphan", order_by="OrthoDailyUpdate.id"
    )


class OrthoWorkSession(Base):
    __tablename__ = "ops_v701_ortho_work_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_work_packages.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    session_type: Mapped[str] = mapped_column(String(30), default="production", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    close_reason: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    work_package: Mapped[OrthoWorkPackage] = relationship(back_populates="sessions")


class OrthoDailyUpdate(Base):
    __tablename__ = "ops_v709_ortho_daily_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_work_packages.id", ondelete="CASCADE"), index=True)
    update_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    work_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    achieved_area: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    progress_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    files_completed: Mapped[int] = mapped_column(Integer, default=0)
    hours_spent: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="on_track", index=True)
    blockers: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    work_package: Mapped[OrthoWorkPackage] = relationship(back_populates="daily_updates")


class OrthoReview(Base):
    __tablename__ = "ops_v701_ortho_reviews"
    __table_args__ = (
        UniqueConstraint("work_package_id", "review_type", "attempt_no", name="uq_ops_v701_review_attempt"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    work_package_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_work_packages.id", ondelete="CASCADE"), index=True)
    review_type: Mapped[str] = mapped_column(String(10), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer)
    reviewer_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    decision: Mapped[str] = mapped_column(String(20), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    work_package: Mapped[OrthoWorkPackage] = relationship(back_populates="reviews")


class OrthoDelivery(Base):
    __tablename__ = "ops_v701_ortho_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("ops_v701_ortho_project_profiles.project_id", ondelete="CASCADE"), index=True)
    delivered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    package_count: Mapped[int] = mapped_column(Integer, default=0)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    profile: Mapped[OrthoProjectProfile] = relationship(back_populates="deliveries")


class ProjectWorkflow(Base):
    """Authoritative BD -> Finance -> Ortho -> Finance closure workflow state.

    This table is additive so legacy opportunity/workstream history can remain in
    the database while the new operational workflow becomes authoritative.
    """

    __tablename__ = "ops_v800_project_workflows"

    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), primary_key=True)
    bd_owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", index=True)
    scope_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    quantity_unit: Mapped[str] = mapped_column(String(30), default="unit")
    priority: Mapped[str] = mapped_column(String(30), default="medium", index=True)
    commercial_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(12), default="INR")
    po_wo_number: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attachment_references: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_count: Mapped[int] = mapped_column(Integer, default=0)
    finance_reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    finance_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    pm_assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    team_assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    operational_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    final_delivery_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    completion_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    finance_closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    finance_closure_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)


class ProjectWorkflowEvent(Base):
    __tablename__ = "ops_v800_project_workflow_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)


class ProjectWorkstream(Base):
    """Technical department workstream under one authoritative Finance Project ID."""

    __tablename__ = "ops_v715_project_workstreams"
    __table_args__ = (
        UniqueConstraint("project_id", "department_code", name="uq_ops_v715_project_department"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("finance_projects.id", ondelete="CASCADE"), index=True)
    department_code: Mapped[str] = mapped_column(String(60), index=True)
    project_manager_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    sequence_order: Mapped[int] = mapped_column(Integer, default=1, index=True)
    status: Mapped[str] = mapped_column(String(40), default="planned", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    updated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now, index=True)
