"""Management-only operational project tracking. No database writes or financial fields.

This intentionally does NOT alter the legacy Project Tracking and Sales API,
project assignments, production, QC/QA, billing or Finance workflows.
"""
from __future__ import annotations

import io
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import get_db
from app.models.entities import User
from app.modules.finance.models import FinanceClient, FinanceProject, FinanceProjectMasterProfile
from app.modules.operations.models import (
    OrthoProjectMember, OrthoProjectProfile, OrthoWorkPackage,
    ProjectWorkflow, ProjectWorkflowEvent, ProjectWorkstream,
    WorkPackageItem, WorkPackageItemActivity,
)
from app.routers.project_tracking_progress import (
    classify_state, department_name, file_score, is_software,
    normalized, stage_score, weighted_progress,
)

router = APIRouter(prefix="/api/management/project-tracking", tags=["Operational Project Tracking"])
# Two authoritative management accounts. This is checked in addition to
# the persisted management role, so a forged UI role cannot grant access.
ALLOWED_EMAILS = frozenset({"vinod@nakshatech.com", "chethan@nakshatech.com"})


def management_only(auth: CurrentAuth = Depends(get_current_auth)) -> User:
    user = auth.user
    if not bool(user.is_active) or normalized(user.role) != "management" or str(user.email).strip().lower() not in ALLOWED_EMAILS:
        raise HTTPException(status_code=403, detail="Only authorized Management accounts can view Project Tracking")
    return user


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None


def _group(rows: list[Any], field: str) -> dict[int, list[Any]]:
    grouped: dict[int, list[Any]] = defaultdict(list)
    for row in rows:
        grouped[getattr(row, field)].append(row)
    return grouped


def _rows(db: Session, model: Any, ids: list[int], field: str = "project_id") -> list[Any]:
    if not ids:
        return []
    # Old ERP installations may not have every additive operations table.
    # Existing tables are read only; this module does not run migrations.
    from sqlalchemy import inspect
    if not inspect(db.get_bind()).has_table(model.__tablename__):
        return []
    return list(db.scalars(select(model).where(getattr(model, field).in_(ids))).all())


def _workload(projects: list[FinanceProject], db: Session) -> dict[str, Any]:
    ids = [p.id for p in projects]
    if not ids:
        return {k: {} for k in ("clients", "master", "workflow", "profile", "workstreams", "packages", "items", "members", "events", "users")}
    client_ids = sorted({p.client_id for p in projects if p.client_id is not None})
    clients = {row.id: row for row in list(db.scalars(select(FinanceClient).where(FinanceClient.id.in_(client_ids))).all())} if client_ids else {}
    masters = {row.project_id: row for row in _rows(db, FinanceProjectMasterProfile, ids)}
    workflow = {row.project_id: row for row in _rows(db, ProjectWorkflow, ids)}
    profile = {row.project_id: row for row in _rows(db, OrthoProjectProfile, ids)}
    workstreams = _group(_rows(db, ProjectWorkstream, ids), "project_id")
    packages = _group(_rows(db, OrthoWorkPackage, ids), "project_id")
    items = _group(_rows(db, WorkPackageItem, ids), "project_id")
    members = _group(_rows(db, OrthoProjectMember, ids), "project_id")
    events = _group(_rows(db, ProjectWorkflowEvent, ids), "project_id")
    user_ids: set[int] = set()
    for x in list(masters.values()):
        for attr in ("project_manager_id", "reporting_manager_id"):
            if getattr(x, attr, None): user_ids.add(getattr(x, attr))
    for x in list(profile.values()):
        if x.project_manager_user_id: user_ids.add(x.project_manager_user_id)
    for group in (workstreams, packages, items, members):
        for rows in group.values():
            for x in rows:
                for attr in ("project_manager_user_id", "team_leader_user_id", "production_user_id", "qc_user_id", "qa_user_id", "user_id"):
                    if getattr(x, attr, None): user_ids.add(getattr(x, attr))
    for rows in events.values():
        for x in rows:
            if x.actor_user_id: user_ids.add(x.actor_user_id)
    users = {row.id: row for row in list(db.scalars(select(User).where(User.id.in_(user_ids))).all())} if user_ids else {}
    return dict(clients=clients, master=masters, workflow=workflow, profile=profile,
                workstreams=workstreams, packages=packages, items=items, members=members,
                events=events, users=users)


def _name(users: dict[int, User], user_id: int | None) -> str | None:
    return users[user_id].full_name if user_id and user_id in users else None


def _department(p: FinanceProject, data: dict[str, Any]) -> str:
    wf = data["workflow"].get(p.id)
    if wf and wf.performing_department_code: return normalized(wf.performing_department_code)
    streams = data["workstreams"].get(p.id, [])
    if streams:
        chosen = sorted(streams, key=lambda s: (not s.is_active, s.sequence_order, s.id))[0]
        return normalized(chosen.department_code)
    # Do NOT guess a performing department from an unrelated user or legacy name.
    return "unassigned"


def _manager(p: FinanceProject, data: dict[str, Any]) -> str | None:
    master, profile = data["master"].get(p.id), data["profile"].get(p.id)
    uid = (getattr(profile, "project_manager_user_id", None) or
           getattr(master, "project_manager_id", None))
    if not uid:
        streams = data["workstreams"].get(p.id, [])
        uid = streams[0].project_manager_user_id if streams else None
    return _name(data["users"], uid)


def _work_units(p: FinanceProject, data: dict[str, Any], *, for_detail: bool = False) -> list[dict[str, Any]]:
    packages = [x for x in data["packages"].get(p.id, [])]
    items = [x for x in data["items"].get(p.id, []) if x.is_active]
    by_package = _group(items, "work_package_id")
    units: list[dict[str, Any]] = []
    for pkg in packages:
        base_weight = float(pkg.target_hours) if pkg.target_hours and float(pkg.target_hours) > 0 else 1.0
        current = by_package.get(pkg.id, [])
        if current:
            for item in current:
                score, state = file_score(item.status, package_delivered=bool(pkg.delivered_at))
                units.append(dict(id=f"file-{item.id}", label=item.item_name or item.item_number,
                                  code=item.item_number, package=pkg.package_code,
                                  weight=base_weight / len(current), score=score, state=state,
                                  type="file", item_id=item.id, status=item.status))
        else:
            score, state = stage_score(production=pkg.production_state, qc=pkg.qc_state,
                                       qa=pkg.qa_state, delivered=bool(pkg.delivered_at),
                                       ready=bool(pkg.ready_for_delivery_at or pkg.delivery_ready_at),
                                       fallback=pkg.current_stage if not pkg.rework_source else "rework")
            units.append(dict(id=f"area-{pkg.id}", label=pkg.package_name, code=pkg.package_code,
                              package=pkg.package_code, weight=base_weight, score=score, state=state,
                              type="survey_section", status=pkg.current_stage))
    return units if for_detail else units[:80]


def _project_row(p: FinanceProject, data: dict[str, Any]) -> dict[str, Any]:
    wf = data["workflow"].get(p.id)
    master = data["master"].get(p.id)
    client = data["clients"].get(p.client_id)
    dept = _department(p, data)
    all_units = _work_units(p, data, for_detail=True)
    completed_at = getattr(wf, "operational_completed_at", None)
    packages = data["packages"].get(p.id, [])
    delivered = bool(packages) and all(bool(x.delivered_at) for x in packages)
    if is_software(dept):
        # No software milestone table has been verified in the current schema.
        # Show one bar, but report an unavailable percentage instead of a fiction.
        percent = 100 if completed_at else None
        method = "software_milestones_not_connected" if percent is None else "workflow_completed"
        heatmap: list[dict[str, Any]] = []
    else:
        percent = weighted_progress(all_units)
        if percent is None and completed_at:
            percent = 100
        method = "stage_weighted_from_work_records" if all_units else "no_recorded_work_units"
        heatmap = [{k: u[k] for k in ("id", "label", "state", "score", "type")}
                   for u in all_units[:80]]
    rework = any(u["state"] == "rework" for u in all_units)
    if rework:
        status = "Rework"
    elif completed_at or (delivered and all_units):
        status = "Completed"
    elif not p.is_active:
        status = "Inactive"
    elif (p.end_date is not None and p.end_date < date.today() and not completed_at):
        status = "Delayed"
    elif any(u["state"] == "working" for u in all_units) or (wf and normalized(wf.status) not in {"draft", "pending", "finance_approved"}):
        status = "In Progress"
    else:
        status = "Not Started"
    start = p.start_date or _date(p.created_at)
    return dict(
        id=p.id, project_code=p.project_code, project_name=p.project_name,
        client_name=client.client_name if client else p.client_name,
        client_code=client.client_code if client else None,
        department=dept, department_label=department_name(dept),
        project_manager=_manager(p, data), description=p.description or (getattr(wf, "scope_text", None)) or (getattr(master, "task", None)),
        status=status, workflow_status=getattr(wf, "status", None),
        start_date=_iso(p.start_date), end_date=_iso(p.end_date), created_at=_iso(p.created_at),
        completed_at=_iso(completed_at), progress_percent=percent, progress_method=method,
        file_or_section_count=len(all_units), heatmap=heatmap,
        heatmap_truncated=len(all_units)>len(heatmap),
    )


def _active_between(p: FinanceProject, data: dict[str, Any], start: date, end: date) -> bool:
    wf = data["workflow"].get(p.id)
    began = p.start_date or _date(p.created_at) or date.min
    # An incomplete project remains active past its planned end date.
    finished = _date(getattr(wf, "operational_completed_at", None)) or date.max
    return began <= end and finished >= start


def _get_projects(db: Session, start: date, end: date) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    # A bounded management read; does not mutate/lock any project records.
    projects = list(db.scalars(select(FinanceProject).order_by(FinanceProject.id.desc()).limit(3000)).all())
    data = _workload(projects, db)
    data["department_catalog"] = sorted({_department(p, data) for p in projects})
    result = [_project_row(p, data) for p in projects if _active_between(p, data, start, end)]
    return result, data


@router.get("/dashboard")
def dashboard(start: date, end: date, db: Session = Depends(get_db), user: User = Depends(management_only)):
    if start > end:
        raise HTTPException(422, "Start date must not be after end date")
    projects, data = _get_projects(db, start, end)
    counts = Counter(p["status"] for p in projects)
    # Combine actual project departments with the ERP's registered technical roles.
    from app.core.roles import VALID_ROLES
    trackable = {"software_team", "software", "laser_scanning", "mobile_mapping", "lidar", "ortho", "civil", "bim", "gis", "drone"}
    codes = set(data["department_catalog"]) | (set(VALID_ROLES) & trackable)
    departments = sorted({(x, department_name(x)) for x in codes}, key=lambda x:x[1])
    values = [p["progress_percent"] for p in projects if p["progress_percent"] is not None]
    payload = dict(projects=projects, departments=[{"code": x, "label": y} for x, y in departments],
                   summary=dict(total=len(projects), ongoing=counts["In Progress"], completed=counts["Completed"],
                                rework=counts["Rework"], delayed=counts["Delayed"],
                                not_started=counts["Not Started"],
                                average_progress=round(sum(values)/len(values)) if values else None),
                   generated_at=datetime.now(timezone.utc).isoformat(), read_only=True)
    return JSONResponse(content=jsonable_encoder(payload), headers={"Cache-Control":"private, no-store"})


def _get_project(db: Session, project_id: int) -> tuple[FinanceProject, dict[str, Any]]:
    project = db.get(FinanceProject, project_id)
    if project is None: raise HTTPException(404, "Project not found")
    return project, _workload([project], db)


def _item_record(item: WorkPackageItem, data: dict[str, Any], activities: list[Any]) -> dict[str, Any]:
    score, state = file_score(item.status, activities=activities)
    return dict(id=item.id, name=item.item_name or item.item_number, code=item.item_number,
                status=item.status, state=state, progress_percent=score,
                production_employee=_name(data["users"], item.production_user_id),
                qc_employee=_name(data["users"], item.qc_user_id),
                qa_employee=_name(data["users"], item.qa_user_id),
                production_target_date=_iso(item.production_target_date),
                qc_target_date=_iso(item.qc_target_date), qa_target_date=_iso(item.qa_target_date),
                work_package_id=item.work_package_id, planned_quantity=float(item.planned_quantity) if item.planned_quantity is not None else None,
                planned_unit=item.planned_unit, created_at=_iso(item.created_at))


@router.get("/projects/{project_id}")
def project_details(project_id: int, db: Session = Depends(get_db), user: User = Depends(management_only)):
    p, data = _get_project(db, project_id)
    members = [dict(name=_name(data["users"], m.user_id), role=m.member_role, active=m.is_active)
               for m in data["members"].get(p.id, [])]
    packages = []
    for pkg in data["packages"].get(p.id, []):
        packages.append(dict(id=pkg.id, code=pkg.package_code, name=pkg.package_name,
                             current_stage=pkg.current_stage, production_state=pkg.production_state,
                             qc_state=pkg.qc_state, qa_state=pkg.qa_state,
                             target_hours=float(pkg.target_hours) if pkg.target_hours is not None else None,
                             target_date=_iso(pkg.target_date),
                             team_lead=_name(data["users"], pkg.team_leader_user_id),
                             production_employee=_name(data["users"], pkg.production_user_id),
                             qc_employee=_name(data["users"], pkg.qc_user_id),
                             qa_employee=_name(data["users"], pkg.qa_user_id),
                             delivered_at=_iso(pkg.delivered_at), rework_source=pkg.rework_source))
    events = []
    for e in sorted(data["events"].get(p.id, []), key=lambda x: x.created_at, reverse=True):
        events.append(dict(action=e.event_type, status=e.to_status, comments=e.comments,
                           at=_iso(e.created_at), actor=_name(data["users"], e.actor_user_id)))
    payload = dict(project=_project_row(p, data), members=members, packages=packages,
                   items_total=len([x for x in data["items"].get(p.id, []) if x.is_active]),
                   workflow_history=events,
                   info="Item and activity history is available through paged read-only endpoints.")
    return JSONResponse(content=jsonable_encoder(payload), headers={"Cache-Control":"private, no-store"})


@router.get("/projects/{project_id}/items")
def project_items(project_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                  db: Session = Depends(get_db), user: User = Depends(management_only)):
    _, data = _get_project(db, project_id)
    items = sorted([x for x in data["items"].get(project_id, []) if x.is_active], key=lambda x: (x.work_package_id, x.sequence_no or 0, x.id))
    subset = items[offset:offset+limit]
    return JSONResponse(content=jsonable_encoder(dict(total=len(items), offset=offset, limit=limit,
                     items=[_item_record(x, data, []) for x in subset])), headers={"Cache-Control":"private, no-store"})


@router.get("/projects/{project_id}/activity")
def project_activity(project_id: int, offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500),
                     db: Session = Depends(get_db), user: User = Depends(management_only)):
    _get_project(db, project_id)  # Ensure the parent project exists.
    from sqlalchemy import inspect
    if not inspect(db.get_bind()).has_table(WorkPackageItemActivity.__tablename__):
        return dict(total=0, offset=offset, limit=limit, activities=[])
    from sqlalchemy import func
    stmt = select(WorkPackageItemActivity).where(WorkPackageItemActivity.project_id == project_id)
    total = db.scalar(select(func.count()).select_from(WorkPackageItemActivity).where(WorkPackageItemActivity.project_id == project_id)) or 0
    rows = list(db.scalars(stmt.order_by(WorkPackageItemActivity.created_at.desc(), WorkPackageItemActivity.id.desc()).offset(offset).limit(limit)).all())
    ids = [x.employee_user_id for x in rows]
    users = {x.id: x.full_name for x in db.scalars(select(User).where(User.id.in_(ids))).all()} if ids else {}
    return JSONResponse(content=jsonable_encoder(dict(total=total, offset=offset, limit=limit,
        activities=[dict(item_id=r.work_package_item_id, stage=r.stage, status=r.status,
            started_at=_iso(r.started_at), ended_at=_iso(r.ended_at), at=_iso(r.created_at),
            employee=users.get(r.employee_user_id), remarks=r.remarks, delay_reason=r.delay_reason,
            duration_seconds=r.duration_seconds, attempt_type=r.attempt_type, attempt_number=r.attempt_number) for r in rows])),
            headers={"Cache-Control":"private, no-store"})


def _safe_excel(value: Any) -> str:
    value = "" if value is None else str(value)
    return "'" + value if value.startswith(("=", "+", "-", "@")) else value


@router.get("/export/{file_type}")
def export(file_type: str, start: date, end: date, department: str | None = None,
           status: str | None = None, db: Session = Depends(get_db), user: User = Depends(management_only)):
    if file_type not in {"xlsx", "pdf"}: raise HTTPException(400, "Unsupported export type")
    if start > end: raise HTTPException(422, "Start date must not be after end date")
    rows, _ = _get_projects(db, start, end)
    if department: rows = [r for r in rows if r["department"] == department]
    if status: rows = [r for r in rows if r["status"] == status]
    columns = [("Project Code", "project_code"), ("Project Name", "project_name"),
               ("Client Code", "client_code"), ("Client", "client_name"),
               ("Department", "department_label"), ("Project Manager", "project_manager"),
               ("Status", "status"), ("Progress %", "progress_percent"),
               ("Start Date", "start_date"), ("End Date", "end_date"),
               ("Project Description", "description"), ("Work Units", "file_or_section_count")]
    buffer = io.BytesIO()
    if file_type == "xlsx":
        wb = Workbook(); sheet = wb.active; sheet.title = "Project Tracking"
        sheet.append([col for col, _ in columns])
        for row in rows:
            sheet.append([row.get(key) if key in {"progress_percent", "file_or_section_count"}
                          else _safe_excel(row.get(key)) for _, key in columns])
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for col in "ABCDEFGHIJKL": sheet.column_dimensions[col].width = 22 if col not in "BK" else 34
        wb.save(buffer)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
        width, height = landscape(A4)
        def header():
            pdf.setFont("Helvetica-Bold", 15); pdf.drawString(30, height-40, "NakshaTech | Project Tracking")
            pdf.setFont("Helvetica", 9); pdf.drawString(30, height-58, f"Operational projects from {start} to {end}")
        header(); y = height - 90
        for row in rows:
            if y < 50: pdf.showPage(); header(); y = height-90
            name = str(row.get("project_name") or "")[:48]
            code = str(row.get("project_code") or "")[:22]
            department = str(row.get("department_label") or "")[:24]
            status = str(row.get("status") or "")[:18]
            score = row.get("progress_percent")
            percentage = "Not tracked" if score is None else str(score)+"%"
            pdf.setFont("Helvetica", 9)
            pdf.drawString(30, y, code)
            pdf.drawString(175, y, name)
            pdf.drawString(445, y, department)
            pdf.drawString(610, y, status)
            pdf.drawRightString(width-30, y, percentage)
            y -= 17
        pdf.save()
        media = "application/pdf"
    buffer.seek(0)
    return StreamingResponse(buffer, media_type=media,
        headers={"Content-Disposition":f'attachment; filename="naksha-project-tracking.{file_type}"',
                 "Cache-Control":"private, no-store"})
