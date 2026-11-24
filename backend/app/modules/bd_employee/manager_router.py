"""Read-only BD Manager 'My Team' reporting for BD01-BD05 test employees.

Only Part 1 BD employee prospects and contact activities are queried. Finance,
Management-origin clients/projects, and commercial revenue are deliberately
excluded because official lead-to-project attribution is not yet available.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User
from app.modules.bd_employee.models import BdEmployeeContactActivity as Activity
from app.modules.bd_employee.models import BdEmployeeProspect as Prospect

router = APIRouter(prefix="/bd-employee/manager", tags=["BD Manager My Team"])

TEST_EMPLOYEE_IDS = frozenset(f"BD{i:02d}" for i in range(1, 6))
RESPONSE_OUTCOMES = ("replied", "interested", "not_interested", "callback", "enquiry", "won")
CLOSED_STATUSES = ("not_interested", "won")  # Closed prospect outcomes; not verified project closures
INDIA = ZoneInfo("Asia/Kolkata")


def _only_bd_manager(auth: CurrentAuth = Depends(get_current_auth)) -> int:
    # Never expand BD Manager access by client-side routing, inherited admin roles,
    # or a stale token after an account's real DB role changes.
    if auth.user.role != "bd" or auth.effective_role != "bd":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="BD Manager access required")
    return auth.user.id


def _period(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="End date must be on or after start date")
    if (end_date - start_date).days > 1096:
        raise HTTPException(status_code=422, detail="Maximum reporting range is three years")
    start = datetime.combine(start_date, time.min, tzinfo=INDIA).astimezone(timezone.utc).replace(tzinfo=None)
    stop = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=INDIA).astimezone(timezone.utc).replace(tzinfo=None)
    return start, stop


def _employees(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(
        User.role == "bd_employee",
        func.upper(User.employee_id).in_(TEST_EMPLOYEE_IDS),
    ).order_by(User.employee_id)).all())


def _match_employee(employees: list[User], employee_id: str) -> User:
    code = employee_id.strip().upper()
    row = next((e for e in employees if (e.employee_id or "").upper() == code), None)
    if not row:
        raise HTTPException(status_code=404, detail="BD test employee not found")
    return row


def _group_counts(db: Session, statement) -> dict[int, int]:
    return {int(owner_id): int(count) for owner_id, count in db.execute(statement).all()}


def _team_summary(db: Session, *, employees: list[User], start_date: date, end_date: date) -> dict:
    start, stop = _period(start_date, end_date)
    ids = [employee.id for employee in employees]
    zero = {"prospects": 0, "clients": 0, "closed": 0, "contacted": 0,
            "responded": 0, "activities": 0, "enquiries": 0,
            "pending_followups": 0, "overdue_followups": 0}
    results = {uid: dict(zero) for uid in ids}
    if ids:
        p = Prospect
        a = Activity
        queries = {
            "prospects": select(p.owner_user_id, func.count(p.id)).where(
                p.owner_user_id.in_(ids), p.created_at >= start, p.created_at < stop
            ).group_by(p.owner_user_id),
            # Unique prospect company names (case/outer-space insensitive) among leads
            # ADDED during the selected reporting period. Not Finance client records.
            "clients": select(p.owner_user_id, func.count(func.distinct(func.lower(func.trim(p.company_name))))).where(
                p.owner_user_id.in_(ids), p.created_at >= start, p.created_at < stop
            ).group_by(p.owner_user_id),
            # Current CLOSED state of prospects added in this period; historical close
            # timestamps are not stored in Part 1, so do not imply close-date metrics.
            "closed": select(p.owner_user_id, func.count(p.id)).where(
                p.owner_user_id.in_(ids), p.created_at >= start, p.created_at < stop,
                p.status.in_(CLOSED_STATUSES)
            ).group_by(p.owner_user_id),
            "contacted": select(a.owner_user_id, func.count(func.distinct(a.prospect_id))).where(
                a.owner_user_id.in_(ids), a.contacted_at >= start, a.contacted_at < stop
            ).group_by(a.owner_user_id),
            "responded": select(a.owner_user_id, func.count(func.distinct(a.prospect_id))).where(
                a.owner_user_id.in_(ids), a.contacted_at >= start, a.contacted_at < stop,
                a.outcome.in_(RESPONSE_OUTCOMES)
            ).group_by(a.owner_user_id),
            "activities": select(a.owner_user_id, func.count(a.id)).where(
                a.owner_user_id.in_(ids), a.contacted_at >= start, a.contacted_at < stop
            ).group_by(a.owner_user_id),
            "enquiries": select(a.owner_user_id, func.count(func.distinct(a.prospect_id))).where(
                a.owner_user_id.in_(ids), a.contacted_at >= start, a.contacted_at < stop,
                a.outcome == "enquiry"
            ).group_by(a.owner_user_id),
            "pending_followups": select(p.owner_user_id, func.count(p.id)).where(
                p.owner_user_id.in_(ids), p.next_followup_date >= start_date,
                p.next_followup_date <= end_date, p.status.notin_(CLOSED_STATUSES)
            ).group_by(p.owner_user_id),
            "overdue_followups": select(p.owner_user_id, func.count(p.id)).where(
                p.owner_user_id.in_(ids), p.next_followup_date >= start_date,
                p.next_followup_date <= end_date,
                p.next_followup_date < datetime.now(INDIA).date(),
                p.status.notin_(CLOSED_STATUSES)
            ).group_by(p.owner_user_id),
        }
        for metric, stmt in queries.items():
            for uid, count in _group_counts(db, stmt).items():
                results[uid][metric] = count
    rows = []
    for employee in employees:
        rows.append({
            "user_id": employee.id, "employee_id": employee.employee_id,
            "name": employee.full_name, "email": employee.email,
            "active": bool(employee.is_active),
            **results[employee.id],
            # No official project linkage exists in the Part 1 schema.
            "confirmed_projects": None, "confirmed_sales_value": None,
        })
    summary = {key: sum(row[key] for row in rows) for key in zero}
    if ids:
        # When viewing All Employees, count one company once even if several
        # employees saved it as a prospect. Individual rows remain per-owner.
        summary["clients"] = int(db.scalar(select(func.count(func.distinct(func.lower(func.trim(Prospect.company_name))))).where(
            Prospect.owner_user_id.in_(ids), Prospect.created_at >= start, Prospect.created_at < stop
        )) or 0)
    summary["confirmed_projects"] = None
    summary["confirmed_sales_value"] = None
    return {
        "start_date": start_date, "end_date": end_date,
        "employee_count": len(employees), "employees": rows, "summary": summary,
        "official_attribution": "not_linked",
    }


@router.get("/team")
def my_team(
    start_date: date = Query(...), end_date: date = Query(...),
    employee_id: str | None = Query(default=None, max_length=80),
    db: Session = Depends(get_db),
    _manager_id: int = Depends(_only_bd_manager),
) -> dict:
    _period(start_date, end_date)
    employees = _employees(db)
    if employee_id:
        employees = [_match_employee(employees, employee_id)]
    return _team_summary(db, employees=employees, start_date=start_date, end_date=end_date)


@router.get("/team/{employee_id}/details")
def my_team_employee_details(
    employee_id: str, start_date: date = Query(...), end_date: date = Query(...),
    prospects_offset: int = Query(default=0, ge=0, le=100000),
    activities_offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    _manager_id: int = Depends(_only_bd_manager),
) -> dict:
    start, stop = _period(start_date, end_date)
    employee = _match_employee(_employees(db), employee_id)
    p = Prospect
    a = Activity
    prospects_filter = (
        p.owner_user_id == employee.id, p.created_at >= start, p.created_at < stop,
    )
    activities_filter = (
        a.owner_user_id == employee.id, a.contacted_at >= start, a.contacted_at < stop,
    )
    prospects_total = int(db.scalar(select(func.count(p.id)).where(*prospects_filter)) or 0)
    activities_total = int(db.scalar(select(func.count(a.id)).where(*activities_filter)) or 0)
    prospects = db.scalars(select(p).where(*prospects_filter)
        .order_by(p.created_at.desc(), p.id.desc())
        .offset(prospects_offset).limit(limit)).all()
    # Joining on BOTH the prospect id and its owner avoids cross-employee data leakage
    # even if a broken activity foreign key were ever inserted.
    activities = db.execute(select(a, p.company_name).join(
        p, (p.id == a.prospect_id) & (p.owner_user_id == a.owner_user_id)
    ).where(*activities_filter).order_by(a.contacted_at.desc(), a.id.desc())
      .offset(activities_offset).limit(limit)).all()
    return {
        "employee": {"id": employee.employee_id, "name": employee.full_name, "email": employee.email},
        "period": {"start_date": start_date, "end_date": end_date},
        "prospects": {"total": prospects_total, "offset": prospects_offset, "items": [{
            "id": item.id, "company_name": item.company_name, "source": item.source,
            "contact_person": item.contact_person, "contact_email": item.contact_email,
            "service_interest": item.service_interest, "status": item.status,
            "next_followup_date": item.next_followup_date, "created_at": item.created_at,
        } for item in prospects]},
        "activities": {"total": activities_total, "offset": activities_offset, "items": [{
            "id": event.id, "prospect_id": event.prospect_id, "company_name": company_name,
            "channel": event.channel, "outcome": event.outcome,
            "remarks": event.remarks, "contacted_at": event.contacted_at,
        } for event, company_name in activities]},
    }
