# Batch 3 — Asset Lifecycle, Audit & Data Integrity

Branch: `integration/batch-3-complete`

Base: `integration/asset-management-complete-2026-08-13` at `465e019`

## Integrated scope

### Replacement → spare stock → procurement

- Replacement requests preserve the exact asset lifecycle status that existed before the request.
- Management approval checks suitable **Available** stock of the same device type first.
- If a suitable spare exists, the spare is allocated and no Purchase Request is generated.
- If no suitable spare exists, one linked Purchase Request is generated automatically and the old asset remains `replacement_pending`.
- The replacement and Purchase Request are linked through the Batch 3 workflow-state table with unique constraints preventing duplicate procurement links.
- Completing procurement for a replacement requires an actual linked Available asset of the correct device type.
- Only after that asset is linked does the old asset become `replaced` and the new asset inherit the live custody when applicable.
- Replacement rejection restores the preserved pre-request lifecycle status rather than guessing from the current user field.

### Complete audit coverage

- Manual asset creation keeps the existing `asset_created` audit entry.
- Normal Asset Excel imports now create audit history for created and changed assets.
- Printer Excel imports now create audit history for created and changed printers.
- External HDD import audit rows are enriched with the authenticated user's email and role.
- Existing edit, assignment, transfer, return, component, handover, replacement and purchase histories are preserved.
- Replacement approval/procurement transitions write asset history and approval history.
- Purchase completion writes purchase-request approval history.

### Recent Changes integrity

The authoritative `/api/it-activity/summary` now includes:

- asset creation;
- asset edits and Excel-import updates;
- custody activity;
- component changes;
- replacement approval history;
- purchase-request approval and completion history;
- IT Work approval history;
- IT Work records without an asset link.

Existing frontend routes continue to use the same API path, so no separate Batch 3 UI or duplicate workflow is introduced.

### Reconciliation

New read-only endpoint: `GET /api/batch3/reconciliation`

It checks:

- primary device totals against canonical device breakdowns;
- lifecycle totals against primary IT totals;
- External HDD separation from primary IT totals;
- duplicate asset codes;
- duplicate serial numbers;
- duplicate asset tags;
- Available assets with stale custodians;
- assigned Computer/Laptop records missing mandatory custody fields.

### Concurrency / duplicate safety

- Manual asset creation and all three asset-import paths share a PostgreSQL transaction advisory lock before code allocation.
- Replacement creation is serialized through the same lock and keeps the existing active-request guard.
- Management replacement decisions use row locks.
- Spare selection uses row locks.
- Purchase completion uses row locks and the existing one-purchase-per-request uniqueness constraint.
- The Batch 3 replacement workflow table makes both replacement-state and linked-purchase relationships unique.

## Runtime integration

Docker now starts `app.batch3_main:app`.

`batch3_main` loads the existing application unchanged, adds the Batch 3 authoritative handlers, removes only the matching legacy route definitions, and leaves all unrelated routes/features intact.

## Automated test added

`backend/tests/test_batch3_complete.py`

The focused test covers:

1. spare-first replacement;
2. no-spare Purchase Request generation;
3. procurement completion with a real linked asset;
4. old/new custody and lifecycle finalization;
5. replacement and purchase activity traceability;
6. reconciliation checks.

## Freeze gate

Do not merge/freeze Batch 3 until the target workstation confirms:

```powershell
# from the Batch 3 branch
docker compose up -d --build
docker compose ps
docker compose exec backend pytest -q tests/test_batch3_complete.py
```

Then manually verify one spare-stock replacement and one no-spare procurement cycle using QA assets only, followed by `GET /api/batch3/reconciliation` with an authorized IT/Management/Admin session.
