from __future__ import annotations

"""Remove only known Batch 3 / Batch 4 QA records from the configured database.

This utility exists to clean records that may have been written before the
backend pytest harness forced an isolated temporary database at collection time.
It is intentionally narrow and defaults to dry-run. Use ``--apply`` only after
reviewing the printed exact IDs/codes.
"""

import argparse
from collections import defaultdict

from sqlalchemy import or_, select

from app.core.database import SessionLocal
from app.models.entities import (
    ApprovalDecisionHistory,
    Asset,
    AssetHistory,
    ComponentReplacement,
    ReplacementRecord,
    User,
    WorkRecord,
)
from app.modules.batch3.models import ReplacementWorkflowState
from app.modules.it_activity.models import (
    ITHandoverRecord,
    ITPurchaseRecord,
    ITPurchaseRequest,
    ITPurchaseRequestHistory,
)
from app.modules.notifications.models import GlobalNotification


TEST_USER_EMAILS = {
    "batch3-it@nakshatech.com",
    "batch3-manager@nakshatech.com",
    "batch4-it@nakshatech.com",
    "batch4-manager@nakshatech.com",
}

TEST_ASSET_CODES = {
    "B3-OLD-LAP",
    "B3-SPARE-LAP",
    "B3-OLD-MOB",
    "B3-NEW-MOB",
    "B4-CUSTODY-001",
    "B4-WORK-001",
    "B4-OLD-LAP",
    "B4-SPARE-LAP",
    "B4-OLD-PRN",
    "B4-SPARE-PRN",
    "B4-OLD-MOB",
    "B4-NEW-MOB",
}

TEST_REPLACEMENT_CODES = {
    "B3-RPL-SPARE",
    "B3-RPL-PURCHASE",
    "RPL-B4-LEGACY",
}

TEST_WORK_CODES = {"ITW-B4-001"}


def _ids(rows):
    return {row.id for row in rows}


def _codes(rows, attr: str):
    return sorted(str(getattr(row, attr)) for row in rows)


def collect_artifacts(db):
    users = list(db.scalars(select(User).where(User.email.in_(TEST_USER_EMAILS))).all())
    user_ids = _ids(users)

    assets = list(db.scalars(select(Asset).where(Asset.asset_code.in_(TEST_ASSET_CODES))).all())
    asset_ids = _ids(assets)

    replacement_conditions = [ReplacementRecord.replacement_code.in_(TEST_REPLACEMENT_CODES)]
    if asset_ids:
        replacement_conditions.extend([
            ReplacementRecord.old_asset_id.in_(asset_ids),
            ReplacementRecord.new_asset_id.in_(asset_ids),
        ])
    replacement_conditions.append(ReplacementRecord.requested_by_email.in_(TEST_USER_EMAILS))
    replacements = list(db.scalars(select(ReplacementRecord).where(or_(*replacement_conditions))).all())
    replacement_ids = _ids(replacements)

    request_conditions = [ITPurchaseRequest.requested_by_email.in_(TEST_USER_EMAILS)]
    purchase_requests = list(db.scalars(select(ITPurchaseRequest).where(or_(*request_conditions))).all())
    purchase_request_ids = _ids(purchase_requests)

    state_conditions = []
    if replacement_ids:
        state_conditions.append(ReplacementWorkflowState.replacement_record_id.in_(replacement_ids))
    if purchase_request_ids:
        state_conditions.append(ReplacementWorkflowState.purchase_request_id.in_(purchase_request_ids))
    if asset_ids:
        state_conditions.append(ReplacementWorkflowState.spare_asset_id.in_(asset_ids))
    states = list(db.scalars(
        select(ReplacementWorkflowState).where(or_(*state_conditions))
    ).all()) if state_conditions else []

    # A workflow state may reveal a generated Purchase Request not found by the
    # first pass (for example after a partially completed replacement test).
    purchase_request_ids.update(
        state.purchase_request_id for state in states if state.purchase_request_id is not None
    )
    if purchase_request_ids:
        purchase_requests = list(db.scalars(
            select(ITPurchaseRequest).where(ITPurchaseRequest.id.in_(purchase_request_ids))
        ).all())

    purchase_records = list(db.scalars(
        select(ITPurchaseRecord).where(or_(
            ITPurchaseRecord.purchase_request_id.in_(purchase_request_ids) if purchase_request_ids else False,
            ITPurchaseRecord.linked_asset_id.in_(asset_ids) if asset_ids else False,
        ))
    ).all()) if (purchase_request_ids or asset_ids) else []

    work_conditions = [WorkRecord.work_code.in_(TEST_WORK_CODES)]
    if asset_ids:
        work_conditions.append(WorkRecord.asset_id.in_(asset_ids))
    work_conditions.append(WorkRecord.submitted_by_email.in_(TEST_USER_EMAILS))
    work_records = list(db.scalars(select(WorkRecord).where(or_(*work_conditions))).all())
    work_ids = _ids(work_records)

    handover_conditions = [ITHandoverRecord.performed_by_email.in_(TEST_USER_EMAILS)]
    if asset_ids:
        handover_conditions.append(ITHandoverRecord.asset_id.in_(asset_ids))
    handovers = list(db.scalars(select(ITHandoverRecord).where(or_(*handover_conditions))).all())

    asset_histories = list(db.scalars(
        select(AssetHistory).where(AssetHistory.asset_id.in_(asset_ids))
    ).all()) if asset_ids else []

    component_conditions = [ComponentReplacement.performed_by_email.in_(TEST_USER_EMAILS)]
    if asset_ids:
        component_conditions.append(ComponentReplacement.asset_id.in_(asset_ids))
    if work_ids:
        component_conditions.append(ComponentReplacement.work_record_id.in_(work_ids))
    component_changes = list(db.scalars(
        select(ComponentReplacement).where(or_(*component_conditions))
    ).all())

    request_histories = list(db.scalars(
        select(ITPurchaseRequestHistory).where(ITPurchaseRequestHistory.request_id.in_(purchase_request_ids))
    ).all()) if purchase_request_ids else []

    approval_histories = list(db.scalars(
        select(ApprovalDecisionHistory).where(
            ApprovalDecisionHistory.performed_by_email.in_(TEST_USER_EMAILS)
        )
    ).all())

    request_codes = {row.request_code for row in purchase_requests}
    replacement_codes = {row.replacement_code for row in replacements}
    work_codes = {row.work_code for row in work_records}
    record_codes = request_codes | replacement_codes | work_codes
    if record_codes:
        approval_histories_by_code = list(db.scalars(
            select(ApprovalDecisionHistory).where(ApprovalDecisionHistory.record_code.in_(record_codes))
        ).all())
        by_id = {row.id: row for row in approval_histories}
        by_id.update({row.id: row for row in approval_histories_by_code})
        approval_histories = list(by_id.values())

    notifications = []
    all_notifications = list(db.scalars(select(GlobalNotification)).all())
    request_tokens = {f"approval:purchase_request:{request_id}:" for request_id in purchase_request_ids}
    replacement_tokens = {f"approval:replacement:{replacement_id}:" for replacement_id in replacement_ids}
    for row in all_notifications:
        dedupe = str(row.dedupe_key or "")
        message = str(row.message or "")
        if row.recipient_user_id in user_ids:
            notifications.append(row)
            continue
        if any(token in dedupe for token in request_tokens | replacement_tokens):
            notifications.append(row)
            continue
        if any(code and code in message for code in record_codes):
            notifications.append(row)

    return {
        "notifications": notifications,
        "approval_histories": approval_histories,
        "purchase_request_histories": request_histories,
        "component_changes": component_changes,
        "handover_records": handovers,
        "asset_histories": asset_histories,
        "purchase_records": purchase_records,
        "replacement_states": states,
        "purchase_requests": purchase_requests,
        "replacement_records": replacements,
        "work_records": work_records,
        "assets": assets,
        "users": users,
    }


def describe(groups):
    print("Known Batch 3 / Batch 4 pytest artifact audit")
    print("=" * 56)
    for name, rows in groups.items():
        print(f"{name:28s} {len(rows):4d}")

    print("\nExact test users:")
    for row in groups["users"]:
        print(f"  user id={row.id} email={row.email}")

    print("\nExact test assets:")
    for row in groups["assets"]:
        print(f"  asset id={row.id} code={row.asset_code} tag={row.cpu_asset_tag}")

    print("\nReplacement records:")
    for row in groups["replacement_records"]:
        print(f"  replacement id={row.id} code={row.replacement_code}")

    print("\nPurchase requests:")
    for row in groups["purchase_requests"]:
        print(f"  request id={row.id} code={row.request_code} status={row.status}")

    print("\nPurchase records:")
    for row in groups["purchase_records"]:
        print(f"  purchase id={row.id} code={row.purchase_code}")


def delete_groups(db, groups):
    # Delete child/audit rows first, then workflow/master rows.
    order = [
        "notifications",
        "approval_histories",
        "purchase_request_histories",
        "component_changes",
        "handover_records",
        "asset_histories",
        "purchase_records",
        "replacement_states",
        "purchase_requests",
        "replacement_records",
        "work_records",
        "assets",
        "users",
    ]
    deleted = defaultdict(int)
    for name in order:
        for row in groups[name]:
            db.delete(row)
            deleted[name] += 1
        db.flush()
    return deleted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete the exact test artifacts. Without this flag the script is read-only.",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        groups = collect_artifacts(db)
        describe(groups)
        total = sum(len(rows) for rows in groups.values())
        if not args.apply:
            print(f"\nDRY RUN ONLY: {total} matched rows. Nothing was deleted.")
            print("Run again with --apply only if the listed records are the Batch 3 / Batch 4 QA artifacts.")
            return
        if total == 0:
            print("\nNo known Batch 3 / Batch 4 pytest artifacts were found. Nothing to delete.")
            return
        deleted = delete_groups(db, groups)
        db.commit()
        print("\nCleanup committed:")
        for name, count in deleted.items():
            print(f"  {name:28s} {count:4d}")


if __name__ == "__main__":
    main()
