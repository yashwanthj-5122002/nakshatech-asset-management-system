"""Shared project production tracking service (V8.1 additive extension).

Extends the EXISTING authoritative workflow engine (``workflow_service``) with:
- generic per-package stage updates for the optional additional stages
  (Import / DXF / Inspection / Upload) with append-only audit events;
- general work-package context fields (Lot/Batch, Supply Date, Remarks);
- a merged stage-history read model (daily production + QC/QA reviews + stage events);
- server-side production-tracking summaries (Team Lead / PM / Management).

Nothing here re-implements or shadows the authoritative transitions (team setup,
allocation, daily activity, production complete, QC, QA, delivery, operational
completion); those remain exclusively in ``workflow_service``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.departments import (
    is_technical_pm_role,
    normalize_department_code_or_default,
)
from app.models.entities import User, utc_now
from app.modules.finance.models import FinanceProject, FinanceProjectMasterProfile
from app.modules.finance.visibility import filter_visible_project_ids
from app.modules.operations.models import (
    OrthoProjectMember,
    OrthoStageEvent,
    OrthoWorkPackage,
    ProjectWorkflow,
)
from app.modules.operations.production_stages import (
    STAGE_DXF,
    STAGE_IMPORT,
    STAGE_INSPECTION,
    STAGE_LABELS,
    STAGE_STATUSES,
    STAGE_STATUS_ATTR,
    STAGE_TIMESTAMP_ATTR,
    STAGE_UPLOAD,
    TRACKABLE_STAGES,
    aggregate_project_progress,
    effective_pending_stages,
    item_stage_status,
    package_production_progress,
    package_workflow_progress,
    pending_stages,
    stage_profile_for_department,
    stage_status,
)
from app.modules.operations.uom import known_units, measurement_type
from app.modules.operations.production_items import (
    deadline_status,
    file_aggregates_for_packages,
    package_completion_for_deadline,
)

ADMIN_ROLE = "admin"
MANAGEMENT_ROLE = "management"
EMPLOYEE_ROLE = "employee"


def _is_pm_for_project(project: FinanceProject, user_id: int) -> bool:
    return bool(project.master_profile and project.master_profile.project_manager_id == user_id)


def visible_project_ids(db: Session, *, actor: User, role: str) -> set[int]:
    """Same visibility contract as ``workflow_service.ortho_dashboard``."""
    project_ids: set[int] = set()
    if is_technical_pm_role(role):
        project_ids.update(int(v) for v in db.scalars(select(FinanceProjectMasterProfile.project_id).where(
            FinanceProjectMasterProfile.project_manager_id == actor.id,
        )).all())
    if role == EMPLOYEE_ROLE:
        project_ids.update(int(v) for v in db.scalars(select(OrthoProjectMember.project_id).where(
            OrthoProjectMember.user_id == actor.id,
            OrthoProjectMember.member_role.in_(["team_leader", "production", "qc", "qa"]),
            OrthoProjectMember.is_active.is_(True),
        )).all())
        from app.core.department_access import user_department_code
        employee_department = user_department_code(db, actor)
        if employee_department is not None:
            department_projects = set(db.scalars(select(ProjectWorkflow.project_id).where(
                ProjectWorkflow.performing_department_code == normalize_department_code_or_default(employee_department),
            )).all())
            project_ids &= department_projects
    if role in {ADMIN_ROLE, MANAGEMENT_ROLE}:
        project_ids.update(int(v) for v in db.scalars(select(ProjectWorkflow.project_id)).all())
    return set(filter_visible_project_ids(db, project_ids))


def _package_full(db: Session, work_package_id: int) -> OrthoWorkPackage:
    package = db.scalar(
        select(OrthoWorkPackage)
        .options(
            selectinload(OrthoWorkPackage.daily_updates),
            selectinload(OrthoWorkPackage.reviews),
            selectinload(OrthoWorkPackage.sessions),
        )
        .where(OrthoWorkPackage.id == work_package_id)
    )
    if package is None:
        raise ValueError("Work package not found")
    return package


def _department_of(db: Session, project_id: int) -> str:
    code = db.scalar(select(ProjectWorkflow.performing_department_code).where(ProjectWorkflow.project_id == project_id))
    return normalize_department_code_or_default(code)


def _ensure_actor_on_package(db: Session, package: OrthoWorkPackage, actor: User, *, allow_dxf_user: bool = False) -> str:
    """Return the actor's package role and raise PermissionError when the actor may not act.

    Trackable-stage updates are limited to the people already responsible for the
    package: the project's PM, the Team Lead, the Production assignee and (for DXF)
    the assigned DXF user. No new permission surface is invented.
    """
    project = db.get(FinanceProject, package.project_id)
    if project is None:
        raise ValueError("Project not found")
    if _is_pm_for_project(project, actor.id):
        return "project_manager"
    if package.team_leader_user_id == actor.id:
        return "team_leader"
    if package.production_user_id == actor.id:
        return "production"
    if allow_dxf_user and package.dxf_user_id is not None and package.dxf_user_id == actor.id:
        return "dxf"
    raise PermissionError("Only the Project Manager, Team Lead or assigned Production employee can update this stage")


def update_trackable_stage(
    db: Session,
    *,
    actor: User,
    work_package_id: int,
    stage: str,
    status_value: str,
    remarks: str | None = None,
    dxf_user_id: int | None = None,
) -> OrthoWorkPackage:
    """Append-only stage update for Import / DXF / Inspection / Upload.

    Validates the stage against the package's department profile and the status
    against that stage's vocabulary, records who/when/old/new/remarks in
    ``OrthoStageEvent``, and updates only the additive current-state columns.
    Production / QC / QA / Delivery are NOT handled here.
    """
    stage = (stage or "").strip().lower()
    if stage not in TRACKABLE_STAGES:
        raise ValueError(f"Stage must be one of: {', '.join(TRACKABLE_STAGES)}")
    package = _package_full(db, work_package_id)
    department_code = _department_of(db, package.project_id)
    if stage not in stage_profile_for_department(department_code):
        raise ValueError(f"The {STAGE_LABELS.get(stage, stage)} stage does not apply to this project's department")
    allowed_statuses = STAGE_STATUSES[stage]
    status_value = (status_value or "").strip().lower()
    if status_value not in allowed_statuses:
        raise ValueError(f"{STAGE_LABELS.get(stage, stage)} status must be one of: {', '.join(allowed_statuses)}")
    actor_role = _ensure_actor_on_package(db, package, actor, allow_dxf_user=stage == STAGE_DXF)

    from_status = getattr(package, STAGE_STATUS_ATTR[stage], None)
    event = OrthoStageEvent(
        work_package_id=package.id,
        project_id=package.project_id,
        stage_code=stage,
        from_status=from_status,
        to_status=status_value,
        actor_user_id=actor.id,
        actor_role=actor_role,
        remarks=(remarks or "").strip() or None,
        event_at=utc_now(),
    )

    if stage == STAGE_DXF and dxf_user_id is not None:
        member = db.scalar(select(OrthoProjectMember).where(
            OrthoProjectMember.project_id == package.project_id,
            OrthoProjectMember.user_id == dxf_user_id,
            OrthoProjectMember.is_active.is_(True),
        ).limit(1))
        if member is None:
            raise ValueError("DXF assignee must be a PM-approved member of this project team")
        assignee = db.get(User, dxf_user_id)
        if assignee is None or not assignee.is_active:
            raise ValueError("DXF assignee must be an active employee account")
        package.dxf_user_id = dxf_user_id

    setattr(package, STAGE_STATUS_ATTR[stage], status_value)
    setattr(package, STAGE_TIMESTAMP_ATTR[stage], utc_now())
    db.add(event)
    db.flush()
    return package


def update_package_general(
    db: Session,
    *,
    actor: User,
    work_package_id: int,
    lot_batch: str | None = None,
    supply_date=None,
    remarks: str | None = None,
) -> OrthoWorkPackage:
    """Team Lead / PM edits of the package's general context (Lot/Batch, Supply Date, Remarks).

    Assignees, quantity and unit are intentionally NOT editable here — quantity
    changes belong to the allocation/rework flows and unit changes would silently
    invalidate history, so neither is exposed.
    """
    package = _package_full(db, work_package_id)
    project = db.get(FinanceProject, package.project_id)
    if project is None:
        raise ValueError("Project not found")
    is_pm = _is_pm_for_project(project, actor.id)
    if not (is_pm or package.team_leader_user_id == actor.id):
        raise PermissionError("Only the Team Lead or Project Manager can update the package details")
    changes: dict[str, tuple[Any, Any]] = {}
    if lot_batch is not None:
        changes["lot_batch"] = (package.lot_batch, lot_batch.strip() or None)
    if supply_date is not None:
        changes["supply_date"] = (package.supply_date, supply_date)
    if remarks is not None:
        changes["remarks"] = (package.remarks, remarks.strip() or None)
    if not changes:
        return package
    event = OrthoStageEvent(
        work_package_id=package.id,
        project_id=package.project_id,
        stage_code="general",
        from_status=None,
        to_status="updated",
        actor_user_id=actor.id,
        actor_role="project_manager" if is_pm else "team_leader",
        remarks="; ".join(f"{name}: {old!r} -> {new!r}" for name, (old, new) in changes.items()),
        event_at=utc_now(),
    )
    for name, (_old, new) in changes.items():
        setattr(package, name, new)
    db.add(event)
    db.flush()
    return package


def package_stage_history(db: Session, *, actor: User, role: str, work_package_id: int) -> list[dict]:
    """Merged, chronological audit timeline for one work package.

    Sources (all append-only, none rewritten):
    1. ``OrthoDailyUpdate`` — daily production entries (user, date, quantity, unit,
       files, hours, status, blockers, remarks);
    2. ``OrthoReview`` — QC / QA attempts (reviewer, decision, comments);
    3. ``OrthoStageEvent`` — Import / DXF / Inspection / Upload / general updates
       (actor, role, old -> new status, remarks).

    Visibility matches the existing dashboard contract: PM / TL / admin / management
    see the full history; other participants see their own daily entries plus the
    package's review/stage events.
    """
    package = _package_full(db, work_package_id)
    project = db.get(FinanceProject, package.project_id)
    viewer_is_pm = bool(project and _is_pm_for_project(project, actor.id))
    viewer_is_tl = package.team_leader_user_id == actor.id
    privileged = viewer_is_pm or viewer_is_tl or role in {ADMIN_ROLE, MANAGEMENT_ROLE}
    if not privileged and actor.id not in {package.team_leader_user_id, package.production_user_id, package.qc_user_id, package.qa_user_id, package.dxf_user_id}:
        raise PermissionError("You are not assigned to this work package")

    known_ids = {row.updated_by_id for row in package.daily_updates if row.updated_by_id}
    known_ids |= {row.reviewer_user_id for row in package.reviews if row.reviewer_user_id}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(known_ids))).all()} if known_ids else {}

    def _user_name(user_id: int | None) -> str | None:
        user = users.get(user_id) if user_id else None
        return user.full_name if user else None

    unit = package.area_unit
    rows: list[dict] = []
    for update in package.daily_updates:
        if not privileged and update.updated_by_id != actor.id:
            continue
        rows.append({
            "kind": "daily_production", "stage": "production",
            "at": update.created_at.isoformat() if update.created_at else None,
            "date": update.update_date.isoformat() if update.update_date else None,
            "actor_user_id": update.updated_by_id, "actor_name": _user_name(update.updated_by_id),
            "from_status": None, "to_status": update.status,
            "quantity": float(update.achieved_area) if update.achieved_area is not None else None,
            "unit": unit, "files": int(update.files_completed or 0),
            "hours": float(update.hours_spent) if update.hours_spent is not None else None,
            "remarks": update.remarks, "blockers": update.blockers,
        })
    for review in package.reviews:
        rows.append({
            "kind": f"{review.review_type}_review", "stage": review.review_type,
            "at": review.created_at.isoformat() if review.created_at else None,
            "date": review.created_at.date().isoformat() if review.created_at else None,
            "actor_user_id": review.reviewer_user_id, "actor_name": _user_name(review.reviewer_user_id),
            "from_status": "pending", "to_status": review.decision,
            "quantity": None, "unit": None, "files": None, "hours": None,
            "remarks": review.comments, "blockers": None, "attempt_no": review.attempt_no,
        })
    stage_events = list(db.scalars(select(OrthoStageEvent).where(
        OrthoStageEvent.work_package_id == package.id,
    ).order_by(OrthoStageEvent.id.asc())).all())
    event_ids = {event.actor_user_id for event in stage_events if event.actor_user_id}
    if event_ids - set(users):
        users.update({u.id: u for u in db.scalars(select(User).where(User.id.in_(event_ids - set(users)))).all()})
    for event in stage_events:
        rows.append({
            "kind": "stage_event", "stage": event.stage_code,
            "at": event.event_at.isoformat() if event.event_at else None,
            "date": event.event_at.date().isoformat() if event.event_at else None,
            "actor_user_id": event.actor_user_id, "actor_name": _user_name(event.actor_user_id),
            "actor_role": event.actor_role,
            "from_status": event.from_status, "to_status": event.to_status,
            "quantity": float(event.quantity) if event.quantity is not None else None,
            "unit": event.unit, "files": None, "hours": None,
            "remarks": event.remarks, "blockers": None,
        })
    rows.sort(key=lambda row: row["at"] or "")
    return rows


def tracking_summary(db: Session, *, actor: User, role: str, project_id: int | None = None, authorized_bd_project_ids: set[int] | None = None) -> dict:
    """Server-side production-tracking summary for Team Lead / PM / Management dashboards.

    Aggregation happens here (never in the browser) and N+1 queries are avoided:
    packages are bulk-loaded per project with ``selectinload`` and users are
    fetched in one batch. Employees receive only their own package rows.
    """
    # BD may use only the IDs explicitly approved by the existing BD project
    # register, never IDs supplied directly by a browser/API query.
    if role == "bd":
        project_ids = set(authorized_bd_project_ids or ())
    else:
        project_ids = visible_project_ids(db, actor=actor, role=role)
    if project_id is not None:
        project_ids &= {project_id}
    if not project_ids:
        return {"projects": [], "units": known_units(), "viewer_mode": "read_only" if role in {ADMIN_ROLE, MANAGEMENT_ROLE, "bd"} else "participant"}

    projects = {p.id: p for p in db.scalars(select(FinanceProject).where(FinanceProject.id.in_(project_ids))).all()}
    workflows = {w.project_id: w for w in db.scalars(select(ProjectWorkflow).where(ProjectWorkflow.project_id.in_(project_ids))).all()}
    packages = list(db.scalars(
        select(OrthoWorkPackage)
        .options(selectinload(OrthoWorkPackage.daily_updates), selectinload(OrthoWorkPackage.reviews))
        .where(OrthoWorkPackage.project_id.in_(project_ids))
        .order_by(OrthoWorkPackage.id.asc())
    ).unique().all())

    pm_by_project = {
        row.project_id: row.project_manager_id
        for row in db.scalars(select(FinanceProjectMasterProfile).where(FinanceProjectMasterProfile.project_id.in_(project_ids))).all()
    }
    member_rows = list(db.scalars(select(OrthoProjectMember).where(
        OrthoProjectMember.project_id.in_(project_ids),
        OrthoProjectMember.is_active.is_(True),
    )).all())

    packages_by_project: dict[int, list[OrthoWorkPackage]] = {}
    for package in packages:
        packages_by_project.setdefault(package.project_id, []).append(package)

    person_ids = {pm_by_project.get(pid) for pid in project_ids} | {m.user_id for m in member_rows}
    person_ids |= {p.team_leader_user_id for p in packages if p.team_leader_user_id}
    person_ids = {pid for pid in person_ids if pid}
    people = {u.id: u for u in db.scalars(select(User).where(User.id.in_(person_ids))).all()} if person_ids else {}
    return _build_tracking_rows(db, actor, role, project_ids, projects, workflows, packages_by_project, pm_by_project, member_rows, people)


def _build_tracking_rows(db: Session, actor: User, role: str, project_ids, projects, workflows, packages_by_project, pm_by_project, member_rows, people) -> dict:
    viewer_is_employee = role == EMPLOYEE_ROLE
    rows: list[dict] = []
    for pid in sorted(project_ids):
        project = projects.get(pid)
        workflow = workflows.get(pid)
        if project is None or workflow is None:
            continue
        department = normalize_department_code_or_default(workflow.performing_department_code)
        project_packages = packages_by_project.get(pid, [])
        if viewer_is_employee:
            project_packages = [
                pkg for pkg in project_packages
                if actor.id in {pkg.team_leader_user_id, pkg.production_user_id, pkg.qc_user_id, pkg.qa_user_id, pkg.dxf_user_id}
            ]
        if not project_packages and viewer_is_employee:
            continue
        rows.append(_project_tracking_row(db, pid, project, workflow, project_packages, department, pm_by_project, member_rows, people))
    return {
        "projects": rows,
        "units": known_units(),
        "viewer_mode": "read_only" if role in {ADMIN_ROLE, MANAGEMENT_ROLE, "bd"} else ("project_manager" if is_technical_pm_role(role) else "participant"),
    }


def _project_tracking_row(db, pid, project, workflow, project_packages, department, pm_by_project, member_rows, people) -> dict:
    totals: dict[str, dict] = {}
    pending_counts: dict[str, int] = {stage: 0 for stage in stage_profile_for_department(department)}
    rework_count = 0
    blocked_count = 0
    stage_counts = {"production": 0, "qc": 0, "qa": 0, "delivery_ready": 0, "delivered": 0}
    employee_totals: dict[int, dict] = {}
    package_rows: list[dict] = []
    file_agg = file_aggregates_for_packages(db, [p.id for p in project_packages])
    # File-tracked areas: ONE source of truth — the item rollups (identical to /ortho).
    from app.modules.operations.production_items import item_dashboard_context
    item_contexts = item_dashboard_context(db, project_packages)
    for package in project_packages:
        ctx = item_contexts.get(package.id) or {}
        has_items = bool(ctx.get("has_items"))
        package_rows.append(_package_tracking_row(
            db, package, department, people,
            file_agg.get(package.id, {}),
            deadline_status(package, completed_at=package_completion_for_deadline(db, package)),
            ctx,
        ))
        total = Decimal(str(ctx.get("production_actual", 0.0))) if has_items \
            else sum((row.achieved_area or Decimal("0")) for row in package.daily_updates)
        target = package.area or Decimal("0")
        group = totals.setdefault(package.area_unit or "(none)", {
            "unit": package.area_unit, "planned": Decimal("0"), "completed": Decimal("0"), "packages": 0,
        })
        group["planned"] += target
        group["completed"] += total
        group["packages"] += 1
        for stage in effective_pending_stages(package, department, ctx):
            if stage in pending_counts:
                pending_counts[stage] += 1
        effective_stage = (ctx.get("stage_bucket") or package.current_stage) if has_items else package.current_stage
        if package.rework_cycle_id is not None and effective_stage != "delivered":
            rework_count += 1
        if any(row.status == "blocked" for row in package.daily_updates):
            blocked_count += 1
        stage = effective_stage
        if stage in {"not_started", "production", "production_rework"}:
            stage_counts["production"] += 1
        elif stage == "qc":
            stage_counts["qc"] += 1
        elif stage == "qa":
            stage_counts["qa"] += 1
        elif stage == "delivery_ready":
            stage_counts["delivery_ready"] += 1
        elif stage == "delivered":
            stage_counts["delivered"] += 1
        for uid in {package.team_leader_user_id, package.qc_user_id, package.qa_user_id, package.production_user_id}:
            if uid:
                employee_totals.setdefault(uid, {"user_id": uid, "packages": 0, "planned": Decimal("0"), "completed": Decimal("0")})["packages"] += 1
        if package.production_user_id:
            entry = employee_totals.setdefault(package.production_user_id, {"user_id": package.production_user_id, "packages": 0, "planned": Decimal("0"), "completed": Decimal("0")})
            entry["planned"] += target
            entry["completed"] += total

    progress = aggregate_project_progress(project_packages, department, item_contexts)
    pm = people.get(pm_by_project.get(pid) or 0)
    team_leaders = sorted({
        people[m.user_id].full_name
        for m in member_rows
        if m.project_id == pid and m.member_role == "team_leader" and m.user_id in people
    })
    return {
        "project_id": pid,
        "project_code": project.project_code,
        "department_code": department,
        "workflow_status": workflow.status,
        "project_manager": {"id": pm.id, "full_name": pm.full_name} if pm else None,
        "team_leaders": team_leaders,
        "packages": len(project_packages),
        "package_rows": package_rows,
        "planned_by_unit": [
            {"unit": data["unit"], "planned": float(data["planned"]), "completed": float(data["completed"]), "packages": data["packages"]}
            for data in totals.values()
        ],
        "production_progress_percent": progress["production_progress_percent"],
        "workflow_progress_percent": progress["workflow_progress_percent"],
        "measurement_groups": [
            {k: (float(v) if isinstance(v, Decimal) else v) for k, v in group.items()}
            for group in progress["measurement_groups"]
        ],
        "mixed_measurement_types": progress["mixed_measurement_types"],
        "weighting": progress["weighting"],
        "pending_stages": pending_counts,
        "stage_counts": stage_counts,
        "rework_packages": rework_count,
        "blocked_packages": blocked_count,
        "employees": [
            {
                "user_id": entry["user_id"],
                "full_name": people.get(entry["user_id"]).full_name if entry["user_id"] in people else None,
                "packages": entry["packages"],
                "planned": float(entry["planned"]),
                "completed": float(entry["completed"]),
            }
            for entry in sorted(employee_totals.values(), key=lambda row: row["user_id"])
        ],
    }


def _iso(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _last_review_of(package: OrthoWorkPackage, kind: str) -> Any:
    matching = [r for r in (package.reviews or []) if r.review_type == kind]
    if not matching:
        return None
    return max(matching, key=lambda r: (r.attempt_no or 0, r.created_at))


def _package_tracking_row(
    db,
    package: OrthoWorkPackage,
    department: str,
    people: dict[int, User],
    file_agg: dict,
    deadline: dict,
    item_ctx: dict | None = None,
) -> dict:
    """One Daily-Activity-style row per work package for the tracking table.

    Additive read model: mirrors the Excel ``production_detail`` sheet columns so
    the UI and the export always agree. Null legacy fields stay null (never
    crash, never coerce to fake values); progress figures come from the shared
    documented formulas (zero-target safe, over-target capped with variance).

    File-tracked areas (``item_ctx["has_items"]``) derive actual quantity, file
    counts, stage status and current stage from the SAME item rollups as /ortho.
    """
    item_ctx = item_ctx or {}
    has_items = bool(item_ctx.get("has_items"))
    if has_items:
        total = Decimal(str(item_ctx.get("production_actual", 0.0)))
        files = int(file_agg.get("files_production_done", 0))
    else:
        total = sum((row.achieved_area or Decimal("0")) for row in package.daily_updates)
        files = sum(int(row.files_completed or 0) for row in package.daily_updates)
    production = package_production_progress(total, package.area)
    qc_review = _last_review_of(package, "qc")
    qa_review = _last_review_of(package, "qa")
    stages = stage_profile_for_department(department)

    def name_of(user_id: int | None) -> str | None:
        if not user_id:
            return None
        person = people.get(user_id)
        return person.full_name if person else None

    def stage_display(stage: str) -> str | None:
        derived = item_stage_status(item_ctx, package, stage)
        return derived if derived is not None else stage_status(package, stage)

    # For file-tracked areas the authoritative timing/decision comes from the item rollups.
    item_rows = [row for row in item_ctx.get("rows", []) if row.get("is_active")] if has_items else []
    counts = item_ctx.get("aggregate", {}) if has_items else {}
    expected = int(counts.get("files_expected") or 0)
    production_date = None
    if has_items:
        dates = [row["production_completed_at"] for row in item_rows if row.get("production_completed_at")]
        production_date = max(dates) if dates else None
    qc_decision = qc_review.decision if qc_review is not None else None
    qa_decision = qa_review.decision if qa_review is not None else None
    if has_items and expected:
        if int(counts.get("files_qc_passed", 0)) >= expected:
            qc_decision = "approved"
        elif (item_ctx.get("stage_rework") or {}).get("qc"):
            qc_decision = "rejected"
        elif (item_ctx.get("stage_started") or {}).get("qc"):
            qc_decision = "pending"
        if int(counts.get("files_qa_passed", 0)) >= expected:
            qa_decision = "approved"
        elif (item_ctx.get("stage_rework") or {}).get("qa"):
            qa_decision = "rejected"
        elif (item_ctx.get("stage_started") or {}).get("qa"):
            qa_decision = "pending"

    return {
        "work_package_id": package.id,
        "lot_batch": package.lot_batch,
        "package_code": package.package_code,
        "area_name": package.package_name,
        "target_quantity": float(package.area) if package.area is not None else None,
        "unit": package.area_unit,
        "actual_quantity": float(total),
        "files": files,
        "production_progress_percent": production["progress_percent"],
        "over_target_quantity": float(production["over_target_quantity"]),
        "workflow_progress_percent": package_workflow_progress(package, department, item_ctx),
        "applicable_stages": list(stages),
        "stage_statuses": {stage: stage_display(stage) for stage in stages},
        "pending_stages": effective_pending_stages(package, department, item_ctx),
        "current_stage": (item_ctx.get("stage_bucket") or package.current_stage) if has_items else package.current_stage,
        "production_state": package.production_state,
        "qc_state": package.qc_state,
        "qa_state": package.qa_state,
        "stage_dates": {
            "supply": _iso(package.supply_date),
            "import": _iso(package.imported_at),
            "production": production_date or _iso(package.production_completed_at),
            "qc": _iso(qc_review.created_at) if qc_review is not None else _iso(package.qc_submitted_at),
            "qa": _iso(qa_review.created_at) if qa_review is not None else _iso(package.qa_submitted_at),
            "dxf": _iso(package.dxf_at),
            "inspection": _iso(package.inspected_at),
            "delivery": _iso(package.delivered_at),
            "upload": _iso(package.uploaded_at),
        },
        "qc_decision": qc_decision,
        "qa_decision": qa_decision,
        "team_leader": name_of(package.team_leader_user_id),
        "production_user": name_of(package.production_user_id),
        "qc_user": name_of(package.qc_user_id),
        "qa_user": name_of(package.qa_user_id),
        "dxf_user": name_of(package.dxf_user_id),
        "rework": package.rework_cycle_id is not None,
        "rework_cycle_id": package.rework_cycle_id,
        "target_date": _iso(package.target_date),
        "production_target_date": _iso(package.production_target_date),
        "buffer": deadline,
        "files_expected": file_agg.get("files_expected", 0),
        "files_production_done": file_agg.get("files_production_done", 0),
        "files_qc_passed": file_agg.get("files_qc_passed", 0),
        "files_qa_passed": file_agg.get("files_qa_passed", 0),
        "files_delivered": file_agg.get("files_delivered", 0),
        # V8.4 physical-file counters (distinct files; rework never inflates these).
        "declared_total_files": package.total_files,
        "files_active": file_agg.get("files_expected", 0),
        "files_assigned": file_agg.get("files_assigned", 0),
        "files_available": file_agg.get("files_available", 0),
        "files_production_in_progress": file_agg.get("production_in_progress", 0),
        "files_production_rework": file_agg.get("production_rework", 0),
        "files_qc_in_progress": file_agg.get("qc_in_progress", 0),
        "files_qc_rework": file_agg.get("qc_rework", 0),
        "files_qa_in_progress": file_agg.get("qa_in_progress", 0),
        "files_qa_rework": file_agg.get("qa_rework", 0),
        "files_ready": file_agg.get("ready", 0),
        "file_production_percent": file_agg.get("production_item_percent", 0.0),
        "file_qc_percent": file_agg.get("qc_item_percent", 0.0),
        "file_qa_percent": file_agg.get("qa_item_percent", 0.0),
        "file_delivery_percent": file_agg.get("delivery_item_percent", 0.0),
        "remarks": package.remarks,
        "instructions": package.instructions,
    }






