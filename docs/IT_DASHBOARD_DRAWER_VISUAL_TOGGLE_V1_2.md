# IT Dashboard Drawer Visual Toggle v1.2

This frontend-only enhancement keeps the working IT dashboard drill-down and chart calculations unchanged while improving space usage inside the drawer.

## Behaviour

- Visual analytics are collapsed when a new drawer opens.
- A single **Show Visuals** button appears in the drawer header beside the Close button.
- Clicking the button expands the charts above the search and asset table.
- The same button changes to **Hide Visuals** and collapses the charts again.
- Opening or closing visuals does not change the reporting month, filters, search, current page, selected summary card or downloaded result scope.
- Device drawers show Status Distribution and Department Allocation.
- Total Assets shows Device Mix, Status Distribution and Department Allocation.
- Department drawers show Device Mix and Status Distribution; the redundant one-department allocation graph is omitted.
- Department Allocation uses adaptive height. Small department lists no longer stretch to the height of the donut chart.

## Safety

The patch changes only:

- `frontend/src/components/AssetDrilldownDrawer.tsx`
- `frontend/src/styles.css`
- one frontend verification script
- this documentation file

It does not change the backend, database schema, asset records, Docker volumes, passwords, permissions, monthly reporting logic or Excel generation.
