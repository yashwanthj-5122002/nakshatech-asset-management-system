# IT Dashboard Drawer Visual Analytics v1.1

This update places visual analytics inside the same-page asset drill-down drawer opened from Total IT Assets, Computers, Laptops, Smartphones, status cards and department bars.

## Scope-aware visuals

- Total IT Assets: Device Mix donut, Status Distribution donut and Department Allocation bar graph.
- Computer/Laptop/Smartphone scope: Status Distribution donut and Department Allocation bar graph.
- Department scope: Device Mix donut and Status Distribution donut.
- Status scope: Device Mix donut and Department Allocation bar graph.

All chart values are calculated from the complete filtered result set returned by the backend, not only the current paginated table page. Clicking a chart slice or department bar filters the same drawer table without navigating away from the dashboard.

## Preserved behavior

- Same-page read-only drawer
- Reporting month persistence
- Search, combined filters, sorting and pagination
- Filtered Excel download
- Asset Register and editing
- Work Records, Component Changes, Handover & Return, Purchase & Procurement and Recent Changes
- IT/Admin/Management permissions
- Existing dashboard-level charts

No database schema or data migration is included.
