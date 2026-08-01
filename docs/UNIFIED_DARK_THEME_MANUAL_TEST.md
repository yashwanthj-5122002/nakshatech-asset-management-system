# Unified Theme Manual Test

## Visual coverage

Log in separately as Admin, Management, IT and Drone. Confirm each role uses the same dark geospatial visual system while retaining its own menu and permissions.

Check:

- Sidebar logo, active menu item, department card and Logout.
- Top header system status and role context.
- Dashboard page header, KPI cards, charts and alerts.
- Asset and Drone registers: search, filters, table, pagination and detail panels.
- Add/Edit forms: field alignment, dropdowns, date inputs, text areas, focus states and sticky actions.
- IT Work Records and Replacements.
- Excel & Reports cards and download buttons.
- Drone Assets, Kits, Projects, Operations, Work Records, Movements and Import.
- Admin and Management overview cards.
- Modals, success/error messages, empty/loading states and status badges.

## Mandatory functional checks

1. Login and Logout for every role.
2. Role-based routes and forbidden-page protection.
3. IT Dashboard month selection and Refresh.
4. IT asset search, filters, pagination, Add and Edit.
5. Work-record creation and component-change workflow.
6. Replacement request and approval.
7. Excel downloads.
8. Drone dashboard data load.
9. Drone asset search, Add/Edit/Open.
10. Drone project and kit pages.
11. Existing Drone operational workflows.
12. Browser console: no new errors.

## Responsive checks

Test at approximately 1440 px, 1024 px, 768 px and 390 px widths. The sidebar should collapse below 900 px, forms should stack, and tables should scroll horizontally without clipping the page.
