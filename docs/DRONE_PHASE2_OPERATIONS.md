# Drone Operational Phase 2

This release converts the Phase 1 Drone registers into a connected operational workflow while preserving the separate IT module.

## New Drone pages

- `/drone/operations` — dispatch, assignment, transfer, full return and partial return
- `/drone/work-records` — dedicated Drone department work records
- `/drone/movements` — permanent movement and custody history
- `/drone/projects/:id` — project detail, current assets/kits, operations, work records and movement timeline

## Connected update behaviour

A confirmed dispatch updates, in one database transaction:

- Drone/Survey asset current status
- current project
- current custodian
- current location
- selected kit and its active components
- dispatch operation and item records
- asset/kit movement history
- an automatically linked Drone work record
- Drone project details
- Drone dashboard operational counters

Return supports full or partial quantities. A kit return can return the complete kit, while component operation rows remain individually visible for partial processing. Transfer updates project/custody/location and preserves the prior movement history. Assignment supports employee custody with an optional project.

## Data isolation

All new records use separate tables:

- `drone_operations`
- `drone_operation_items`
- `drone_asset_movements`
- `drone_work_records`

No IT asset, IT work, IT replacement or IT monthly report table is reused.

## Validation

The backend prevents:

- dispatch of an unavailable serialized asset
- quantity allocation above available stock
- duplicate item selection in one dispatch
- dispatch to a closed/cancelled project
- return of more than the open quantity
- return against a completed dispatch
- closing a project while assets, kits or dispatches remain unresolved
- IT-role access to the new Drone operational APIs

## Phase boundary

This phase does not yet add the complete maintenance, calibration, physical verification, UIN workflow, HDD chain-of-custody UI or final monthly/yearly Drone Excel reporting. Those remain separate future phases.
