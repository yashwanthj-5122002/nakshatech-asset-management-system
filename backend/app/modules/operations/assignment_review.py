"""Assignment-level QC/QA controls using the existing append-only file activities.

One button press can start or finish several file activities in one transaction.
The existing per-file Production workflow, schemas and tables remain untouched.
Callers own the transaction and must commit only after the entire operation succeeds.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.operations import production_items
from app.modules.operations.models import OrthoWorkPackage, WorkPackageItem, WorkPackageItemActivity

REVIEW_STAGES = frozenset({"qc", "qa"})
REJECTED_STATUSES = frozenset({"rejected", "rework"})


def _assigned_items(db: Session, *, actor: User, package_id: int, stage: str) -> tuple[OrthoWorkPackage, list[WorkPackageItem]]:
    if stage not in REVIEW_STAGES:
        raise ValueError("Only QC and QA are supported by assignment review controls")
    # Serialize concurrent assignment-level start/complete/rework operations.
    package = db.scalar(select(OrthoWorkPackage).where(OrthoWorkPackage.id == package_id).with_for_update())
    if package is None:
        raise ValueError("Work package not found")
    stage_col = WorkPackageItem.qc_user_id if stage == "qc" else WorkPackageItem.qa_user_id
    rows = list(db.scalars(
        select(WorkPackageItem).where(
            WorkPackageItem.work_package_id == package_id,
            stage_col == actor.id,
            WorkPackageItem.is_active.is_(True),
        ).order_by(WorkPackageItem.id).with_for_update()
    ).all())
    if not rows:
        raise PermissionError(f"Only a {stage.upper()} employee assigned to this area may perform this action")
    return package, rows


def _latest(db: Session, package_id: int):
    return production_items.latest_activities_by_item(db, [package_id])


def _may_start(stage: str, stages: dict[str, WorkPackageItemActivity]) -> bool:
    production = stages.get("production")
    if production is None or production.status != "completed":
        return False
    if stage == "qa":
        qc = stages.get("qc")
        if qc is None or qc.status != "passed":
            return False
    current = stages.get(stage)
    if current is None:
        return True
    if current.status in {"passed", "in_progress"} or current.ended_at is None:
        return False
    if current.status in REJECTED_STATUSES:
        # File rejected by QC/QA must be corrected by Production first.
        # Do not let a reviewer retry on the stale pre-rework file.
        return bool(production.ended_at and current.ended_at and production.ended_at > current.ended_at)
    return True


def start_review(db: Session, *, actor: User, role: str, package_id: int, stage: str) -> dict:
    _, owned = _assigned_items(db, actor=actor, package_id=package_id, stage=stage)
    latest = _latest(db, package_id)
    candidates = [item for item in owned if _may_start(stage, latest.get(item.id, {}))]
    if not candidates:
        raise ValueError(f"No eligible files are ready to start {stage.upper()} for this assignment")
    started = []
    for item in candidates:
        activity = production_items.start_activity(
            db, actor=actor, role=role, work_package_item_id=item.id, stage=stage
        )
        started.append({"item_id": item.id, "activity_id": activity.id})
    db.flush()
    return {"stage": stage, "started": started, "count": len(started)}


def _open_owned_sessions(
    db: Session, *, actor: User, package_id: int, stage: str, owned: list[WorkPackageItem]
) -> list[WorkPackageItemActivity]:
    item_ids = [item.id for item in owned]
    return list(db.scalars(
        select(WorkPackageItemActivity).where(
            WorkPackageItemActivity.work_package_id == package_id,
            WorkPackageItemActivity.work_package_item_id.in_(item_ids),
            WorkPackageItemActivity.employee_user_id == actor.id,
            WorkPackageItemActivity.stage == stage,
            WorkPackageItemActivity.ended_at.is_(None),
        ).order_by(WorkPackageItemActivity.id).with_for_update()
    ).all())


def complete_review(db: Session, *, actor: User, package_id: int, stage: str) -> dict:
    _, owned = _assigned_items(db, actor=actor, package_id=package_id, stage=stage)
    sessions = _open_owned_sessions(db, actor=actor, package_id=package_id, stage=stage, owned=owned)
    if not sessions:
        raise ValueError(f"Start {stage.upper()} before completing the assignment")
    completed = []
    for session in sessions:
        row = production_items.stop_activity(db, actor=actor, activity_id=session.id, status="passed")
        completed.append({"item_id": row.work_package_item_id, "activity_id": row.id})
    db.flush()
    return {"stage": stage, "completed": completed, "count": len(completed)}


def _may_rework_passed(
    *, package: OrthoWorkPackage, stage: str, stages: dict[str, WorkPackageItemActivity]
) -> bool:
    """A completed review may be rejected only before its downstream handoff.

    Never reopen delivered or delivery-confirmed work, and never invalidate QC
    while QA has already begun. The current review must be a completed PASS.
    """
    current = stages.get(stage)
    if current is None or current.status != "passed" or current.ended_at is None:
        return False
    production = stages.get("production")
    if production is None or production.status != "completed":
        return False
    if stages.get("delivery") is not None:
        return False
    if package.ready_for_delivery_at is not None:
        return False
    if stage == "qc" and stages.get("qa") is not None:
        return False
    if stage == "qa":
        qc = stages.get("qc")
        if qc is None or qc.status != "passed":
            return False
    return True


def send_file_to_rework(
    db: Session, *, actor: User, package_id: int, stage: str, item_id: int, reason: str
) -> dict:
    package, owned = _assigned_items(db, actor=actor, package_id=package_id, stage=stage)
    selected_item = next((item for item in owned if item.id == item_id), None)
    if selected_item is None:
        raise PermissionError("This file is not assigned to you for this review stage")
    reason = reason.strip()
    if len(reason) < 3:
        raise ValueError("A rework reason of at least 3 characters is required")

    # Previously started and not yet completed: use the normal review rejection
    # path and preserve its actual session start/end/duration.
    sessions = _open_owned_sessions(db, actor=actor, package_id=package_id, stage=stage, owned=owned)
    session = next((row for row in sessions if row.work_package_item_id == item_id), None)
    if session is not None:
        row = production_items.stop_activity(
            db, actor=actor, activity_id=session.id, status="rework", remarks=reason
        )
    else:
        # Rework is also allowed AFTER the reviewer clicked Complete, if QA
        # has not begun (QC) or delivery has not been confirmed (QA).
        # Do not mutate the historical PASS; append a new audit activity.
        latest = _latest(db, package_id)
        stages = latest.get(item_id, {})
        if not _may_rework_passed(package=package, stage=stage, stages=stages):
            raise ValueError(
                "This file cannot be sent for rework now. Start review first, "
                "or check whether it has advanced to QA/delivery or was already returned."
            )
        open_any_stage = db.scalar(select(WorkPackageItemActivity.id).where(
            WorkPackageItemActivity.work_package_item_id == item_id,
            WorkPackageItemActivity.ended_at.is_(None),
        ).limit(1))
        if open_any_stage is not None:
            raise ValueError("The file has an active work session; it cannot be sent for rework")

        existing = stages[stage]
        now = production_items.utc_now()
        # A zero-second, server-timed rework decision. End > start is required
        # by the shared stop_activity implementation; no time is back-billed.
        decision = WorkPackageItemActivity(
            project_id=package.project_id,
            work_package_id=package.id,
            work_package_item_id=item_id,
            stage=stage,
            employee_user_id=actor.id,
            performed_role=stage,
            from_status=selected_item.status,
            started_at=now - timedelta(microseconds=1),
            status="in_progress",
            files_completed=0,
            attempt_type="REWORK",
            attempt_number=int(existing.attempt_number or 1) + 1,
        )
        db.add(decision)
        db.flush()
        row = production_items.stop_activity(
            db, actor=actor, activity_id=decision.id,
            status="rework", remarks=reason, ended_at=now,
        )
    db.flush()
    return {"stage": stage, "item_id": row.work_package_item_id,
            "activity_id": row.id, "status": row.status}
