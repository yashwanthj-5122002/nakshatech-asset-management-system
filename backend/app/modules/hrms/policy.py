"""Company-wide HR leave allowances and year-safe balance calculations.

No payroll posting, changes to User rows, or alteration of legacy invoice logic.
Only HR-verified category and joining date are used for entitlement decisions.
"""
from calendar import monthrange
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from .models import HRHoliday, HRLeavePolicy, HRWorkerProfile, LeaveRequest, LeaveEntitlement

PAID_KINDS = {"paid", "casual", "sick", "earned"}


def leave_calendar_days(row: LeaveRequest) -> float:
    return 0.5 if row.duration == "half_day" else float(row.requested_calendar_days)


def leave_chargeable_days(row: LeaveRequest, start: date, end: date,
                          weekdays: set[int], holidays: set[date]) -> float:
    if row.duration == "half_day":
        return 0.5 if start <= row.from_date <= end and row.from_date.weekday() in weekdays and row.from_date not in holidays else 0.0
    return float(chargeable_days(start, end, weekdays, holidays))


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def policy_json(row: HRLeavePolicy):
    return {"year": row.year, "intern_monthly_days": row.intern_monthly_days,
            "probation_first_six_month_days": row.probation_first_six_month_days,
            "months_seven_to_twelve_extra_days": row.months_seven_to_twelve_extra_days,
            "full_time_annual_days": row.full_time_annual_days,
            "working_weekdays": [int(n) for n in row.working_weekdays.split(",")],
            "no_carry_forward": row.no_carry_forward}


def stage_on(profile: HRWorkerProfile, as_of: date) -> str:
    if as_of < profile.joining_date:
        return "not_joined"
    if profile.employment_category == "intern":
        return "intern"
    if as_of < add_months(profile.joining_date, 6):
        return "probation_first_six_months"
    if as_of < add_months(profile.joining_date, 12):
        return "months_seven_to_twelve"
    return "full_time"


def paid_entitlement(policy: HRLeavePolicy, profile: HRWorkerProfile, as_of: date) -> tuple[int, str, date, date]:
    """Returns credit, employment stage, and allowance period (calendar year or first service year)."""
    stage = stage_on(profile, as_of)
    jan1, dec31 = date(as_of.year, 1, 1), date(as_of.year, 12, 31)
    if stage == "not_joined":
        return 0, stage, jan1, dec31
    if stage == "intern":
        n, total = 1, 0
        while n <= 1200:
            anniversary = add_months(profile.joining_date, n)
            if anniversary > as_of:
                break
            if jan1 <= anniversary <= dec31:
                total += policy.intern_monthly_days
            n += 1
        return total, stage, jan1, dec31
    if stage == "full_time":
        return policy.full_time_annual_days, stage, jan1, dec31
    first_year_end = add_months(profile.joining_date, 12) - timedelta(days=1)
    entitlement = policy.probation_first_six_month_days
    if stage == "months_seven_to_twelve":
        entitlement += policy.months_seven_to_twelve_extra_days
    return entitlement, stage, profile.joining_date, first_year_end


def chargeable_days(start: date, end: date, working_weekdays: set[int], holidays: set[date]) -> int:
    if end < start:
        return 0
    count, day = 0, start
    while day <= end:
        if day.weekday() in working_weekdays and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count


def active_policy(db: Session, year: int) -> HRLeavePolicy | None:
    # A policy stays effective in future years until HR publishes a newer one.
    # Leave days themselves are never carried across full-time calendar years.
    return db.scalars(select(HRLeavePolicy).where(HRLeavePolicy.year <= year).order_by(
        HRLeavePolicy.year.desc()).limit(1)).first()


def compute_balance(db: Session, user: User, year: int, as_of: date):
    policy = active_policy(db, year)
    profile = db.get(HRWorkerProfile, user.id)
    if not policy:
        # Backwards-compatible read of Stage 1 entitlements until HR publishes a company-wide policy.
        # No legacy balances are deleted or rewritten.
        allowances = {x.leave_type: x.days for x in db.scalars(select(LeaveEntitlement).where(
            LeaveEntitlement.user_id == user.id, LeaveEntitlement.year == year)).all()}
        leave_rows = db.scalars(select(LeaveRequest).where(
            LeaveRequest.user_id == user.id, LeaveRequest.status.in_(("approved", "pending")),
            LeaveRequest.from_date >= date(year, 1, 1),
            LeaveRequest.to_date <= date(year, 12, 31))).all()
        balances = []
        for kind in ("casual", "sick", "earned", "unpaid"):
            approved = sum(leave_calendar_days(x) for x in leave_rows if x.leave_type == kind and x.status == "approved")
            pending = sum(leave_calendar_days(x) for x in leave_rows if x.leave_type == kind and x.status == "pending")
            granted = allowances.get(kind)
            balances.append({"leave_type": kind, "entitled": granted,
                             "approved_calendar_days": approved, "pending_calendar_days": pending,
                             "remaining_provisional": max(0, granted - approved) if granted is not None else None})
        return {"configured": False, "year": year, "employment_stage": None,
                "notice": "Legacy provisional leave balances. HR must publish the company policy to activate automatic entitlements.",
                "balances": balances}
    if not profile:
        return {"configured": False, "year": year, "employment_stage": None,
                "notice": "HR must verify the employee category and joining date to calculate the company policy.",
                "balances": [{"leave_type": "paid", "entitled": None, "approved_calendar_days": 0,
                              "pending_calendar_days": 0, "remaining_provisional": None}]}
    # Never credit future time merely because a future year was selected.
    if as_of.year > year:
        as_of = date(year, 12, 31)
    elif as_of.year < year:
        as_of = date(year, 1, 1) - timedelta(days=1)
    if as_of.year < year:
        credit, stage, period_start, period_end = 0, "not_yet_accrued", date(year, 1, 1), date(year, 12, 31)
    else:
        credit, stage, period_start, period_end = paid_entitlement(policy, profile, as_of)
    weekdays = set(int(n) for n in policy.working_weekdays.split(","))
    holiday_rows = db.scalars(select(HRHoliday.holiday_date).where(
        HRHoliday.hr_verified.is_(True), HRHoliday.holiday_date >= period_start,
        HRHoliday.holiday_date <= period_end)).all()
    holidays = set(holiday_rows)
    requests = db.scalars(select(LeaveRequest).where(
        LeaveRequest.user_id == user.id, LeaveRequest.status.in_(("approved", "pending")),
        LeaveRequest.from_date <= period_end, LeaveRequest.to_date >= period_start)).all()
    approved, pending = 0, 0
    approved_calendar, pending_calendar = 0, 0
    for row in requests:
        if row.leave_type not in PAID_KINDS:
            continue
        start = max(period_start, row.from_date)
        end = min(period_end, row.to_date)
        count = leave_chargeable_days(row, start, end, weekdays, holidays)
        raw_days = 0.5 if row.duration == "half_day" else (end - start).days + 1
        if row.status == "approved":
            approved += count
            approved_calendar += raw_days
        else:
            pending += count
            pending_calendar += raw_days
    balance = {"leave_type": "paid", "entitled": credit,
               "approved_calendar_days": approved_calendar, "pending_calendar_days": pending_calendar,
               "approved_chargeable_days": approved, "pending_chargeable_days": pending,
               "remaining_provisional": max(0, credit - approved)}
    return {"configured": True, "year": year, "employment_stage": stage,
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "employment_category": profile.employment_category, "policy_effective_year": policy.year,
            "balances": [balance], "notice": "HR policy calculation: working weekdays and HR-verified holidays; paid leave requests share one pool. No automatic payroll posting. Verify statutory entitlements before production use."}
