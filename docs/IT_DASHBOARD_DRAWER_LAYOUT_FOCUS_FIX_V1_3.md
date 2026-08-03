# IT Dashboard Drawer Layout and Focus Fix v1.3

This frontend-only update corrects the dashboard drill-down drawer without changing any API, database record, reporting-month behavior, permission or Excel calculation.

## Corrected behavior

- The drawer begins below the global application top bar.
- The drawer title, reporting-month subtitle, Show/Hide Visuals button and Close button remain fully visible.
- The header and footer remain stable while the asset table scrolls.
- Search, Download, filters, results and pagination use consistent control heights and alignment.
- Desktop, tablet and mobile top-bar heights are handled separately.
- Search inputs and other form controls display one accessible focus ring instead of an outer and inner blue box.
- Composite search fields place the focus ring on their outer shell only.

## Preserved behavior

- Dashboard card and department drill-down
- Visual analytics toggle and graph filtering
- Asset filters, sorting and pagination
- Filtered Excel download
- Reporting-month persistence
- Asset Register and edit workflows
- Work Records, Component Changes, Handover and Purchase
- Recent Changes, backups, roles and permissions
- Backend, database schema, records and Docker volumes
