"""Isolated HRMS records. Does not change User or EmployeeMaster schemas."""
from datetime import date, datetime
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base
from app.models.entities import utc_now


class AttendanceDay(Base):
    __tablename__ = "hrms_attendance_days"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_hrms_attendance_day"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    check_in_utc: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    check_out_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class AbsenceExplanation(Base):
    __tablename__ = "hrms_absence_explanations"
    __table_args__ = (UniqueConstraint("user_id", "work_date", name="uq_hrms_absence_explanation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="pending", index=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    hr_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LeaveRequest(Base):
    __tablename__ = "hrms_leave_requests"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    leave_type: Mapped[str] = mapped_column(String(40))
    from_date: Mapped[date] = mapped_column(Date, index=True)
    to_date: Mapped[date] = mapped_column(Date, index=True)
    # Provisional calendar-day count, pending HR policy confirmation.
    requested_calendar_days: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="pending", index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LeaveEntitlement(Base):
    __tablename__ = "hrms_leave_entitlements"
    __table_args__ = (UniqueConstraint("user_id", "year", "leave_type", name="uq_hrms_leave_entitlement"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    leave_type: Mapped[str] = mapped_column(String(40))
    days: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class HRHoliday(Base):
    __tablename__ = "hrms_holidays"
    __table_args__ = (UniqueConstraint("holiday_date", "region", name="uq_hrms_holiday_region"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    holiday_date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(180))
    region: Mapped[str] = mapped_column(String(80), default="Karnataka")
    category: Mapped[str] = mapped_column(String(40), default="state")
    official_source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hr_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)


class HRLeaveNoticeRead(Base):
    """Per-HR read state for a pending employee leave request; no shared notifications schema changes."""
    __tablename__ = "hrms_leave_notice_reads"
    __table_args__ = (UniqueConstraint("hr_user_id", "leave_request_id", name="uq_hrms_leave_notice_read"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hr_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    leave_request_id: Mapped[int] = mapped_column(ForeignKey("hrms_leave_requests.id", ondelete="CASCADE"), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class HRLeavePolicy(Base):
    """Year-specific company leave policy; no changes to existing User or leave tables."""
    __tablename__ = "hrms_company_leave_policies"
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    intern_monthly_days: Mapped[int] = mapped_column(Integer, default=1)
    probation_first_six_month_days: Mapped[int] = mapped_column(Integer, default=5)
    months_seven_to_twelve_extra_days: Mapped[int] = mapped_column(Integer)
    full_time_annual_days: Mapped[int] = mapped_column(Integer, default=15)
    working_weekdays: Mapped[str] = mapped_column(String(20), default="0,1,2,3,4")
    no_carry_forward: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class HRWorkerProfile(Base):
    """HR-verified worker category and starting date. Does not overwrite Employee Master."""
    __tablename__ = "hrms_worker_profiles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    employment_category: Mapped[str] = mapped_column(String(16))  # intern or staff
    joining_date: Mapped[date] = mapped_column(Date)
    assigned_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
