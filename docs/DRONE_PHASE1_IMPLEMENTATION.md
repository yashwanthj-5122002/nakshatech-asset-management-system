# Drone and Survey Asset Management — Foundation Delivery

## Canonical project

The root project containing `docker-compose.yml`, `backend/` and `frontend/` was used as the active implementation. A duplicate project remains under `asset-management-system/` and was not edited independently.

## Delivered in this phase

- Separate Drone/Survey SQLAlchemy models and `/api/drone/*` router.
- Lossless parser for all four supplied workbook sheets.
- Preservation of all 52 named source attributes.
- Original workbook, sheet, row, section, raw payload and header map retained.
- Import preview, exception detection and Admin commit workflow.
- Permanent Drone and Survey Asset Master.
- Manual creation/editing of future drones and equipment.
- Multiple projects and project creation.
- Trinity Unit 1173 and Unit 1076 kit/component creation.
- Airtel modem, UAV/UIN and HDD-delivery preservation.
- Searchable, paginated Drone asset register.
- Separate Drone dashboard, assets, kits, projects and import pages.
- Existing `/api/drones`, location POST and WebSocket remain available.
- Drone role remains forbidden from the IT dashboard.

## Verified workbook parse

- Main inventory records: 66
- Airtel modem connections: 2
- UAV/UIN registrations: 3
- Trinity component rows: 39
- Trinity kits: 2
- Amrut custody records: 18
- HDD delivery transactions: 7
- Total parsed records: 135
- Named source attributes: 52

The first approved import creates 123 permanent physical/quantity assets. UIN, telecom and HDD delivery records remain in their own operational tables rather than being incorrectly counted as physical assets.

## Intentional phase boundary

This delivery is the tested data foundation and first usable UI. Dispatch/partial return, maintenance, calibration, physical verification, historical monthly snapshots, exact monthly Excel regeneration and long-range reports remain for subsequent phases. They were not represented as finished placeholder pages.
