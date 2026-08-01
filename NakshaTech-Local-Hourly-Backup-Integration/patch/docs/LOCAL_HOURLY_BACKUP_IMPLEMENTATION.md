# NakshaTech Local Hourly Backup Integration

## Scope

This release adds a read-only backup layer. Existing dashboards, charts, tracking, routes, business rules, IT workflows, Drone workflows, authentication and frontend files are unchanged.

## Final behavior

- All users continue saving to the central PostgreSQL database.
- The designated Windows backup PC checks the deployed application every 5 minutes.
- At minute 55 of every hour, the agent downloads one current-month Excel workbook for each role:
  - IT
  - Drone
  - Management
  - Admin
- The current workbook for a role is atomically replaced only after checksum and XLSX validation.
- At a month boundary, the last valid current workbook is moved to the role's `Monthly` folder and is never automatically overwritten.
- If the application or backup API becomes unavailable, a crash incident folder is created with the latest validated Excel files and a crash report.
- When the application recovers, the agent records the recovery and immediately refreshes all four workbooks.

## Local folder

`E:\NakshaTech_Backups`

Each role has `Current` and `Monthly` folders. Crash reports and logs are separate.

## Accuracy rule

PostgreSQL remains the live source of truth. The hourly workbooks contain current master data plus activity/history records for the reporting month. Completed-month workbooks are the last validated hourly files from that month and are frozen locally.

## Security

- The backup API is disabled by default.
- It requires a dedicated token of at least 32 characters.
- Password hashes are excluded from Excel.
- The Windows token/config folder is restricted to SYSTEM and local Administrators.
- The PC opens an outbound HTTPS connection. No inbound port or fixed PC IP address is required.
