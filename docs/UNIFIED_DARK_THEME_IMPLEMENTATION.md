# Unified Dark Geospatial Enterprise Theme

## Scope

This release changes the authenticated frontend presentation only. It applies one shared Dark Geospatial Enterprise Glassmorphism design system to Admin, Management, IT and Drone pages.

The approved Welcome and Login pages are not redesigned. Their component files and page-specific styles remain unchanged.

## Frontend files changed

- `frontend/src/styles.css`
- `frontend/src/components/Layout.tsx`
- `frontend/src/components/Charts.tsx`
- `frontend/src/components/DroneMap.tsx`
- `frontend/public/geospatial-world-grid.svg` (new decorative asset)

## Design changes

- Centralized dark navy, cyan and blue theme variables scoped to authenticated pages.
- Shared premium sidebar, active-navigation treatment and role/department card.
- Shared translucent top header and system-status presentation.
- Subtle geospatial world-grid watermark in page headers and internal backgrounds.
- Glass KPI cards, panels, module cards, report cards and project cards.
- Dark forms, dropdowns, filters, search controls and focus rings.
- Dark tables with aligned headers, thin separators and row hover states.
- Consistent semantic status colors.
- Cyan/blue chart palette and dark treatment for the existing Drone map.
- Responsive sidebar, cards, forms and tables.
- Reduced-motion support.

## Functionality preserved

No API path, form payload, event handler, route, role permission, authentication rule, data-fetching function, Excel download, calculation or backend file was changed.

The IT and Drone business workflows remain exactly as supplied in the source ZIP.

## Installation

1. Extract the release ZIP into `E:\BEST_ASSEST_MANAGEMENT_SYSTEM`.
2. Confirm the folder remains `E:\BEST_ASSEST_MANAGEMENT_SYSTEM\asset-management-system`.
3. Run `APPLY_UNIFIED_DARK_THEME_WINDOWS.cmd`.
4. Open `http://localhost:3100`.
5. Press `Ctrl+Shift+R` once.

The apply script builds and recreates only the frontend container and restarts Nginx. It does not recreate the backend, database, Redis or MinIO services and never deletes Docker volumes.
