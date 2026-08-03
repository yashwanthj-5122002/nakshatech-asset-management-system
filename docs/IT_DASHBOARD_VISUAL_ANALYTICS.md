# IT Dashboard Visual Analytics v1.0

This frontend-only advancement builds on the working IT Dashboard Drill-Down v1.2 integration.

## Added visuals

1. Interactive Device Distribution donut chart
   - Uses the same inventory data as the dashboard KPI cards.
   - Clicking a segment or legend opens the matching device records in the existing same-page drawer.

2. Interactive Asset Status donut chart
   - Assigned and In Use are intentionally combined so the chart count matches the existing Assigned / In Use drill-down.
   - Other statuses remain exact and open their matching records in the same-page drawer.

3. Department allocation bar graph
   - Existing department bars remain clickable and continue to open the same-page drawer.

4. Six-month IT activity line graph
   - The six-month window ends at the reporting month selected on the dashboard.
   - Selectable metrics: total activities, full asset edit saves, component changes, handovers, returns, and purchases.
   - Activity data is read from the existing month-aware IT activity API.

## Accuracy protections

- Selected-month response validation for every trend request.
- AbortController cancellation when the reporting month changes.
- Latest-request-wins sequence guard.
- Live inventory charts remain separate from historical monthly activity charts.
- Chart clicks never navigate to Asset Register.
- No database schema or record changes.

## Existing features retained

- Reporting-month persistence and historical month viewing.
- Same-dashboard asset drill-down drawer.
- Search, combined filters, sorting, pagination and filtered Excel.
- Asset Register, editing, Work Records, Component Changes, Handover & Return, Purchases, Recent Changes and existing reports.
- IT, Admin and Management permissions.
- Drone module and all other application modules.
