# Employee Authentication and Ticketing Test Report

Branch: `feature/employee-auth-ticket-system`  
Base: `dc80808`

## Passed backend verification

The following checks passed in isolated test databases:

- Python compilation for `backend/app` and `backend/scripts`.
- Non-destructive employee portal route/model verification: 22 required routes and 9 required tables.
- Existing health and development-account login tests.
- Existing IT dashboard and company workbook seeding tests.
- Existing Excel/dashboard/replacement report tests.
- Existing IT work and replacement workflow tests.
- Existing role-permission tests.
- Existing manual asset lifecycle test after aligning the test with the current mandatory edit-reason rule.
- Existing component-change and multi-item batch/report tests after aligning test column expectations with the current report schema.
- Existing historical month/report tests.
- Existing Drone preview, import, permission, telemetry, project, dispatch, return, transfer, and work-record tests.
- Existing local backup role-workbook test after aligning the expected Software Team/Admin-equivalent export behavior.
- New registration, email OTP, QR Authenticator, branch selection, IT ticket routing, department isolation, Software Team read-only monitoring, and returning-login test.
- New forgot-password, session invalidation, Software Team ticket handling, user directory, and audit visibility test.

All 17 backend end-to-end tests passed when run in stable grouped sessions. A single monolithic invocation of the stateful test module exceeded the execution environment time limit after six tests; no assertion failure was shown before timeout. The grouped runs cover every collected test.

## Employee isolation verified

The new employee role received `403 Forbidden` for existing department-only endpoints, including:

- dashboard summary;
- IT dashboard;
- asset register;
- work records;
- backup status.

The employee role can use only employee authentication, branch selection, support tickets, notifications, and its own profile/session routes.

## Ticket-routing verification

Verified behavior:

- IT ticket is visible and actionable to IT.
- IT ticket is not visible to Drone.
- IT ticket is visible to Software Team as read-only monitoring.
- Software Team cannot reply to an IT ticket.
- Software Team ticket is fully actionable by Software Team.
- IT cannot view a Software Team ticket.
- Ticket codes use department prefixes such as `NT-IT-...` and `NT-SW-...`.

## Frontend verification

- TypeScript/TSX syntax transpilation passed for all 56 source files.
- New routes, context flows, pages, and matching styles were parsed successfully.
- A full `npm run build` could not be executed in this container because the environment could not resolve the public npm registry (`EAI_AGAIN`) and no `node_modules` or lock file was included in the source archive.

A complete frontend build remains mandatory on the Windows development workstation before merging or deploying:

```powershell
cd frontend
npm install
npm run build
```

## Production activation prerequisites

The code is integrated, but real organization email OTP delivery requires:

- the actual NakshaTech email provider/SMTP host;
- a sender mailbox such as `no-reply@nakshatech.com`;
- the SMTP username/password entered privately in cPanel, never committed or shared in chat;
- a separate random `TOTP_ENCRYPTION_KEY` of at least 32 characters;
- the official branch names/codes inserted before organization-wide rollout.

Only the default `Head Office` branch is seeded because the official branch list was not provided.

## Deployment status

Not deployed to production. The feature remains isolated on `feature/employee-auth-ticket-system` and requires local frontend build, UI review, SMTP configuration, official branch configuration, database backup, and controlled staging/production smoke testing.
