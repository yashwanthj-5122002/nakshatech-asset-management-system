"""Isolated non-billable pilots attached to the existing project/workflow engine.

Only BD controls pilot creation, feedback recording and optional paid linking.
Standard operations modules are not replaced or monkey-patched.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import utc_now
from app.modules.finance.models import FinanceProject
from app.modules.finance.service import set_project_status
from app.modules.notifications.service import create_global_notification
from app.modules.operations.models import ProjectWorkflow, ProjectWorkflowEvent
from app.modules.operations.schemas import WorkflowProjectCreate
from app.modules.operations.workflow_service import (
    WORKFLOW_FINANCE_APPROVED, create_bd_project,
)

router = APIRouter(prefix="/pilots", tags=["Non-billable Pilot Projects"])


class PilotCreate(WorkflowProjectCreate):
    # All workflow fields are reused. Pilot-specific inputs are additive.
    client_data_percentage: Decimal = Field(default=Decimal("2.00"), gt=0, le=100)
    client_data_reference: str = Field(default="Client-provided sample", min_length=3, max_length=500)


class PilotDelivery(BaseModel):
    delivery_reference: str = Field(min_length=3, max_length=500)


class PilotFeedback(BaseModel):
    satisfaction: Literal["satisfied", "not_satisfied"]
    feedback_note: str = Field(min_length=5, max_length=2000)


class PaidLink(BaseModel):
    paid_project_id: int = Field(gt=0)


def _role(auth: CurrentAuth) -> str:
    return str(auth.effective_role or "").strip().lower()


def _bd(auth: CurrentAuth) -> None:
    if _role(auth) != "bd":
        raise HTTPException(403, "Business Development permission required")


def _allowed(auth: CurrentAuth) -> None:
    if _role(auth) not in {"bd", "finance", "software_team", "management", "admin"}:
        raise HTTPException(403, "Pilot registry access denied")


def _record(db: Session, project_id: int, *, lock: bool = False):
    stmt = text("SELECT * FROM ops_pilot_projects WHERE project_id = :pid" + (" FOR UPDATE" if lock else ""))
    row = db.execute(stmt, {"pid": project_id}).mappings().first()
    if not row:
        raise HTTPException(404, "Pilot project not found")
    return row


def _as_json(db: Session, record) -> dict:
    project = db.get(FinanceProject, record["project_id"])
    workflow = db.get(ProjectWorkflow, record["project_id"])
    ready = bool(workflow and workflow.operational_completed_at and record["delivered_at"])
    eligible = bool(ready and record["satisfaction"] == "satisfied" and not record["paid_project_id"])
    return {
        "id": record["project_id"], "project_id": record["project_id"],
        "client_id": project.client_id if project else None,
        "project_code": project.project_code if project else str(record["project_id"]),
        "project_name": project.project_name if project else "Pilot",
        "project_type": "pilot", "non_billable": True,
        "client_data_percentage": float(record["client_data_percentage"]),
        "client_data_reference": record["client_data_reference"],
        "workflow_status": workflow.status if workflow else "unknown",
        "operational_completed_at": workflow.operational_completed_at.isoformat() if workflow and workflow.operational_completed_at else None,
        "delivered_at": record["delivered_at"].isoformat() if record["delivered_at"] else None,
        "delivery_reference": record["delivery_reference"],
        "satisfaction": record["satisfaction"], "feedback_note": record["feedback_note"],
        "feedback_at": record["feedback_at"].isoformat() if record["feedback_at"] else None,
        "paid_project_id": record["paid_project_id"],
        "conversion_eligible": eligible, "conversion_deferred": bool(record["conversion_deferred"]),
        "status": record["status"],
    }


def _owner_or_admin(db: Session, auth: CurrentAuth, row) -> None:
    if _role(auth) in {"admin", "management"}:
        return
    if _role(auth) == "bd" and row["bd_owner_user_id"] == auth.user.id:
        return
    raise HTTPException(403, "This pilot belongs to another BD owner")


@router.get("")
def list_pilots(db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _allowed(auth)
    stmt = "SELECT * FROM ops_pilot_projects"
    args = {}
    if _role(auth) == "bd":
        stmt += " WHERE bd_owner_user_id = :owner"
        args["owner"] = auth.user.id
    stmt += " ORDER BY created_at DESC, project_id DESC LIMIT 500"
    records = db.execute(text(stmt), args).mappings().all()
    return [_as_json(db, record) for record in records]


@router.get("/{project_id}")
def get_pilot(project_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _allowed(auth)
    row = _record(db, project_id)
    if _role(auth) == "bd":
        _owner_or_admin(db, auth, row)
    return _as_json(db, row)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_pilot(payload: PilotCreate, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _bd(auth)
    if not payload.project_code.strip().upper().startswith("PILOT-"):
        raise HTTPException(422, "Pilot Project ID must start with PILOT- so all departments recognize it")
    if payload.commercial is not None:
        raise HTTPException(422, "Pilot must not contain commercial estimates or billing terms")
    if payload.commercial_value != 0:
        raise HTTPException(422, "Pilot commercial amount must be zero")
    if payload.po_wo_number:
        raise HTTPException(422, "Pilot cannot have a purchase or work order")
    try:
        # The same authoritative project, PM/team assignment and QA/QC engine is used.
        # Finance commercial approval is *not* invoked for a free demo.
        normal = payload.model_copy(update={
            "commercial": None, "commercial_value": Decimal("0"),
            "po_wo_number": None, "currency": "INR", "attachment_references": [],
        })
        project, workflow = create_bd_project(db, actor=auth.user, payload=normal)
        workflow.status = WORKFLOW_FINANCE_APPROVED
        workflow.approved_at = utc_now()
        set_project_status(db, project=project, actor=auth.user, project_status="active")
        db.execute(text("""
            INSERT INTO ops_pilot_projects (
                project_id, bd_owner_user_id, client_data_percentage, client_data_reference,
                status, created_at, conversion_deferred
            ) VALUES (:pid, :uid, :pct, :ref, 'active', CURRENT_TIMESTAMP, FALSE)
        """), {"pid": project.id, "uid": auth.user.id,
                "pct": payload.client_data_percentage, "ref": payload.client_data_reference.strip()})
        db.add(ProjectWorkflowEvent(
            project_id=project.id, event_type="pilot_nonbillable_authorized",
            from_status="draft", to_status=WORKFLOW_FINANCE_APPROVED,
            comments="Client supplied sample; non-billable pilot. Finance notified for information only.",
            actor_user_id=auth.user.id,
        ))
        for role in ("finance", "software_team"):
            create_global_notification(
                db, event_type="pilot.created", category="system",
                title=f"NON-BILLABLE PILOT: {project.project_code}",
                message=f"Pilot {project.project_code} created with {payload.client_data_percentage}% client-provided data. No client invoice, payment, or project expense is permitted. Informational notification only.",
                target_url=(f"/finance?project={project.id}" if role == "finance" else "/"),
                recipient_roles=[role], dedupe_key=f"pilot.created.{project.id}.{role}",
                requires_action=False, severity="info",
                metadata={"project_id":project.id,"project_type":"pilot","non_billable":True},
            )
        db.commit()
        row = _record(db, project.id)
        return _as_json(db, row)
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(422, f"Unable to create pilot: {exc}") from exc


@router.post("/{project_id}/deliver")
def mark_pilot_client_delivery(project_id: int, payload: PilotDelivery,
                               db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _bd(auth)
    row = _record(db, project_id, lock=True)
    _owner_or_admin(db, auth, row)
    wf = db.get(ProjectWorkflow, project_id)
    # Operational completion already validates *all* work packages' full stages.
    if not wf or not wf.operational_completed_at:
        raise HTTPException(409, "Finish every assigned work package, QA/QC, and PM operational completion before client delivery")
    if row["delivered_at"]:
        raise HTTPException(409, "Pilot has already been delivered; maintain the original delivery evidence")
    db.execute(text("""UPDATE ops_pilot_projects SET delivered_at=CURRENT_TIMESTAMP,
         delivery_reference=:ref, status='delivered' WHERE project_id=:pid"""),
        {"ref":payload.delivery_reference.strip(), "pid":project_id})
    db.commit()
    return _as_json(db, _record(db, project_id))


@router.post("/{project_id}/feedback")
def pilot_client_feedback(project_id: int, payload: PilotFeedback,
                          db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    """BD records feedback actually received from the client (mail/call/letter).

    Do not represent this endpoint as a client-authenticated feedback portal.
    """
    _bd(auth)
    row = _record(db, project_id, lock=True)
    _owner_or_admin(db, auth, row)
    if not row["delivered_at"]:
        raise HTTPException(409, "Pilot must first be delivered to the client")
    if row["satisfaction"] is not None:
        raise HTTPException(409, "Client feedback already recorded; revisions require an audited correction procedure")
    db.execute(text("""UPDATE ops_pilot_projects SET satisfaction=:s, feedback_note=:note,
        feedback_at=CURRENT_TIMESTAMP, status=:stat, conversion_deferred=FALSE WHERE project_id=:pid"""),
        {"s":payload.satisfaction,"note":payload.feedback_note.strip(),
         "stat":"eligible" if payload.satisfaction == "satisfied" else "feedback_negative", "pid":project_id})
    project = db.get(FinanceProject, project_id)
    if payload.satisfaction == "satisfied":
        create_global_notification(db, event_type="pilot.client_satisfied", category="approval",
            title=f"Pilot approved by client: {project.project_code}",
            message="Client feedback is positive after full processing and sample delivery. BD: decide whether to create a separate paid project. No automatic conversion.",
            target_url=f"/bd/clients?client={project.client_id}&pilot={project_id}",
            recipient_user_ids=[row["bd_owner_user_id"]],
            dedupe_key=f"pilot.satisfied.{project_id}", requires_action=True,
            severity="success", metadata={"project_id":project_id,"project_type":"pilot"})
    db.commit()
    return _as_json(db, _record(db, project_id))


@router.post("/{project_id}/defer")
def defer_conversion(project_id: int, db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    _bd(auth)
    row = _record(db, project_id, lock=True)
    _owner_or_admin(db, auth, row)
    if row["satisfaction"] != "satisfied" or not row["delivered_at"]:
        raise HTTPException(409, "Conversion is only available after delivered, satisfied feedback")
    db.execute(text("UPDATE ops_pilot_projects SET conversion_deferred=TRUE WHERE project_id=:pid"), {"pid":project_id})
    db.commit()
    return {"deferred": True}


@router.post("/{project_id}/link-paid")
def link_paid(project_id: int, payload: PaidLink,
              db: Session = Depends(get_db), auth: CurrentAuth = Depends(get_current_auth)):
    """Called only after standard Create Project saves its paid-project record."""
    _bd(auth)
    row = _record(db, project_id, lock=True)
    _owner_or_admin(db, auth, row)
    wf = db.get(ProjectWorkflow, project_id)
    if not wf or not wf.operational_completed_at or not row["delivered_at"] or row["satisfaction"] != "satisfied":
        raise HTTPException(409, "All workflow, delivery, and satisfied-feedback gates must be complete")
    if row["paid_project_id"]:
        if row["paid_project_id"] == payload.paid_project_id:
            return _as_json(db, row)
        raise HTTPException(409, "Pilot already linked to another paid project")
    paid = db.get(FinanceProject, payload.paid_project_id)
    if not paid or paid.id == project_id or paid.client_id != (db.get(FinanceProject, project_id)).client_id:
        raise HTTPException(422, "Paid project must be a distinct, existing project for the same client")
    if db.execute(text("SELECT 1 FROM ops_pilot_projects WHERE project_id=:pid"), {"pid":paid.id}).first():
        raise HTTPException(422, "The linked record must be a paid project, not another pilot")
    paid_workflow = db.get(ProjectWorkflow, paid.id)
    if not paid_workflow or paid_workflow.bd_owner_user_id != auth.user.id:
        raise HTTPException(403, "Only the owner of the newly created paid project may link it")
    if paid_workflow.commercial_value is None or paid_workflow.commercial_value <= 0:
        raise HTTPException(422, "Paid project must have a positive commercial value")
    db.execute(text("UPDATE ops_pilot_projects SET paid_project_id=:paid, status='converted' WHERE project_id=:pid"),
        {"paid":paid.id,"pid":project_id})
    create_global_notification(db, event_type="pilot.paid_project_created", category="system",
        title=f"Paid project created from pilot: {paid.project_code}",
        message=f"Pilot {project_id} resulted in paid project {paid.project_code}. Normal commercial and Finance approval rules now apply only to the new paid project.",
        target_url=f"/finance?project={paid.id}", recipient_roles=["finance"],
        dedupe_key=f"pilot.converted.{project_id}",requires_action=False)
    db.commit()
    return _as_json(db, _record(db, project_id))
