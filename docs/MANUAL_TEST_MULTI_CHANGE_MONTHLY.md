# Manual Test — Multi-Component Change and Monthly Reports

## Test 1: Search and select a system

1. Login as IT.
2. Open **Work Records**.
3. Select **Upgrade / Replacement**.
4. Type a CPU tag, workstation, employee or system name.
5. Select the result showing the correct `CPU Tag + Workstation`.

Expected: the selected system card displays employee, department, system name and internal ID.

## Test 2: Multiple changes in one activity

Choose **Upgrade + Replacement** and add four rows:

1. Mouse — Replacement — old tag to new tag.
2. Keyboard — Replacement — old tag to new tag.
3. Memory — Upgrade — 8 GB to 16 GB.
4. SSD — Upgrade + Replacement — 256 GB to 512 GB.

Save once.

Expected:

- One `CHG-xxxx` batch is created.
- One `ITW-xxxx` work record is created.
- Four history items are created.
- The Asset Register immediately shows all four new values.
- Reusing an active component tag is rejected.

## Test 3: Month-wise Excel

1. Open **Excel & Reports**.
2. Select the current month.
3. Download **Monthly Asset Register**.
4. Download **Monthly Change History**.
5. Download **Monthly Summary**.

Expected:

- Asset Register shows only latest values.
- Change History shows each old-to-new item with the same batch/work ID.
- Summary counts the new asset and each change category.

## Test 4: Historical month

Select a prior workbook month such as October 2025.

Expected: a single clean monthly workbook downloads with the selected month's original records.

## Test 5: Persistence

Run:

```powershell
docker compose restart
```

Expected: the live values, work record, batch history and report months remain available.
