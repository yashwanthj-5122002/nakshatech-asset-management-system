"""Additional CLD-import TL/PM bulk Ready for Delivery workflow.

One source-scoped click delegates to the EXISTING single-package delivery
readiness operation. The router owns the transaction; no package is committed
until all requested packages have succeeded. No actual delivery occurs here.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import User
from app.modules.operations import production_items
from app.modules.operations.models import OrthoWorkPackage, WorkPackageItem


def _is_eligible(db: Session, package: OrthoWorkPackage, item: WorkPackageItem) -> bool:
    if package.ready_for_delivery_at is not None or package.delivered_at is not None:
        return False
    if item.status == production_items.ITEM_STATUS_DELIVERED:
        return False
    return production_items.delivery_readiness(db, package)["ready"]


def mark_cld_group_ready(
    db: Session, *, actor: User, role: str, project_id: int, item_ids: list[int]
) -> dict:
    """Mark ALL currently eligible files for one import source ready, atomically.

    Each CLD import file is a separate package. Server-side scope is based on
    authoritative project, package, source and TL/PM authorization, not a
    client-supplied package list or trusted UI count.
    """
    if not item_ids or len(item_ids) > 512 or len(set(item_ids)) != len(item_ids):
        raise ValueError("Select between 1 and 512 distinct CLD files")

    packages = list(db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.project_id == project_id,
        OrthoWorkPackage.lot_batch == "CLD_IMPORT",
        OrthoWorkPackage.rework_cycle_id.is_(None),
    ).order_by(OrthoWorkPackage.id).with_for_update()).all())
    packages = [p for p in packages if p.package_code.startswith("CENTRELINE_M_")]
    if not packages:
        raise ValueError("No CLD import assignments exist in this project")

    by_package = {p.id: p for p in packages}
    rows = list(db.scalars(select(WorkPackageItem).where(
        WorkPackageItem.project_id == project_id,
        WorkPackageItem.work_package_id.in_(sorted(by_package)),
        WorkPackageItem.is_active.is_(True),
    ).order_by(WorkPackageItem.id).with_for_update()).all())
    by_id = {item.id: item for item in rows}
    selected = [by_id.get(item_id) for item_id in item_ids]
    if any(item is None for item in selected):
        raise PermissionError("One or more files are outside the CLD project assignment")

    source = selected[0].import_source
    if not source or any(item.import_source != source for item in selected):
        raise ValueError("Bulk confirmation requires files from one identified CLD import source")

    same_source = [item for item in rows if item.import_source == source]
    candidate_by_package: dict[int, WorkPackageItem] = {}
    for item in same_source:
        package = by_package[item.work_package_id]
        ctx = production_items.actor_context(db, package, actor, role)
        if ctx["read_only_role"] or not (ctx["is_tl"] or ctx["is_pm"]):
            continue
        if _is_eligible(db, package, item):
            candidate_by_package[package.id] = item

    eligible_ids = {item.id for item in candidate_by_package.values()}
    if set(item_ids) != eligible_ids:
        raise ValueError(
            "The eligible file list changed or contains unauthorized/unready files. "
            "Refresh the TL page and retry."
        )
    if not candidate_by_package:
        raise ValueError("No QA-passed files are waiting for Ready for Delivery confirmation")

    confirmed_packages = []
    for package_id in sorted(candidate_by_package):
        # Reuse all original stage checks, TL/PM authorization, timestamps and
        # PM notifications; any exception rolls back every package in router.
        result = production_items.mark_ready_for_delivery(
            db, actor=actor, role=role, work_package_id=package_id
        )
        if not result["confirmed"]:
            raise ValueError("Delivery readiness was not saved for a selected file")
        confirmed_packages.append(package_id)
    db.flush()
    return {
        "count": len(candidate_by_package),
        "item_ids": sorted(eligible_ids),
        "package_ids": confirmed_packages,
        "source": source,
    }


# One authenticated TL/PM operation for *final* delivery of a CLD import source.
# Reuses the original per-work-package mark_delivered() for identical checks,
# delivery activities, timestamps, notifications and rework-cycle synchronization.
def mark_cld_group_delivered(
    db: Session, *, actor: User, role: str, project_id: int,
    item_ids: list[int], remarks: str | None = None,
) -> dict:
    """Deliver exactly the eligible ready-confirmed, undelivered files in one source.

    The router commits once, after every package has been processed. Invalid,
    stale, cross-project, mixed-source and unauthorized selections change nothing.
    """
    if not item_ids or len(item_ids) > 512 or len(set(item_ids)) != len(item_ids):
        raise ValueError("Select between 1 and 512 distinct CLD files")

    packages = list(db.scalars(select(OrthoWorkPackage).where(
        OrthoWorkPackage.project_id == project_id,
        OrthoWorkPackage.lot_batch == "CLD_IMPORT",
        OrthoWorkPackage.rework_cycle_id.is_(None),
    ).order_by(OrthoWorkPackage.id).with_for_update()).all())
    packages = [p for p in packages if p.package_code.startswith("CENTRELINE_M_")]
    if not packages:
        raise ValueError("No CLD import assignments exist in this project")
    by_package = {p.id: p for p in packages}
    rows = list(db.scalars(select(WorkPackageItem).where(
        WorkPackageItem.project_id == project_id,
        WorkPackageItem.work_package_id.in_(sorted(by_package)),
        WorkPackageItem.is_active.is_(True),
    ).order_by(WorkPackageItem.id).with_for_update()).all())
    by_id = {item.id: item for item in rows}
    selected = [by_id.get(item_id) for item_id in item_ids]
    if any(item is None for item in selected):
        raise PermissionError("One or more files are outside the CLD project assignment")
    source = selected[0].import_source
    if not source or any(item.import_source != source for item in selected):
        raise ValueError("Bulk delivery requires files from one identified CLD import source")

    source_items = [item for item in rows if item.import_source == source]
    # mark_delivered operates on the entire package; never include a package
    # containing active files from a different imported source.
    source_package_ids = {item.work_package_id for item in source_items}
    if any(item.import_source != source for item in rows
           if item.work_package_id in source_package_ids):
        raise ValueError("A CLD package contains files from different import sources")
    items_by_package: dict[int, list[WorkPackageItem]] = {}
    for item in source_items:
        items_by_package.setdefault(item.work_package_id, []).append(item)
    latest = production_items.latest_activities_by_item(db, list(items_by_package))
    candidates: dict[int, list[WorkPackageItem]] = {}
    for package_id, group in items_by_package.items():
        package = by_package[package_id]
        ctx = production_items.actor_context(db, package, actor, role)
        # Match the existing final-delivery permission, not merely project-wide TL membership.
        if ctx["read_only_role"] or not (ctx["is_pm"] or package.team_leader_user_id == actor.id):
            continue
        if package.ready_for_delivery_at is None or package.delivered_at is not None or package.current_stage == "delivered":
            continue
        readiness = production_items.delivery_readiness(db, package, items=group, latest=latest)
        if not readiness["ready"]:
            continue
        pending = [item for item in group if (
            item.status != production_items.ITEM_STATUS_DELIVERED
            and (latest.get(item.id, {}).get("delivery") is None
                 or latest[item.id]["delivery"].status != "delivered")
        )]
        if pending:
            candidates[package_id] = pending

    eligible_ids = {item.id for group in candidates.values() for item in group}
    if not eligible_ids:
        raise ValueError("No ready-confirmed files are waiting for final delivery")
    if set(item_ids) != eligible_ids:
        raise ValueError(
            "The eligible delivery list changed or contains unauthorized/unready files. "
            "Refresh the TL/PM page and retry."
        )

    from app.modules.operations.schemas import WorkflowDeliveryRequest
    from app.modules.operations.workflow_service import mark_delivered
    delivered_packages = []
    for package_id in sorted(candidates):
        result = mark_delivered(
            db, actor=actor, work_package_id=package_id,
            payload=WorkflowDeliveryRequest(remarks=remarks),
        )
        if result.current_stage != "delivered" or result.delivered_at is None:
            raise ValueError("Final delivery was not recorded for a selected package")
        delivered_packages.append(package_id)
    db.flush()
    return {
        "count": len(eligible_ids),
        "item_ids": sorted(eligible_ids),
        "package_ids": delivered_packages,
        "source": source,
    }
