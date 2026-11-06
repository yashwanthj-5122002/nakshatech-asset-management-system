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


def send_files_to_rework(
    db: Session, *, actor: User, package_id: int, stage: str,
    item_ids: list[int], reason: str,
) -> dict:
    """Return multiple selected files to Production in ONE database transaction.

    Preflight every selected file before touching any file, then delegate each
    decision to the EXISTING single-file implementation so its append-only audit,
    Production notifications, timing, and QC/QA gates are preserved unchanged.
    The API caller must roll back the whole transaction on any failure.
    """
    if not item_ids or len(item_ids) > 128:
        raise ValueError("Select between 1 and 128 files for rework")
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("The same file was selected more than once")
    cleaned_reason = reason.strip()
    if len(cleaned_reason) < 3 or len(cleaned_reason) > 2000:
        raise ValueError("Enter a rework reason between 3 and 2000 characters")

    package, owned = _assigned_items(db, actor=actor, package_id=package_id, stage=stage)
    owned_by_id = {item.id: item for item in owned}
    selected = [owned_by_id.get(item_id) for item_id in item_ids]
    if any(item is None for item in selected):
        raise PermissionError("One or more files are inactive, outside this block, or not assigned to you")
    if package.ready_for_delivery_at is not None:
        raise ValueError("Delivery was already confirmed for this block; rework is locked")

    latest = _latest(db, package_id)
    sessions = {
        row.work_package_item_id: row
        for row in _open_owned_sessions(db, actor=actor, package_id=package_id,
                                        stage=stage, owned=owned)
    }
    invalid = []
    for item in selected:
        stages = latest.get(item.id, {})
        production = stages.get("production")
        if (item.status == "delivered" or stages.get("delivery") is not None
                or production is None or production.status != "completed"):
            invalid.append(item.item_number)
            continue
        if item.id in sessions:
            # The original single-file endpoint permits rejecting an active
            # review owned by the current reviewer.
            continue
        if not _may_rework_passed(package=package, stage=stage, stages=stages):
            invalid.append(item.item_number)
    if invalid:
        preview = ", ".join(invalid[:5])
        if len(invalid) > 5:
            preview += f" and {len(invalid) - 5} more"
        raise ValueError(f"These files are not eligible for {stage.upper()} rework: {preview}. Refresh and try again")

    # Predictable lock/order. All of these run inside the route's ONE
    # transaction; a failure rolls back all activities and notifications.
    results = [
        send_file_to_rework(
            db, actor=actor, package_id=package_id, stage=stage,
            item_id=item_id, reason=cleaned_reason,
        )
        for item_id in sorted(item_ids)
    ]
    return {
        "stage": stage, "count": len(results),
        "item_ids": [row["item_id"] for row in results],
        "activity_ids": [row["activity_id"] for row in results],
    }


# V2: source-scoped CLD import review controls across multiple work packages.
# Every CLD import row is intentionally a distinct package. The pre-existing
# package-level review and per-file stage controls above remain unchanged.
def _cld_source_items(
    db: Session, *, actor: User, project_id: int, stage: str,
    item_ids: list[int], require_entire_source: bool,
) -> list[WorkPackageItem]:
    if stage not in REVIEW_STAGES:
        raise ValueError("Only QC and QA are supported")
    if not item_ids or len(item_ids) > 512 or len(set(item_ids)) != len(item_ids):
        raise ValueError("Choose 1 to 512 distinct files in one CLD assignment block")

    stage_col = WorkPackageItem.qc_user_id if stage == "qc" else WorkPackageItem.qa_user_id
    # Query only the current reviewer's project-scoped CLD files. Never trust a
    # client-supplied package/source name to authorize other people's work.
    rows = list(db.scalars(
        select(WorkPackageItem).join(
            OrthoWorkPackage, OrthoWorkPackage.id == WorkPackageItem.work_package_id
        ).where(
            WorkPackageItem.project_id == project_id,
            WorkPackageItem.is_active.is_(True),
            stage_col == actor.id,
            OrthoWorkPackage.project_id == project_id,
            OrthoWorkPackage.lot_batch == "CLD_IMPORT",
            OrthoWorkPackage.rework_cycle_id.is_(None),
            OrthoWorkPackage.package_code.startswith("CENTRELINE_M_"),
        ).order_by(WorkPackageItem.id).with_for_update()
    ).all())
    indexed = {row.id: row for row in rows}
    if any(item_id not in indexed for item_id in item_ids):
        raise PermissionError("One or more files are not in your active CLD review assignment")
    selected = [indexed[item_id] for item_id in item_ids]
    source = selected[0].import_source
    if any(item.import_source != source for item in selected):
        raise ValueError("Files from different CLD source imports cannot be combined")
    in_block = [item for item in rows if item.import_source == source]
    if require_entire_source and {item.id for item in in_block} != set(item_ids):
        raise ValueError("The CLD assignment has changed. Refresh before running Start All or Complete All")
    return selected


def cld_source_review(
    db: Session, *, actor: User, role: str, project_id: int,
    stage: str, action: str, item_ids: list[int], reason: str | None = None,
) -> dict:
    """Perform source-grouped QC/QA actions atomically across CLD work packages.

    API caller owns ONE commit/rollback. The individual-file controls are not
    involved or changed; activities use the existing authoritative services.
    """
    if action not in {"start", "complete", "rework"}:
        raise ValueError("Unsupported CLD review action")
    selected = _cld_source_items(
        db, actor=actor, project_id=project_id, stage=stage,
        item_ids=item_ids, require_entire_source=action != "rework",
    )
    package_ids = sorted({item.work_package_id for item in selected})
    # Lock all packages in a stable order before changing any activity.
    packages = {
        package.id: package for package in db.scalars(
            select(OrthoWorkPackage).where(
                OrthoWorkPackage.id.in_(package_ids),
                OrthoWorkPackage.project_id == project_id,
            ).order_by(OrthoWorkPackage.id).with_for_update()
        ).all()
    }
    if len(packages) != len(package_ids):
        raise ValueError("The CLD assignment packages have changed; refresh and retry")
    results: list[dict] = []

    if action == "start":
        latest_by_pkg = {
            pkg_id: production_items.latest_activities_by_item(db, [pkg_id])
            for pkg_id in package_ids
        }
        candidates = [item for item in selected if _may_start(
            stage, latest_by_pkg[item.work_package_id].get(item.id, {})
        )]
        if not candidates:
            raise ValueError(f"No files in this block are ready to start {stage.upper()}")
        for item in candidates:
            activity = production_items.start_activity(
                db, actor=actor, role=role,
                work_package_item_id=item.id, stage=stage,
            )
            results.append({"item_id": item.id, "activity_id": activity.id})

    elif action == "complete":
        sessions = list(db.scalars(
            select(WorkPackageItemActivity).where(
                WorkPackageItemActivity.work_package_item_id.in_(item_ids),
                WorkPackageItemActivity.project_id == project_id,
                WorkPackageItemActivity.stage == stage,
                WorkPackageItemActivity.employee_user_id == actor.id,
                WorkPackageItemActivity.ended_at.is_(None),
            ).order_by(WorkPackageItemActivity.id).with_for_update()
        ).all())
        if not sessions:
            raise ValueError(f"Start {stage.upper()} on this block before completing it")
        session_ids = {session.work_package_item_id for session in sessions}
        latest_by_pkg = {
            pkg_id: production_items.latest_activities_by_item(db, [pkg_id])
            for pkg_id in package_ids
        }
        pending = [item.item_number for item in selected if item.id not in session_ids and (
            latest_by_pkg[item.work_package_id].get(item.id, {}).get(stage) is None
            or latest_by_pkg[item.work_package_id][item.id][stage].status != "passed"
        )]
        if pending:
            raise ValueError(
                f"Cannot complete the entire block: {len(pending)} file(s) have not started, "
                "need rework, or are not yet eligible. Use Start All after they are ready."
            )
        for session in sessions:
            row = production_items.stop_activity(
                db, actor=actor, activity_id=session.id, status="passed"
            )
            results.append({"item_id": row.work_package_item_id, "activity_id": row.id})

    else:  # selective rework; every per-package operation uses existing V1 service
        cleaned_reason = (reason or "").strip()
        if not 3 <= len(cleaned_reason) <= 2000:
            raise ValueError("A Production rework reason of 3 to 2000 characters is required")
        # Use the original validated file-level rejection path and its native
        # Production notification logic; any later error rolls back all files.
        for pkg_id in package_ids:
            current_ids = sorted(
                item.id for item in selected if item.work_package_id == pkg_id
            )
            changed = send_files_to_rework(
                db, actor=actor, package_id=pkg_id, stage=stage,
                item_ids=current_ids, reason=cleaned_reason,
            )
            results.extend(
                {"item_id": item_id, "activity_id": activity_id}
                for item_id, activity_id in zip(
                    changed["item_ids"], changed["activity_ids"]
                )
            )
    db.flush()
    return {
        "stage": stage, "action": action, "count": len(results),
        "item_ids": [entry["item_id"] for entry in results],
        "activity_ids": [entry["activity_id"] for entry in results],
    }
