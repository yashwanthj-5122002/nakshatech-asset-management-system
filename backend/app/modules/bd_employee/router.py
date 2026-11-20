"""Strict BD employee prospect endpoints and owned official-project read access.

No management-origin data, cross-employee records, or manager-only mutations are exposed.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.modules.bd_employee.models import BdEmployeeContactActivity, BdEmployeeProspect

router = APIRouter(prefix="/bd-employee", tags=["BD Employee Workspace"])

LeadSource = Literal["linkedin", "google", "email", "phone", "referral", "website", "other"]
LeadStatus = Literal["new", "contacted", "no_response", "replied", "interested", "not_interested", "enquiry", "won"]
ContactChannel = Literal["linkedin", "email", "phone", "whatsapp", "meeting", "other"]
ContactOutcome = Literal["no_response", "replied", "interested", "not_interested", "callback", "enquiry", "won"]


class ProspectInput(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    contact_person: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=80)
    source: LeadSource = "other"
    service_interest: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    next_followup_date: date | None = None


class ProspectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_name: str | None = Field(default=None, min_length=2, max_length=255)
    contact_person: str | None = Field(default=None, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=80)
    source: LeadSource | None = None
    service_interest: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=4000)
    next_followup_date: date | None = None
    status: LeadStatus | None = None


class ActivityInput(BaseModel):
    channel: ContactChannel
    outcome: ContactOutcome
    remarks: str | None = Field(default=None, max_length=4000)
    next_followup_date: date | None = None


def _employee(auth: CurrentAuth = Depends(get_current_auth)) -> int:
    # Use the persisted user role, not only the claim. This also prevents access
    # after changing the account role without waiting for old tokens to expire.
    if auth.user.role != "bd_employee" or auth.effective_role != "bd_employee":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="BD Employee access required")
    return auth.user.id


def _own(db: Session, owner_id: int, prospect_id: int, *, lock: bool = False) -> BdEmployeeProspect:
    stmt = select(BdEmployeeProspect).where(
        BdEmployeeProspect.id == prospect_id,
        BdEmployeeProspect.owner_user_id == owner_id,
    )
    prospect = db.scalar(stmt.with_for_update() if lock else stmt)
    if not prospect:
        raise HTTPException(status_code=404, detail="Prospect not found")
    return prospect


def _as_prospect(row: BdEmployeeProspect) -> dict:
    return {
        "id": row.id, "company_name": row.company_name,
        "contact_person": row.contact_person, "contact_email": row.contact_email,
        "contact_phone": row.contact_phone, "source": row.source,
        "service_interest": row.service_interest, "status": row.status,
        "notes": row.notes, "next_followup_date": row.next_followup_date,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), owner_id: int = Depends(_employee)) -> dict:
    rows = db.scalars(select(BdEmployeeProspect).where(
        BdEmployeeProspect.owner_user_id == owner_id,
    )).all()
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    day_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    utc_start = day_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = (day_start + timedelta(days=1)).astimezone(timezone.utc).replace(tzinfo=None)
    closed = {"not_interested", "won"}
    due = [row for row in rows if row.next_followup_date and row.next_followup_date <= today and row.status not in closed]
    recent = db.scalars(select(BdEmployeeContactActivity).where(
        BdEmployeeContactActivity.owner_user_id == owner_id,
        BdEmployeeContactActivity.contacted_at >= utc_start,
        BdEmployeeContactActivity.contacted_at < utc_end,
    )).all()
    return {
        "prospects": len(rows),
        "contacted": sum(p.status != "new" for p in rows),
        "responded": sum(p.status in {"replied", "interested", "enquiry", "won"} for p in rows),
        "open_enquiries": sum(p.status == "enquiry" for p in rows),
        "followups_due": len(due),
        "activities_today": len(recent),
        "upcoming_followups": [_as_prospect(p) for p in sorted(
            (r for r in rows if r.next_followup_date and r.status not in closed),
            key=lambda r: (r.next_followup_date, r.id),
        )[:15]],
    }


@router.get("/projects")
def own_official_projects(
    db: Session = Depends(get_db),
    owner_id: int = Depends(_employee),
) -> dict:
    """Official projects explicitly linked to this employee after BD Manager creation.

    The project must be BD-origin and owned by a BD Manager in the existing
    workflow. A user-supplied employee/project id cannot widen authorization.
    """
    from app.modules.bd_employee.handoff_models import BdClientHandoff, BdEmployeeProjectLink
    from app.modules.finance.models import FinanceClient, FinanceProject
    from app.modules.finance.visibility import exclude_hidden_projects
    from app.modules.operations.models import ProjectWorkflow
    from app.modules.operations.workflow_service import _full_project_payload, _project_query

    query = (
        _project_query()
        .join(BdEmployeeProjectLink, BdEmployeeProjectLink.project_id == FinanceProject.id)
        .join(BdClientHandoff, BdClientHandoff.id == BdEmployeeProjectLink.request_id)
        .join(ProjectWorkflow, ProjectWorkflow.project_id == FinanceProject.id)
        .join(FinanceClient, FinanceClient.id == FinanceProject.client_id)
        .where(
            BdEmployeeProjectLink.employee_user_id == owner_id,
            BdClientHandoff.employee_user_id == owner_id,
            BdClientHandoff.registered_client_id == FinanceProject.client_id,
            BdClientHandoff.status == "approved",
            FinanceProject.created_by_id == BdEmployeeProjectLink.manager_user_id,
            ProjectWorkflow.bd_owner_user_id == BdEmployeeProjectLink.manager_user_id,
            FinanceProject.project_source_team == "bd_team",
            FinanceClient.source_team == "bd_team",
        )
    )
    query = exclude_hidden_projects(db, query)
    projects = db.scalars(
        query.order_by(FinanceProject.updated_at.desc(), FinanceProject.id.desc())
    ).unique().all()
    workflows = {
        workflow.project_id: workflow
        for workflow in db.scalars(
            select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_([p.id for p in projects]))
        ).all()
    } if projects else {}
    return {"projects": [_full_project_payload(db, p, workflows[p.id]) for p in projects]}


@router.get("/prospects")
def prospects(
    search: str = Query(default="", max_length=120),
    db: Session = Depends(get_db),
    owner_id: int = Depends(_employee),
) -> dict:
    stmt = select(BdEmployeeProspect).where(BdEmployeeProspect.owner_user_id == owner_id)
    if search.strip():
        needle = f"%{search.strip()}%"
        stmt = stmt.where(BdEmployeeProspect.company_name.ilike(needle))
    rows = db.scalars(stmt.order_by(BdEmployeeProspect.created_at.desc(), BdEmployeeProspect.id.desc()).limit(500)).all()
    return {"items": [_as_prospect(p) for p in rows]}


@router.post("/prospects", status_code=201)
def create_prospect(
    payload: ProspectInput,
    db: Session = Depends(get_db),
    owner_id: int = Depends(_employee),
) -> dict:
    record = BdEmployeeProspect(owner_user_id=owner_id, **payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return _as_prospect(record)


@router.patch("/prospects/{prospect_id}")
def update_prospect(
    prospect_id: int, payload: ProspectUpdate,
    db: Session = Depends(get_db), owner_id: int = Depends(_employee),
) -> dict:
    record = _own(db, owner_id, prospect_id, lock=True)
    for name, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, name, value)
    db.commit()
    db.refresh(record)
    return _as_prospect(record)


@router.get("/prospects/{prospect_id}/activities")
def contact_history(
    prospect_id: int, db: Session = Depends(get_db), owner_id: int = Depends(_employee),
) -> dict:
    _own(db, owner_id, prospect_id)
    events = db.scalars(select(BdEmployeeContactActivity).where(
        BdEmployeeContactActivity.prospect_id == prospect_id,
        BdEmployeeContactActivity.owner_user_id == owner_id,
    ).order_by(BdEmployeeContactActivity.contacted_at.desc(), BdEmployeeContactActivity.id.desc())).all()
    return {"items": [{
        "id": event.id, "channel": event.channel, "outcome": event.outcome,
        "remarks": event.remarks, "contacted_at": event.contacted_at,
    } for event in events]}


@router.post("/prospects/{prospect_id}/activities", status_code=201)
def log_contact(
    prospect_id: int, payload: ActivityInput,
    db: Session = Depends(get_db), owner_id: int = Depends(_employee),
) -> dict:
    record = _own(db, owner_id, prospect_id, lock=True)
    state_map = {
        "no_response": "no_response", "replied": "replied", "interested": "interested",
        "not_interested": "not_interested", "callback": "contacted",
        "enquiry": "enquiry", "won": "won",
    }
    event = BdEmployeeContactActivity(
        prospect_id=record.id, owner_user_id=owner_id,
        channel=payload.channel, outcome=payload.outcome,
        remarks=payload.remarks,
    )
    db.add(event)
    record.status = state_map[payload.outcome]
    if "next_followup_date" in payload.model_fields_set:
        record.next_followup_date = payload.next_followup_date
    db.commit()
    db.refresh(event)
    return {"id": event.id, "status": record.status, "contacted_at": event.contacted_at}


# The handoff endpoints live under this existing authenticated BD employee router.
from app.modules.bd_employee.direct_router import router as bd_direct_router
router.include_router(bd_direct_router)
