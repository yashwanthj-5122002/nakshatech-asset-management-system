# Manual Test — Drone Operational Phase 2

## 1. Create a project

Open `/drone/projects`, create `TEST - Davangere Drone Survey`, then open its card. Confirm the project detail page loads.

## 2. Create a test drone

Open `/drone/assets/new` and create:

- Equipment: `TEST - DJI M350 RTK`
- Category: `Drone`
- Serial: `TEST-M350-001`
- Tracking: Serialized asset
- Quantity: 1
- Status: Available
- Location: NakshaTech Head Office

Refresh and confirm it remains in the register.

## 3. Dispatch

Open `/drone/operations`:

- Dispatch tab
- Project: test project
- Custodian: `Vaibhav`
- Destination: `Davangere, Karnataka`
- Purpose: `Urban drone survey and mapping`
- Select the test drone
- Confirm Dispatch

Expected:

- operation code begins `DRN-DSP-`
- asset becomes `Deployed To Project`
- project and custodian appear on asset detail
- project detail shows the asset and operation
- Drone Work Records receives an automatic dispatch record
- Movement History receives a dispatch row

## 4. Partial return

Dispatch a quantity-managed test battery with quantity 2 from a total quantity 5. On the Return tab, return quantity 1.

Expected:

- source dispatch becomes `Partial`
- one quantity remains open
- the asset still shows active project custody
- the register shows allocated and available quantities

## 5. Transfer

Transfer the remaining quantity or a serialized asset to another active project/custodian.

Expected:

- current project/custodian/location change
- a `DRN-TRF-` operation is created
- movement history preserves old and new custody

## 6. Final return

Return the remaining open quantity.

Expected:

- source dispatch becomes `Completed`
- asset becomes Available
- project/custodian are cleared
- return work record and movement are created

## 7. Project close rule

Try closing a project with active assets: it must be blocked. Return all items, then close it: it must succeed.

## 8. IT isolation

Login as IT and verify:

- IT Dashboard remains 183 assets before adding any separate IT test asset
- Drone operational pages are not shown
- `/api/drone/operations` returns forbidden for IT role
