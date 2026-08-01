# NakshaTech Asset Management System Architecture

## Access model

A single login page validates both credentials and the selected role.

- **Admin**: all dashboards, asset changes, imports, approvals, reports and future settings.
- **Management**: combined IT/drone monitoring, completed-work approval, replacement approval and reports.
- **IT**: IT dashboard, asset register, work records, replacement requests and Excel exports.
- **Drone**: drone dashboard, fleet/location view and drone work records.

The frontend hides inaccessible routes and the FastAPI backend independently enforces every role permission.

## Runtime architecture

```text
Browser
  |
  +-- http://localhost:3100  React + TypeScript + Vite
  |
  +-- http://localhost:8088  Nginx unified entry point
                               |
                               +-- /      -> frontend:3100
                               +-- /api/* -> backend:8000

FastAPI backend
  |
  +-- PostgreSQL + PostGIS  assets, users, work, replacements, drones, locations
  +-- MinIO                future photos, invoices, certificates and evidence
  +-- Redis                future notifications, queues and caching
```

## IT data model

```text
User
Asset
  +-- AssetHistory
  +-- WorkRecord
  +-- ReplacementRecord (old asset)
  +-- ReplacementRecord (new asset)

Drone
  +-- DroneLocation
  +-- WorkRecord
```

The old asset record is never deleted during replacement. An approved replacement links the old and new asset, changes the old status to `replaced`, transfers employee/department/workstation information to the new asset and preserves the audit history.

## Excel flow

```text
Supplied NakshaTech workbook
  -> latest sheet parsed and standardized
  -> 183 current assets seeded into PostgreSQL
  -> users maintain records through application forms
  -> Download Asset Excel
  -> current database values written back into the original workbook layout
  -> historical monthly sheets preserved
```

A separate Dashboard Excel export contains summary KPIs, the complete asset register, status and department summaries, work records, replacement records and data-quality checks.

## Drone location flow

```text
Drone GNSS / controller / SDK / GPS tracker / manual form
  -> POST /api/drones/{id}/location
  -> DroneLocation table with timestamp
  -> REST or WebSocket update
  -> MapLibre map in the drone dashboard
```

The map displays the current or last-known coordinate and timestamp; it does not claim stale data is live.

## Expansion strategy

New features should be isolated by module. Add a frontend feature/page and corresponding backend router/service/model rather than placing unrelated logic into existing files.

Planned extension points already represented in the UI include QR/barcode asset scanning, notifications, branch masters, employee masters, software licences, preventive maintenance, vendor/procurement workflows, SSO and manufacturer-specific drone telemetry adapters.
