"""Read-only BD Manager 'My Team' reporting for BD01-BD05 test employees.

All prospects remain leads even after conversion. Registered clients and confirmed
project values are attributed through persisted BD ownership / handoff links only.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User
from app.modules.bd_employee.models import BdEmployeeContactActivity as Activity
from app.modules.bd_employee.models import BdEmployeeProspect as Prospect
from app.modules.bd_employee.direct_router import _visible_employee_project_query
from app.modules.bd_employee.handoff_models import BdClientHandoff, BdEmployeeProjectLink
from app.modules.commercial.models import ProjectCommercialEstimateRevision
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.sales_revenue_service import _baseline_revision, _baseline_sales_inr
from app.modules.finance.visibility import hidden_client_ids
from app.modules.operations.models import ProjectWorkflow

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


def _registered_client_ids(db: Session, *, employee_id: int, start: datetime, stop: datetime, hidden: set[int]) -> set[int]:
    """Registered BD clients created directly or by an approved manager handoff.

    The client's actual registration date drives the period, not prospect status,
    company-name matching, or the time an existing client was linked to a lead.
    Inactive historical registrations still count; centrally hidden clients do not.
    """
    c = FinanceClient
    base = (c.source_team == "bd_team", c.created_at >= start, c.created_at < stop)
    direct = set(db.scalars(select(c.id).where(*base, c.created_by_id == employee_id)).all())
    handed_off = set(db.scalars(select(c.id).join(
        BdClientHandoff, BdClientHandoff.registered_client_id == c.id,
    ).where(*base, BdClientHandoff.employee_user_id == employee_id,
            BdClientHandoff.status == "approved")).all())
    return (direct | handed_off) - hidden


def _confirmed_project_amount(revisions: list[ProjectCommercialEstimateRevision], workflow: ProjectWorkflow) -> Decimal | None:
    """Use a frozen commercial baseline, never a draft/lead or guessed FX rate.

    Finance uses the same baseline valuation helper for its sales reporting. A
    submitted BD project has a finalized baseline; if one is missing or the INR
    conversion is unavailable, return None instead of displaying a false zero.
    """
    baseline = _baseline_revision(revisions)
    if baseline is None or not baseline.is_baseline:
        return None
    currency = (baseline.currency_code or workflow.currency or "INR").upper()
    if currency != "INR" and baseline.gross_inr is None and baseline.estimated_inr is None:
        return None
    value = _baseline_sales_inr(baseline, workflow)
    return value if value >= 0 else None


def _employee_sales(db: Session, *, employees: list[User], start: datetime, stop: datetime) -> dict[int, dict]:
    """Attribute each eligible BD-origin project to at most one BD employee.

    Reuse the employee project visibility boundary (incl. centrally hidden
    projects). Priority: approved explicit project link, direct creator/BD owner,
    then manager-created project on the employee's registered client.
    """
    result = {e.id: {"confirmed_projects": 0, "confirmed_sales_value": 0.0} for e in employees}
    if not employees:
        return result

    candidates: dict[int, list[tuple[int, int]]] = defaultdict(list)
    projects: dict[int, FinanceProject] = {}
    workflows: dict[int, ProjectWorkflow] = {}
    for employee in employees:
        # The same query already guards BD employee financial/project access.
        rows = db.scalars(_visible_employee_project_query(db, employee)).unique().all()
        for project in rows:
            projects[project.id] = project
            candidates[project.id].append((employee.id, 2))  # least-specific ownership
    if not projects:
        return result

    project_ids = list(projects)
    workflows = {w.project_id: w for w in db.scalars(select(ProjectWorkflow).where(
        ProjectWorkflow.project_id.in_(project_ids)
    )).all()}
    clients = {c.id: c for c in db.scalars(select(FinanceClient).where(
        FinanceClient.id.in_([p.client_id for p in projects.values() if p.client_id is not None])
    )).all()}
    links = {link.project_id: link for link in db.scalars(select(BdEmployeeProjectLink).where(
        BdEmployeeProjectLink.project_id.in_(project_ids)
    )).all()}
    approved_links = {handoff.id: handoff for handoff in db.scalars(select(BdClientHandoff).where(
        BdClientHandoff.id.in_([link.request_id for link in links.values()])
    )).all()} if links else {}

    selected: dict[int, int] = {}
    for project_id, owners in candidates.items():
        project = projects[project_id]
        workflow = workflows.get(project_id)
        client = clients.get(project.client_id)
        if workflow is None or client is None:
            continue
        link = links.get(project_id)
        approved = approved_links.get(link.request_id) if link is not None else None
        ranked: list[tuple[int, int]] = []
        for user_id, _ in owners:
            if (link is not None and approved is not None and approved.status == "approved"
                    and approved.employee_user_id == user_id
                    and link.employee_user_id == user_id
                    and approved.registered_client_id == project.client_id):
                ranked.append((0, user_id))
            elif project.created_by_id == user_id and workflow.bd_owner_user_id == user_id:
                ranked.append((1, user_id))
            elif client.created_by_id == user_id:
                ranked.append((2, user_id))
        if ranked:
            # A deterministic tie-breaker never credits one project twice.
            selected[project_id] = min(ranked)[1]

    revisions_by_project: dict[int, list[ProjectCommercialEstimateRevision]] = defaultdict(list)
    if selected:
        for revision in db.scalars(select(ProjectCommercialEstimateRevision).where(
            ProjectCommercialEstimateRevision.project_id.in_(list(selected))
        )).all():
            revisions_by_project[revision.project_id].append(revision)

    total_by_employee: dict[int, Decimal] = defaultdict(lambda: Decimal("0.00"))
    missing: set[int] = set()
    for project_id, owner_id in selected.items():
        workflow = workflows[project_id]
        # A project counts in the period when it was submitted with its finalized
        # baseline, NOT when an unverified prospect was marked Won.
        if workflow.submitted_at is None or not (start <= workflow.submitted_at < stop):
            continue
        amount = _confirmed_project_amount(revisions_by_project.get(project_id, []), workflow)
        if amount is None:
            missing.add(owner_id)
            continue
        result[owner_id]["confirmed_projects"] += 1
        total_by_employee[owner_id] += amount
    for employee in employees:
        result[employee.id]["confirmed_sales_value"] = (
            None if employee.id in missing else float(total_by_employee[employee.id])
        )
    return result


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
    # Registered clients are FinanceClient rows, NOT names in the prospects table.
    hidden = set(hidden_client_ids(db)) if ids else set()
    unique_client_ids: set[int] = set()
    sales = _employee_sales(db, employees=employees, start=start, stop=stop)
    for employee in employees:
        client_ids = _registered_client_ids(db, employee_id=employee.id,
                                            start=start, stop=stop, hidden=hidden)
        results[employee.id]["clients"] = len(client_ids)
        unique_client_ids.update(client_ids)
    rows = []
    for employee in employees:
        rows.append({
            "user_id": employee.id, "employee_id": employee.employee_id,
            "name": employee.full_name, "email": employee.email,
            "active": bool(employee.is_active),
            **results[employee.id],
            **sales[employee.id],
        })
    summary = {key: sum(row[key] for row in rows) for key in zero}
    summary["clients"] = len(unique_client_ids)
    summary["confirmed_projects"] = sum(row["confirmed_projects"] for row in rows)
    summary["confirmed_sales_value"] = (
        None if any(row["confirmed_sales_value"] is None for row in rows)
        else sum(row["confirmed_sales_value"] for row in rows)
    )
    return {
        "start_date": start_date, "end_date": end_date,
        "employee_count": len(employees), "employees": rows, "summary": summary,
        "official_attribution": (
            "partial" if summary["confirmed_sales_value"] is None else "verified_project_value"
        ),
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
