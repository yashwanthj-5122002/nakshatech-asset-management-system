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
