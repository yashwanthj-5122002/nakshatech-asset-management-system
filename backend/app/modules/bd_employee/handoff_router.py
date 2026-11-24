"""Get Client -> BD Manager registers or links client -> manager-created project attribution.

Every route uses the database principal; employee IDs from requests never select ownership.
No Finance/Management-origin client is returned through employee endpoints.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User, utc_now
from app.modules.bd_employee.handoff_models import BdClientHandoff, BdClientHandoffEvent, BdEmployeeProjectLink
from app.modules.bd_employee.models import BdEmployeeProspect
from app.modules.finance.models import FinanceClient, FinanceProject
from app.modules.finance.visibility import hidden_client_ids
from app.modules.finance.schemas import FinanceClientCreateRequest
from app.modules.operations.workflow_service import create_bd_client

router = APIRouter(prefix="/client-handoff", tags=["BD Client Handoff"])


class GetClientInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prospect_id: int | None = None
    company_name: str = Field(min_length=2, max_length=255)
    contact_person: str = Field(min_length=2, max_length=255)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=40)
    country: str = Field(default="India", min_length=2, max_length=100)
    address: str | None = Field(default=None, max_length=3000)
    gst_number: str | None = Field(default=None, max_length=32)
    lead_source: str = Field(default="other", max_length=40)
    service_interest: str | None = Field(default=None, max_length=255)
    remarks: str | None = Field(default=None, max_length=4000)


class ManagerReturn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


class ManagerApprove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_code: str | None = Field(default=None, max_length=32)
    existing_client_id: int | None = None
    note: str | None = Field(default=None, max_length=2000)


def _employee(auth: CurrentAuth = Depends(get_current_auth)) -> User:
    if auth.user.role != "bd_employee" or auth.effective_role != "bd_employee":
        raise HTTPException(403, "BD Employee access required")
    return auth.user


def _manager(auth: CurrentAuth = Depends(get_current_auth)) -> User:
    if auth.user.role != "bd" or auth.effective_role != "bd":
        raise HTTPException(403, "BD Manager access required")
    return auth.user


def _row(row: BdClientHandoff, employee: User | None = None) -> dict:
    return {
        "id": row.id, "employee_user_id": row.employee_user_id,
        "employee_id": employee.employee_id if employee else None,
        "employee_name": employee.full_name if employee else None,
        "prospect_id": row.prospect_id, "company_name": row.company_name,
        "contact_person": row.contact_person, "contact_email": row.contact_email,
        "contact_phone": row.contact_phone, "country": row.country, "address": row.address,
        "gst_number": row.gst_number, "lead_source": row.lead_source,
        "service_interest": row.service_interest, "remarks": row.remarks,
        "status": row.status, "manager_note": row.manager_note,
        "registered_client_id": row.registered_client_id,
        "created_at": row.created_at, "reviewed_at": row.reviewed_at,
    }


def _audit(db: Session, row: BdClientHandoff, user: User, action: str, note: str | None = None) -> None:
    db.add(BdClientHandoffEvent(request_id=row.id, actor_user_id=user.id, action=action, note=note))


def _get_pending(db: Session, request_id: int) -> BdClientHandoff:
    row = db.scalar(select(BdClientHandoff).where(BdClientHandoff.id == request_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Client request not found")
    if row.status != "pending":
        raise HTTPException(409, "This request has already been reviewed. Refresh the list.")
    return row


@router.get("/my-requests")
def my_requests(db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    rows = db.scalars(select(BdClientHandoff).where(
        BdClientHandoff.employee_user_id == employee.id
    ).order_by(BdClientHandoff.created_at.desc(), BdClientHandoff.id.desc())).all()
    return {"items": [_row(r) for r in rows]}


@router.post("/my-requests", status_code=201)
def submit_client(payload: GetClientInput, db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    if payload.prospect_id is not None:
        prospect = db.scalar(select(BdEmployeeProspect).where(
            BdEmployeeProspect.id == payload.prospect_id,
            BdEmployeeProspect.owner_user_id == employee.id,
        ))
        if prospect is None:
            raise HTTPException(404, "Your prospect was not found")
        # A prospect should not generate competing open requests.
        already = db.scalar(select(BdClientHandoff.id).where(
            BdClientHandoff.prospect_id == payload.prospect_id,
            BdClientHandoff.status.in_(["pending", "approved"]),
        ).limit(1))
        if already is not None:
            raise HTTPException(409, "A pending or approved request already exists for this prospect")
    data = payload.model_dump()
    data["company_name"] = data["company_name"].strip()
    data["contact_person"] = data["contact_person"].strip()
    if not data["company_name"] or not data["contact_person"]:
        raise HTTPException(422, "Company and contact person are required")
    row = BdClientHandoff(employee_user_id=employee.id, **data)
    db.add(row)
    db.flush()
    _audit(db, row, employee, "submitted")
    db.commit()
    db.refresh(row)
    return _row(row)


@router.put("/my-requests/{request_id}")
def resubmit_returned(
    request_id: int, payload: GetClientInput,
    db: Session = Depends(get_db), employee: User = Depends(_employee),
) -> dict:
    row = db.scalar(select(BdClientHandoff).where(
        BdClientHandoff.id == request_id,
        BdClientHandoff.employee_user_id == employee.id,
    ).with_for_update())
    if row is None:
        raise HTTPException(404, "Your request was not found")
    if row.status != "returned":
        raise HTTPException(409, "Only returned requests may be edited and resubmitted")
    if payload.prospect_id is not None:
        own = db.scalar(select(BdEmployeeProspect.id).where(
            BdEmployeeProspect.id == payload.prospect_id,
            BdEmployeeProspect.owner_user_id == employee.id,
        ))
        if own is None:
            raise HTTPException(404, "Your prospect was not found")
        conflicting = db.scalar(select(BdClientHandoff.id).where(
            BdClientHandoff.prospect_id == payload.prospect_id,
            BdClientHandoff.id != request_id,
            BdClientHandoff.status.in_(["pending", "approved"]),
        ).limit(1))
        if conflicting is not None:
            raise HTTPException(409, "Another pending or approved request exists for this prospect")
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.status = "pending"
    row.manager_note = None
    row.reviewed_by_id = None
    row.reviewed_at = None
    _audit(db, row, employee, "resubmitted")
    db.commit()
    return _row(row)


@router.get("/my-clients")
def my_clients(db: Session = Depends(get_db), employee: User = Depends(_employee)) -> dict:
    # This does not enumerate all BD clients: only those explicitly approved for this employee.
    records = db.execute(
        select(BdClientHandoff, FinanceClient).join(
            FinanceClient, FinanceClient.id == BdClientHandoff.registered_client_id
        ).where(
            BdClientHandoff.employee_user_id == employee.id,
            BdClientHandoff.status == "approved",
            FinanceClient.source_team == "bd_team",
            FinanceClient.is_active.is_(True),
            FinanceClient.id.not_in(hidden_client_ids(db)),
        ).order_by(BdClientHandoff.reviewed_at.desc())
    ).all()
    results = []
    for req, client in records:
        # Count explicitly attributed projects only (not unrelated projects on the same client).
        count = db.scalar(select(func.count(BdEmployeeProjectLink.project_id)).where(
            BdEmployeeProjectLink.request_id == req.id,
            BdEmployeeProjectLink.employee_user_id == employee.id,
        )) or 0
        results.append({
            "id": client.id, "client_code": client.client_code,
            "client_name": client.client_name, "contact_person_name": client.contact_person_name,
            "contact_person_phone": client.contact_person_phone,
            "client_email": client.client_email, "country": client.country,
            "address": client.address, "project_count": int(count),
            "request_id": req.id, "registered_at": req.reviewed_at,
        })
    return {"items": results}


@router.get("/manager/requests")
def manager_requests(
    request_status: str = Query(default="all", pattern="^(all|pending|approved|returned)$"),
    db: Session = Depends(get_db), manager: User = Depends(_manager),
) -> dict:
    stmt = select(BdClientHandoff)
    if request_status != "all":
        stmt = stmt.where(BdClientHandoff.status == request_status)
    rows = db.scalars(stmt.order_by(BdClientHandoff.created_at.desc(), BdClientHandoff.id.desc()).limit(500)).all()
    users = {u.id: u for u in db.scalars(select(User).where(
        User.id.in_([r.employee_user_id for r in rows])
    )).all()} if rows else {}
    return {"items": [_row(r, users.get(r.employee_user_id)) for r in rows]}


@router.post("/manager/requests/{request_id}/return")
def return_request(
    request_id: int, payload: ManagerReturn,
    db: Session = Depends(get_db), manager: User = Depends(_manager),
) -> dict:
    row = _get_pending(db, request_id)
    row.status = "returned"
    row.manager_note = payload.note.strip()
    row.reviewed_by_id = manager.id
    row.reviewed_at = utc_now()
    _audit(db, row, manager, "returned", row.manager_note)
    db.commit()
    return _row(row)


@router.post("/manager/requests/{request_id}/approve")
def approve_request(
    request_id: int, payload: ManagerApprove,
    db: Session = Depends(get_db), manager: User = Depends(_manager),
) -> dict:
    if bool(payload.client_code) == bool(payload.existing_client_id):
        raise HTTPException(422, "Provide a new client ID OR select an existing BD client")
    row = _get_pending(db, request_id)
    if payload.existing_client_id is not None:
        client = db.scalar(select(FinanceClient).where(
            FinanceClient.id == payload.existing_client_id,
            FinanceClient.source_team == "bd_team", FinanceClient.is_active.is_(True),
            FinanceClient.id.not_in(hidden_client_ids(db)),
        ).with_for_update())
        if client is None:
            raise HTTPException(404, "Existing BD client not found")
        duplicate_claim = db.scalar(select(BdClientHandoff.id).where(
            BdClientHandoff.registered_client_id == client.id
        ).limit(1))
        if duplicate_claim is not None:
            raise HTTPException(409, "This client is already attributed to a BD employee")
    else:
        # Prevent creating another official client for a matching registered
        # organization/email. The manager may instead link an existing BD client.
        duplicate = db.scalar(select(FinanceClient.id).where(
            func.lower(func.trim(FinanceClient.client_name)) == row.company_name.strip().lower(),
            FinanceClient.source_team == "bd_team",
            FinanceClient.id.not_in(hidden_client_ids(db)),
        ).limit(1))
        if duplicate is None and row.contact_email:
            duplicate = db.scalar(select(FinanceClient.id).where(
                func.lower(FinanceClient.client_email) == row.contact_email.strip().lower(),
                FinanceClient.source_team == "bd_team",
                FinanceClient.id.not_in(hidden_client_ids(db)),
            ).limit(1))
        if duplicate is not None:
            raise HTTPException(409, "A client with this company name or email already exists; check the Client Register and link an existing BD client instead")
        try:
            employee = db.get(User, row.employee_user_id)
            if employee is None or employee.role != "bd_employee":
                raise HTTPException(409, "Employee account is unavailable; do not register the client")
            client = create_bd_client(db, actor=manager, payload=FinanceClientCreateRequest(
                client_code=payload.client_code,
                client_name=row.company_name, contact_person_name=row.contact_person,
                contact_person_phone=row.contact_phone,
                contact_person_email=row.contact_email,
                client_email=row.contact_email, primary_phone=row.contact_phone,
                country=row.country, address=row.address, gst_number=row.gst_number,
                task=row.service_interest, description=row.remarks,
                source_team="bd_team", source_person_name=employee.full_name,
                bd_name=employee.full_name,
            ))
            db.flush()
        except (ValueError, IntegrityError) as exc:
            db.rollback()
            raise HTTPException(409, "Client ID conflicts with an existing client; review before approving") from exc
        except ValidationError as exc:
            db.rollback()
            raise HTTPException(422, "Invalid client details or client ID. Return request for correction.") from exc
    row.status = "approved"
    row.registered_client_id = client.id
    row.manager_note = payload.note
    row.reviewed_by_id = manager.id
    row.reviewed_at = utc_now()
    _audit(db, row, manager, "approved", f"Client {client.client_code}; {payload.note or ''}".strip())
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Client was already assigned to another request") from exc
    return {"request": _row(row), "client_code": client.client_code, "client_id": client.id}


def link_new_bd_project_if_requested(db: Session, *, project: FinanceProject, manager: User) -> None:
    """Called in the existing manager-only BD project-creation transaction, before commit.

    No project is exposed to an employee unless a manager explicitly registered
    or linked the originating client request beforehand.
    """
    if manager.role != "bd" or project.project_source_team != "bd_team" or project.client_id is None:
        return
    row = db.scalar(select(BdClientHandoff).where(
        BdClientHandoff.registered_client_id == project.client_id,
        BdClientHandoff.status == "approved",
    ).limit(1))
    if row is not None and row.reviewed_at is not None and project.created_at is not None and project.created_at >= row.reviewed_at:
        db.add(BdEmployeeProjectLink(
            project_id=project.id, request_id=row.id,
            employee_user_id=row.employee_user_id, manager_user_id=manager.id,
        ))


def synchronize_bd_project_link(db: Session, *, project: FinanceProject, manager: User) -> None:
    """BD Manager may correct draft/returned project's client; keep attribution exact."""
    existing = db.get(BdEmployeeProjectLink, project.id)
    if existing is not None:
        db.delete(existing)
        db.flush()
    link_new_bd_project_if_requested(db, project=project, manager=manager)
