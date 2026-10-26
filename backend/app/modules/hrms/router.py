"""NakshaTech HRMS: self-service punches and leave, HR review, no cross-module mutations."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User, utc_now
from .models import AttendanceDay, AbsenceExplanation, LeaveRequest, LeaveEntitlement, HRHoliday, HRLeaveNoticeRead, HRLeavePolicy, HRWorkerProfile
from .policy import PAID_KINDS, active_policy, chargeable_days, compute_balance, policy_json

router = APIRouter(prefix="/hrms", tags=["Leave and Attendance"])
TZ = ZoneInfo("Asia/Kolkata")
LEAVE_TYPES = ("casual", "sick", "earned", "paid", "unpaid")


def today_ist() -> date:
    return datetime.now(TZ).date()


def require_hr(auth: CurrentAuth) -> None:
    if auth.effective_role not in ("hr", "admin"):
        raise HTTPException(403, "HR or Admin permission required")


def month_range(month: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(f"{month}-01")
        finish = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    except (ValueError, TypeError):
        raise HTTPException(422, "month must be YYYY-MM") from None
    return start, finish


def punch_json(row: AttendanceDay):
    return {"id": row.id, "work_date": row.work_date.isoformat(),
            "check_in_utc": row.check_in_utc.isoformat() + "Z",
            "check_out_utc": row.check_out_utc.isoformat() + "Z" if row.check_out_utc else None}


def explanation_json(row: AbsenceExplanation):
    return {"id": row.id, "work_date": row.work_date.isoformat(), "reason": row.reason,
            "status": row.status, "hr_note": row.hr_note}


def leave_json(row: LeaveRequest):
    return {"id": row.id, "user_id": row.user_id, "leave_type": row.leave_type,
            "from_date": row.from_date.isoformat(), "to_date": row.to_date.isoformat(),
            "requested_calendar_days": row.requested_calendar_days, "reason": row.reason,
            "status": row.status, "decision_note": row.decision_note}


class ExplanationIn(BaseModel):
    work_date: date
    reason: str = Field(min_length=5, max_length=1500)


class LeaveIn(BaseModel):
    leave_type: str
    from_date: date
    to_date: date
    reason: str = Field(min_length=5, max_length=1500)


class ReviewIn(BaseModel):
    status: str
    note: str = Field(default="", max_length=1000)


class EntitlementIn(BaseModel):
    user_id: int
    year: int = Field(ge=2020, le=2100)
    leave_type: str
    days: int = Field(ge=0, le=366)


class CompanyPolicyIn(BaseModel):
    year: int = Field(ge=2020, le=2100)
    intern_monthly_days: int = Field(default=1, ge=0, le=31)
    probation_first_six_month_days: int = Field(default=5, ge=0, le=31)
    months_seven_to_twelve_extra_days: int = Field(ge=0, le=31)
    full_time_annual_days: int = Field(default=15, ge=0, le=366)
    working_weekdays: list[int] = Field(min_length=1, max_length=7)


class BulkClassificationIn(BaseModel):
    user_ids: list[int] = Field(min_length=1, max_length=500)
    employment_category: str
    joining_date: date | None = None  # When omitted, use each user's verified existing joining date.


class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=180)
    region: str = Field(default="Karnataka", max_length=80)
    category: str = Field(default="state", max_length=40)
    official_source_url: str | None = Field(default=None, max_length=800)
    hr_verified: bool = False


@router.get("/me/attendance")
def my_attendance(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
                  db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    start, finish = month_range(month)
    punches = db.scalars(select(AttendanceDay).where(AttendanceDay.user_id == auth.user.id,
        AttendanceDay.work_date >= start, AttendanceDay.work_date < finish).order_by(AttendanceDay.work_date.desc())).all()
    reasons = db.scalars(select(AbsenceExplanation).where(AbsenceExplanation.user_id == auth.user.id,
        AbsenceExplanation.work_date >= start, AbsenceExplanation.work_date < finish)).all()
    return {"punches": [punch_json(x) for x in punches], "explanations": [explanation_json(x) for x in reasons],
            "timezone": "Asia/Kolkata", "source": "erp_web_manual_check_in_out"}


@router.post("/me/check-in", status_code=201)
def check_in(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    work_date = today_ist()
    current = db.scalar(select(AttendanceDay).where(AttendanceDay.user_id == auth.user.id,
                                                          AttendanceDay.work_date == work_date))
    if current:
        raise HTTPException(409, "Already checked in for today")
    row = AttendanceDay(user_id=auth.user.id, work_date=work_date, check_in_utc=utc_now())
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Already checked in for today") from None
    db.refresh(row)
    return punch_json(row)


@router.post("/me/check-out")
def check_out(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    row = db.scalar(select(AttendanceDay).where(AttendanceDay.user_id == auth.user.id,
        AttendanceDay.work_date == today_ist()).with_for_update())
    if not row:
        raise HTTPException(409, "Check in first")
    if row.check_out_utc:
        raise HTTPException(409, "Already checked out")
    row.check_out_utc = utc_now()
    db.commit()
    return punch_json(row)


@router.post("/me/absence")
def explain_absence(payload: ExplanationIn, db: Session = Depends(get_db),
                    auth: CurrentAuth = Depends(get_current_auth)):
    if not today_ist() - timedelta(days=90) <= payload.work_date <= today_ist():
        raise HTTPException(422, "Explanation date must be within the past 90 days")
    row = db.scalar(select(AbsenceExplanation).where(AbsenceExplanation.user_id == auth.user.id,
        AbsenceExplanation.work_date == payload.work_date))
    if row and row.status != "pending":
        raise HTTPException(409, "This explanation has already been reviewed")
    if row:
        row.reason = payload.reason.strip()
    else:
        row = AbsenceExplanation(user_id=auth.user.id, work_date=payload.work_date,
                                 reason=payload.reason.strip())
        db.add(row)
    db.commit()
    db.refresh(row)
    return explanation_json(row)


@router.get("/me/leave")
def my_leave(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    return [leave_json(x) for x in db.scalars(select(LeaveRequest).where(
        LeaveRequest.user_id == auth.user.id).order_by(LeaveRequest.id.desc())).all()]


@router.post("/me/leave", status_code=201)
def apply_leave(payload: LeaveIn, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    # HR personnel request their own leave by email under NakshaTech policy.
    # Keep ordinary employee applications available; enforce this server-side too.
    if auth.effective_role == "hr":
        raise HTTPException(403, "HR staff request personal leave through their designated email process")
    leave_type = payload.leave_type.strip().lower()
    if leave_type not in LEAVE_TYPES:
        raise HTTPException(422, "Unsupported leave category")
    days = (payload.to_date - payload.from_date).days + 1
    if days < 1 or days > 60:
        raise HTTPException(422, "Select a valid leave period of at most 60 calendar days")
    if payload.from_date < today_ist() - timedelta(days=90):
        raise HTTPException(422, "Historical leave requires HR review")
    if leave_type in PAID_KINDS and payload.from_date.year != payload.to_date.year and active_policy(db, payload.from_date.year):
        raise HTTPException(422, "Submit separate paid-leave applications for each calendar year")
    overlap = db.scalar(select(LeaveRequest.id).where(LeaveRequest.user_id == auth.user.id,
        LeaveRequest.status.in_(["pending", "approved"]),
        LeaveRequest.from_date <= payload.to_date, LeaveRequest.to_date >= payload.from_date).limit(1))
    if overlap:
        raise HTTPException(409, "You already have a pending or approved application in this period")
    row = LeaveRequest(user_id=auth.user.id, leave_type=leave_type, from_date=payload.from_date,
        to_date=payload.to_date, requested_calendar_days=days, reason=payload.reason.strip())
    db.add(row)
    db.commit()
    db.refresh(row)
    return leave_json(row)


@router.post("/me/leave/{leave_id}/cancel")
def cancel_leave(leave_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    row = db.get(LeaveRequest, leave_id)
    if not row or row.user_id != auth.user.id:
        raise HTTPException(404, "Leave application not found")
    if row.status != "pending":
        raise HTTPException(409, "Only pending requests can be withdrawn")
    row.status = "cancelled"
    db.commit()
    return leave_json(row)


@router.get("/me/balance")
def my_balance(year: int = Query(..., ge=2020, le=2100), db: Session = Depends(get_db),
               auth: CurrentAuth = Depends(get_current_auth)):
    return compute_balance(db, auth.user, year, today_ist())


@router.get("/hr/policy")
def get_company_policy(year: int = Query(..., ge=2020, le=2100),
                       db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    row = active_policy(db, year)
    return {"configured": bool(row), "inherited_from_year": row.year if row and row.year != year else None,
            "policy": policy_json(row) if row else None}


@router.put("/hr/policy")
def save_company_policy(payload: CompanyPolicyIn, db: Session = Depends(get_db),
                        auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    weekdays = payload.working_weekdays
    if len(set(weekdays)) != len(weekdays) or any(n not in range(7) for n in weekdays):
        raise HTTPException(422, "Select distinct weekdays between Monday (0) and Sunday (6)")
    row = db.get(HRLeavePolicy, payload.year)
    if row is None:
        row = HRLeavePolicy(year=payload.year)
        db.add(row)
    row.intern_monthly_days = payload.intern_monthly_days
    row.probation_first_six_month_days = payload.probation_first_six_month_days
    row.months_seven_to_twelve_extra_days = payload.months_seven_to_twelve_extra_days
    row.full_time_annual_days = payload.full_time_annual_days
    row.working_weekdays = ",".join(map(str, sorted(weekdays)))
    row.no_carry_forward = True
    row.updated_by = auth.user.id
    db.commit()
    return {"saved": True, "policy": policy_json(row)}


@router.get("/hr/employees/classifications")
def list_classifications(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    profiles = {p.user_id: p for p in db.scalars(select(HRWorkerProfile)).all()}
    employees = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    today = today_ist()
    result = []
    for u in employees:
        p = profiles.get(u.id)
        result.append({"user_id": u.id, "employee_name": u.full_name, "department": u.department,
                       "role": u.role, "joining_date": (p.joining_date if p else u.joining_date).isoformat() if (p or u.joining_date) else None,
                       "employment_category": p.employment_category if p else None,
                       "assigned": bool(p)})
    return result


@router.put("/hr/employees/classifications/bulk")
def bulk_classify(payload: BulkClassificationIn, db: Session = Depends(get_db),
                  auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    if payload.employment_category not in ("intern", "staff"):
        raise HTTPException(422, "Employment category must be intern or staff")
    if len(set(payload.user_ids)) != len(payload.user_ids):
        raise HTTPException(422, "Duplicate employee IDs")
    users = db.scalars(select(User).where(User.id.in_(payload.user_ids))).all()
    if len(users) != len(payload.user_ids):
        raise HTTPException(422, "One or more selected users do not exist")
    if any(user.role == "hr" for user in users):
        raise HTTPException(422, "HR personal leave is managed by email, not the employee application policy")
    for u in users:
        joining = payload.joining_date or u.joining_date
        if not joining or joining > today_ist():
            raise HTTPException(422, f"A verified past joining date is required for user {u.id}")
    for u in users:
        profile = db.get(HRWorkerProfile, u.id)
        if profile is None:
            profile = HRWorkerProfile(user_id=u.id)
            db.add(profile)
        profile.employment_category = payload.employment_category
        profile.joining_date = payload.joining_date or u.joining_date
        profile.assigned_by = auth.user.id
    db.commit()
    return {"saved": len(users)}


@router.get("/hr/employees/{user_id}/balance")
def employee_balance(user_id: int, year: int = Query(..., ge=2020, le=2100),
                     db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "Employee not found")
    return compute_balance(db, user, year, today_ist())


@router.get("/holidays")
def holidays(year: int = Query(..., ge=2020, le=2100), db: Session = Depends(get_db),
             auth: CurrentAuth = Depends(get_current_auth)):
    rows = db.scalars(select(HRHoliday).where(HRHoliday.holiday_date >= date(year, 1, 1),
        HRHoliday.holiday_date <= date(year, 12, 31)).order_by(HRHoliday.holiday_date)).all()
    return [{"date": x.holiday_date.isoformat(), "name": x.name, "region": x.region,
             "category": x.category, "official_source_url": x.official_source_url,
             "hr_verified": x.hr_verified} for x in rows]


@router.get("/hr/leave-notifications")
def hr_leave_notifications(db: Session = Depends(get_db),
                           auth: CurrentAuth = Depends(get_current_auth)):
    """Pending employee requests, with durable per-HR unread state (pollable)."""
    require_hr(auth)
    pending = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "pending")
        .order_by(LeaveRequest.created_at.desc(), LeaveRequest.id.desc()).limit(100)).all()
    read_ids = set(db.scalars(select(HRLeaveNoticeRead.leave_request_id).where(
        HRLeaveNoticeRead.hr_user_id == auth.user.id,
        HRLeaveNoticeRead.leave_request_id.in_([row.id for row in pending])
    )).all()) if pending else set()
    people = {row.user_id: db.get(User, row.user_id) for row in pending}
    notifications = [{
        "leave_id": row.id, "user_id": row.user_id,
        "employee_name": (people[row.user_id].full_name if people[row.user_id] else "Employee"),
        "leave_type": row.leave_type, "from_date": row.from_date.isoformat(),
        "to_date": row.to_date.isoformat(), "created_at": row.created_at.isoformat(),
        "is_read": row.id in read_ids,
    } for row in pending]
    return {"unread_count": sum(not n["is_read"] for n in notifications),
            "pending_count": len(notifications), "notifications": notifications}


@router.post("/hr/leave-notifications/{leave_id}/read")
def mark_hr_leave_notification_read(leave_id: int, db: Session = Depends(get_db),
                                    auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    row = db.get(LeaveRequest, leave_id)
    if not row:
        raise HTTPException(404, "Leave application not found")
    existing = db.scalar(select(HRLeaveNoticeRead).where(
        HRLeaveNoticeRead.hr_user_id == auth.user.id,
        HRLeaveNoticeRead.leave_request_id == leave_id))
    if existing is None:
        db.add(HRLeaveNoticeRead(hr_user_id=auth.user.id, leave_request_id=leave_id))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # another tab marked the same notice read concurrently
    return {"read": True}


@router.get("/hr/employees/{user_id}/leave-history")
def hr_employee_leave_history(user_id: int, year: int | None = Query(default=None, ge=2020, le=2100),
                              db: Session = Depends(get_db),
                              auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    employee = db.get(User, user_id)
    if not employee:
        raise HTTPException(404, "Employee not found")
    conditions = [LeaveRequest.user_id == user_id]
    if year is not None:
        conditions += [LeaveRequest.from_date <= date(year, 12, 31),
                       LeaveRequest.to_date >= date(year, 1, 1)]
    history = db.scalars(select(LeaveRequest).where(*conditions).order_by(
        LeaveRequest.from_date.desc(), LeaveRequest.id.desc())).all()
    approved = [row for row in history if row.status == "approved"]
    pending = [row for row in history if row.status == "pending"]
    return {"employee": {"user_id": employee.id, "name": employee.full_name,
                        "employee_id": employee.employee_id, "department": employee.department,
                        "role": employee.role},
            "year": year, "requests": [leave_json(row) for row in history],
            "summary": {"total_requests": len(history), "approved_requests": len(approved),
                        "approved_calendar_days": sum(row.requested_calendar_days for row in approved),
                        "pending_requests": len(pending),
                        "pending_calendar_days": sum(row.requested_calendar_days for row in pending),
                        "rejected_requests": sum(row.status == "rejected" for row in history),
                        "cancelled_requests": sum(row.status == "cancelled" for row in history)},
            "notice": "Calendar days are provisional and are not payroll deductions."}


@router.get("/hr/overview")
def hr_overview(day: date | None = None, db: Session = Depends(get_db),
                auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    work_date = day or today_ist()
    if abs((today_ist() - work_date).days) > 365:
        raise HTTPException(422, "Date out of supported reporting range")
    people = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).all()
    punches = {x.user_id: x for x in db.scalars(select(AttendanceDay).where(AttendanceDay.work_date == work_date)).all()}
    reasons = {x.user_id: x for x in db.scalars(select(AbsenceExplanation).where(
        AbsenceExplanation.work_date == work_date)).all()}
    leaves = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "approved",
        LeaveRequest.from_date <= work_date, LeaveRequest.to_date >= work_date)).all()
    away = {x.user_id: x.leave_type for x in leaves}
    rows = []
    for user in people:
        punch = punches.get(user.id)
        reason = reasons.get(user.id)
        status = ("on_approved_leave" if user.id in away else
                  "checked_out" if punch and punch.check_out_utc else
                  "checked_in" if punch else "no_punch_recorded")
        rows.append({"user_id": user.id, "name": user.full_name, "employee_id": user.employee_id,
                     "department": user.department, "role": user.role, "status": status,
                     "check_in_utc": punch.check_in_utc.isoformat() + "Z" if punch else None,
                     "check_out_utc": punch.check_out_utc.isoformat() + "Z" if punch and punch.check_out_utc else None,
                     "absence_reason": reason.reason if reason else None,
                     "explanation_status": reason.status if reason else None})
    pending_leaves = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "pending").order_by(
        LeaveRequest.created_at.desc()).limit(100)).all()
    pending_explanations = db.scalars(select(AbsenceExplanation).where(
        AbsenceExplanation.status == "pending").order_by(AbsenceExplanation.created_at.desc()).limit(100)).all()
    return {"date": work_date.isoformat(), "employees": rows,
        "pending_leaves": [dict(leave_json(x), employee_name=next(
            (u.full_name for u in people if u.id == x.user_id), str(x.user_id))) for x in pending_leaves],
        "pending_explanations": [dict(explanation_json(x), user_id=x.user_id,
            employee_name=next((u.full_name for u in people if u.id == x.user_id), str(x.user_id)))
            for x in pending_explanations], "notice": "No punch is not an automatic absence finding."}


@router.post("/hr/leave/{leave_id}/decision")
def decide_leave(leave_id: int, payload: ReviewIn, db: Session = Depends(get_db),
                 auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(422, "Decision must be approved or rejected")
    row = db.get(LeaveRequest, leave_id)
    if not row:
        raise HTTPException(404, "Leave application not found")
    if row.status != "pending":
        raise HTTPException(409, "Only pending applications can be decided")
    if row.user_id == auth.user.id:
        raise HTTPException(403, "HR cannot approve their own leave")
    # Enforce paid allowance only when a company-wide HR policy is published.
    # Existing leave workflows without a published policy remain unchanged.
    if payload.status == "approved" and row.leave_type in PAID_KINDS:
        policy = active_policy(db, row.to_date.year)
        if policy:
            if row.from_date.year != row.to_date.year:
                raise HTTPException(409, "Split cross-year paid leave into separate requests so annual limits are enforced")
            employee = db.get(User, row.user_id)
            balance = compute_balance(db, employee, row.to_date.year, max(today_ist(), row.to_date))
            if not balance["configured"]:
                raise HTTPException(409, "HR must assign the employment category and joining date before approving paid leave")
            paid = balance["balances"][0]
            profile = db.get(HRWorkerProfile, row.user_id)
            start = date.fromisoformat(balance["period_start"])
            end = date.fromisoformat(balance["period_end"])
            holidays = set(db.scalars(select(HRHoliday.holiday_date).where(
                HRHoliday.hr_verified.is_(True), HRHoliday.holiday_date >= start,
                HRHoliday.holiday_date <= end)).all())
            weekdays = set(int(n) for n in policy.working_weekdays.split(","))
            projected = chargeable_days(max(start, row.from_date), min(end, row.to_date), weekdays, holidays)
            if paid["approved_chargeable_days"] + projected > paid["entitled"]:
                raise HTTPException(409, "Paid leave exceeds the company policy balance; decline or review the request")
    row.status = payload.status
    row.reviewer_id = auth.user.id
    row.decision_note = payload.note.strip() or None
    row.decided_at = utc_now()
    db.commit()
    return leave_json(row)


@router.post("/hr/absence/{explanation_id}/decision")
def decide_absence(explanation_id: int, payload: ReviewIn, db: Session = Depends(get_db),
                   auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    if payload.status not in ("approved", "rejected"):
        raise HTTPException(422, "Decision must be approved or rejected")
    row = db.get(AbsenceExplanation, explanation_id)
    if not row:
        raise HTTPException(404, "Explanation not found")
    if row.status != "pending":
        raise HTTPException(409, "Already reviewed")
    if row.user_id == auth.user.id:
        raise HTTPException(403, "HR cannot review their own explanation")
    row.status = payload.status
    row.reviewed_by = auth.user.id
    row.hr_note = payload.note.strip() or None
    row.reviewed_at = utc_now()
    db.commit()
    return explanation_json(row)


@router.put("/hr/entitlement")
def set_entitlement(payload: EntitlementIn, db: Session = Depends(get_db),
                    auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    if payload.leave_type not in LEAVE_TYPES or not db.get(User, payload.user_id):
        raise HTTPException(422, "Unknown employee or leave type")
    row = db.scalar(select(LeaveEntitlement).where(LeaveEntitlement.user_id == payload.user_id,
        LeaveEntitlement.year == payload.year, LeaveEntitlement.leave_type == payload.leave_type))
    if row:
        row.days = payload.days
    else:
        db.add(LeaveEntitlement(user_id=payload.user_id, year=payload.year,
                                leave_type=payload.leave_type, days=payload.days))
    db.commit()
    return {"saved": True}


@router.post("/hr/holidays")
def add_holiday(payload: HolidayIn, db: Session = Depends(get_db),
                auth: CurrentAuth = Depends(get_current_auth)):
    require_hr(auth)
    if payload.official_source_url and not payload.official_source_url.startswith("https://"):
        raise HTTPException(422, "Official source must be an HTTPS URL")
    if payload.hr_verified and payload.category != "company" and not payload.official_source_url:
        raise HTTPException(422, "Verify a government holiday against its official notification URL")
    row = db.scalar(select(HRHoliday).where(HRHoliday.holiday_date == payload.holiday_date,
        HRHoliday.region == payload.region))
    if not row:
        row = HRHoliday(holiday_date=payload.holiday_date, region=payload.region,
                        name=payload.name, category=payload.category, created_by=auth.user.id)
        db.add(row)
    row.name = payload.name
    row.category = payload.category
    row.official_source_url = payload.official_source_url
    row.hr_verified = payload.hr_verified
    db.commit()
    return {"saved": True}
