# IT Dashboard Same-Page Asset Drill-Down

## Purpose

This integration converts the IT Dashboard inventory KPI cards and department allocation bars into read-only, same-page drill-down controls. The Asset Register page is not opened when a dashboard card or department bar is clicked.

## Clickable dashboard items

- Total IT Assets
- Computers
- Laptops
- Smartphones
- Assigned / In Use
- Available
- Under Repair
- Replacement Pending
- Every department shown in Assets by Department

## Drawer behavior

The drawer opens over the right side of the same dashboard and shows:

- The selected reporting month
- Exact scope total and filtered total
- Device and status summary cards
- Search by asset tag, internal ID, workstation, employee, system name, IP, MAC, location or remarks
- Department, device, status, location and work-mode filters
- Sorting and pagination
- Expandable complete asset details
- Download Current Results Excel
- Loading, empty, retry and stale-response protection

## Count accuracy

All dashboard and drawer data use the same month-aware inventory source:

- Present month: live `assets` table
- Finalized month: monthly system snapshot
- Historical workbook month: original read-only Excel sheet

The Computer card uses only `device_type = Computer`. The Laptop card uses only `device_type = Laptop`. Assigned / In Use combines only `assigned` and `in_use`, exactly matching the existing dashboard KPI.

## Permissions

The new APIs use the same existing dashboard permissions:

- IT Department
- Admin
- Management

The drawer is read-only. It does not add, edit, assign, return, replace, retire or delete assets.

## Data safety

- No database migration
- No database schema change
- No record update from the drawer
- No password or `.env` change
- No Docker volume reset
- Existing Asset Register, Work Records, Component Changes, Handover & Return, Purchases, Recent Changes, Excel reports, Backups, Drone and role workflows remain unchanged

## New API routes

- `GET /api/dashboard/it/assets`
- `GET /api/reports/it-dashboard-assets.xlsx`

Both routes are read-only and require the same roles as the existing IT dashboard.

## Installer v1.2 route verification

The deployed backend routes are verified by `scripts/verify_dashboard_drilldown_routes.py`.
The verifier safely handles normal routes and nested/custom route wrappers and confirms
both `/api/dashboard/it/assets` and `/api/reports/it-dashboard-assets.xlsx`.
