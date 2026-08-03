# NakshaTech IT Monthly Tracking Integration

## Purpose

This patch adds a clean, month-wise IT activity tracking layer to the existing NakshaTech Asset Management System. It is applied on top of the current Software Team/Admin role integration and the existing Upgrade, Replacement, Downgrade and Upgrade + Replacement workflows.

## New pages

- **Handover & Return** (`/it/handover-return`)
  - Record laptop and desktop handovers, returns and transfers.
  - Search and optionally link an existing asset.
  - When explicitly enabled, update the linked Asset Register entry in the same database transaction.
  - Import the supplied historical laptop and desktop workbooks without overwriting current assets.

- **Purchase & Procurement** (`/it/purchases`)
  - Record supplier, PO/asset number, item, quantity, price, received date, inspection status, approver and remarks.
  - Link a purchase to an existing asset where applicable.
  - Import the supplied historical purchase workbook.

- **Recent Changes** (`/it/recent-changes`)
  - Month-wise visual summary.
  - Filters for department, device type, changed-by user, action type and text search.
  - Unified activity timeline and detailed old-to-new change table.
  - Includes full asset edits, component changes, handover/return and purchase records.

## Monthly Excel

The **Complete Monthly IT Activity** workbook contains:

1. Monthly Summary
2. Detailed Monthly Activity
3. Asset Edit History
4. Component Changes
5. Laptop Handover Return
6. Desktop Handover Return
7. Purchase Details
8. User Activity Summary

New software-entered records include the authenticated user and backend-generated Asia/Kolkata date/time. Historical workbook rows retain their source date. If the source workbook did not contain a time, the report states **Not recorded** rather than inventing one.

## Historical source files included

- Laptop_Handover_and_Returned.xlsx
- Desktop_Handover_and_Returned.xlsx
- Purchase_Details.xlsx

Expected first import from the supplied files:

- Laptop records: 59 created; 2 invalid rows skipped
- Desktop records: 185 created; 3 invalid rows skipped
- Purchase records: 19 created; 0 invalid rows

The importer is idempotent. Running the installer again does not duplicate previously imported rows.

## Existing workflow protection

The patch does not reset or delete Docker volumes. It does not replace existing login credentials. It preserves:

- Software Team, Admin, Management, IT and Drone logins
- Asset Register and full edit audit
- Upgrade, Replacement, Downgrade and combined component changes
- IT Work Records
- Drone assets, kits, projects, operations and movement history
- Existing Excel reports and backup functions

New handover and purchase records are stored in separate tables. Historical imports do not mutate the live Asset Register.

## Installer safety

The installer:

1. Validates Docker Compose.
2. Starts only required data services without resetting volumes.
3. Backs up every source file that will be changed.
4. Attempts a PostgreSQL dump.
5. Stops only frontend, backend and Nginx during source replacement.
6. Rebuilds and verifies the application.
7. Imports the supplied historical workbooks.
8. Restores the previous source automatically if the application build or verification fails.

Backups are stored under:

`_it_activity_tracking_backups\<timestamp>`

## Validation performed before release

- Backend Python compilation passed.
- New FastAPI routes loaded successfully.
- Role tests passed for IT, Management and Software Team.
- Management read-only restrictions passed.
- Handover and purchase create/read tests passed.
- Existing IT dashboard, component replacement and report-month endpoints remained available.
- Full asset edit plus multiple component changes produced correct, non-duplicated monthly totals.
- Historical imports were tested twice and did not create duplicates on the second run.
- Monthly workbook structure, sheet names and freeze panes were checked with openpyxl.
- All frontend TypeScript/TSX files passed syntax transpilation.

A complete npm dependency build could not be performed in the sandbox because its internal npm registry did not provide the project's React type package. The Windows installer performs the actual Docker frontend build on the user's machine and rolls back the source if it fails.
