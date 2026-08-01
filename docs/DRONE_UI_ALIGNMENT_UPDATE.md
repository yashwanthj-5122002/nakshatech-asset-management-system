# Drone Module UI Alignment Update

## Scope

This update is isolated to the Drone frontend presentation. It does not alter IT routes, IT APIs, IT database models, IT Excel reports, authentication, or Docker volumes.

## Pages corrected

- `/drone/projects`
- `/drone/assets`
- `/drone/assets/new`
- `/drone/assets/:id/edit`
- `/drone/kits` responsive text handling

## Main corrections

- Restored real CSS grid layout for Drone forms.
- Added consistent labels, spacing, input heights, focus states and placeholders.
- Grouped Add/Edit Asset fields into aligned four-, three-, two- and one-column responsive layouts.
- Added clean numbered section headings and a sticky action footer.
- Rebuilt New Project form with defined column spans and a separate remarks field.
- Aligned Asset Register search, filters, total count, table and pagination.
- Added horizontal table scrolling only when the viewport is too narrow.
- Added mobile layouts with one field per row and full-width actions.
- Prevented long kit component values from overflowing.

## Breakpoints

- Large desktop: 4-column asset forms and 6-column project form grid.
- Standard desktop/laptop: 3-column asset form and 4-column project grid.
- Tablet: 2-column forms.
- Mobile: 1-column forms and stacked action buttons.

## Apply

Run `APPLY_DRONE_UI_ALIGNMENT_WINDOWS.cmd` from the project root.
