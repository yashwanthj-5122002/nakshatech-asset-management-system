# IT Reporting Month Persistence and Audit Separation

## Purpose

This integration separates the **effective reporting month** from the immutable
**system-recorded date and time**.

Example:

- Selected reporting month: June 2026
- User saves an asset edit on: 03 August 2026 at 03:15 PM
- The activity appears in: June dashboard activity, June Recent Changes and June monthly Excel
- The audit still shows: actually recorded on 03 August 2026 at 03:15 PM
- August activity totals are not increased by that June-assigned activity

## Persistent month behavior

The selected month is kept in all three places:

1. React IT month context
2. Browser local storage (`nakshatech_it_reporting_month`)
3. URL query parameter (`?month=YYYY-MM`)

All IT sidebar links carry the selected month. It changes only when the user
chooses another month or clicks **Return to Present Month**.

## Live asset values versus monthly activity

The Asset Register always loads the current live asset values. A historical
reporting month does not create a separate editable copy of the asset.

Saving an action while June is selected:

- updates the current live asset when the operation requires it;
- writes the activity with `reporting_month = 2026-06`;
- keeps `created_at` as the actual server timestamp;
- displays the activity only in June month-filtered activity reports.

## Remarks isolation

Two remark types are deliberately separate:

- **Activity Remarks** belong only to one audit/activity record and its selected
  reporting month. They never carry automatically into later months.
- **Asset Master Remarks** are a permanent live-register field. They change only
  when a user intentionally edits the field in Full Asset Edit or explicitly
  chooses **Asset Master Remarks** as the changed field.

Status, assignment, return, handover, purchase and component activity remarks do
not append themselves to Asset Master Remarks.

## Database changes

A nullable `reporting_month VARCHAR(7)` column is added non-destructively to:

- `asset_history`
- `work_records`
- `component_replacements`
- `replacement_records`
- `it_handover_records`
- `it_purchase_records`

Existing records remain valid. When `reporting_month` is null, month filters fall
back to the record's original timestamp or business date, preserving historical
behavior.

No table, row, password, Docker volume or existing asset record is deleted.

## Monthly Excel

Monthly IT workbooks contain both:

- Reporting Month
- Activity / Business Date
- Activity Time
- System Recorded At

The activity remark is exported only on its own activity row.

## Verification

Read-only live schema verification:

```powershell
cd "E:\NakshaTech_Asset_Management_Local_Master\NakshaTech-Asset-Management-Local-Master"
docker compose exec -T backend python scripts/verify_reporting_month_schema.py
```

In-memory behavior verification (does not connect to PostgreSQL):

```powershell
docker compose exec -T backend python scripts/verify_reporting_month_integration.py
```

Expected final line:

```text
REPORTING MONTH VERIFICATION PASSED
```

## Acceptance test

1. Select June 2026 on IT Dashboard.
2. Open Asset Register and confirm the URL still contains `month=2026-06`.
3. Edit a test asset and enter an Edit Activity Remark.
4. Open Recent Changes; June must still be selected.
5. Confirm the edit appears in June and shows the actual August recorded time.
6. Select August and confirm that June activity is not listed or counted there.
7. Return to the asset and confirm Asset Master Remarks did not change unless it
   was intentionally edited.
8. Download June Full Tracking Workbook and verify the Reporting Month and System
   Recorded At columns.
9. Click Return to Present Month and confirm all IT links now carry the present
   month.
10. Test IT, Admin, Management and Drone navigation and existing workflows.
