# IT Reporting Month Race Fix v1.4

## Confirmed problem

The frontend previously copied a valid `?month=` value from the URL back into the global reporting-month state on every render. When a user selected a historical month, React updated the global state before React Router committed the new query string. During that small interval, the old URL value—normally the present month—was copied back and reset the selection.

The dashboard and Recent Changes page also accepted whichever API response completed last. Rapid month changes could therefore show data for a month different from the month displayed in the selector.

## Fixes

- Updates the reporting month and URL as one guarded transition.
- Prevents a stale URL value from overwriting a new user selection.
- Keeps the selected month in sidebar navigation and page URLs.
- Adds latest-request-wins protection to Dashboard, Recent Changes, Handover/Return and Purchase pages.
- Verifies that the API response month matches the requested month before rendering.
- Clears old month data while a newly selected month is loading.
- Keeps existing backend reporting-month storage, audit timestamps and month-specific remarks unchanged.

## Expected behavior

1. Select June 2026 on the IT Dashboard.
2. Navigate to Asset Register, Work Records, Component Changes, Handover & Return, Purchase & Procurement, Recent Changes and Reports.
3. Every page remains in June 2026.
4. An asset edit saved while June is selected is reported in June.
5. The actual server-recorded date and time remain the real date and time of entry.
6. June activity remarks stay attached only to the June activity record.
7. August totals and August activity remarks are not changed by the June reporting entry.
8. The month resets only through Return to Present Month.

## Scope and safety

This patch changes frontend files only. It does not alter the database schema, backend API, passwords, Docker volumes, Drone features, role permissions or existing records.
