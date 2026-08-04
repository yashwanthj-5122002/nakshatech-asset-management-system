# NakshaTech Employee Authentication and Department Ticketing

Feature branch: `feature/employee-auth-ticket-system`  
Base commit: `dc80808`

## What this feature adds

The integration is additive. Existing Admin, Software Team, Management, IT, Drone, asset, reporting, handover, procurement, recent-change, backup, and Excel workflows remain on their existing routes and roles.

### First-time employee flow

1. Open `crm.nakshatech.com` and select **Create account**.
2. Enter an email ending exactly in `@nakshatech.com`.
3. Receive a six-digit OTP through the organization mailbox.
4. Verify the OTP.
5. Enter employee profile information and create a CRM password.
6. Scan the displayed QR code with Google Authenticator, Microsoft Authenticator, 2FAS, or another standards-compatible TOTP application.
7. Enter the current six-digit Authenticator code.
8. Select the branch where the employee is working or where the issue occurred.
9. Open the Employee Support dashboard and raise a department ticket.

No Software Team approval is required for a verified employee support account.

### Returning employee flow

`Organization email + CRM password + phone Authenticator code -> branch selection -> Employee Support dashboard`

The QR-based phone code is free and does not use SMS. Scanning the QR does not reveal the employee's phone number, IMEI, SIM data, contacts, or files.

### Forgot-password flow

`Organization email -> email OTP -> new CRM password -> old sessions invalidated -> normal login + Authenticator`

## Ticket routing and visibility

| Selected destination | Full handling access | Monitoring access | No access |
|---|---|---|---|
| IT | IT | Software Team, read-only | Drone, Management |
| Drone | Drone | Software Team, read-only | IT, Management |
| Management | Management | Software Team, read-only | IT, Drone |
| Software Team | Software Team | Software Team | IT, Drone, Management |

Employees can view and reply only to tickets they raised. The selected department can assign, reply, update status, add resolution notes, resolve, and close. Software Team can view every ticket and its routing information, but cannot reply to or change another department's ticket.

Ticket statuses: `new`, `assigned`, `in_progress`, `waiting_for_employee`, `resolved`, `closed`, `reopened`.

## Software Team visibility

The Software Team dashboard includes:

- verified users and employee profile information;
- account state and Authenticator-enabled state;
- last login and logout timestamps;
- successful and failed authentication events;
- branch selections;
- password-reset completion events;
- important module visits;
- tickets raised, selected department, priority, status, assignment, replies, and resolution history;
- IP address and browser user-agent context for audit events.

It never exposes passwords, password hashes, OTP values, Authenticator secrets, QR secrets, access tokens, session tokens, SMTP credentials, or database credentials.

## Existing-account behavior

Existing accounts and password hashes are preserved. Existing department users are not forced into Authenticator setup during this first rollout. The new `employee` role is isolated from IT, Drone, Management, Admin, and Software Team dashboards.

## New backend routes

- `GET /auth/capabilities`
- `GET /auth/branches`
- `POST /auth/register/request-otp`
- `POST /auth/register/verify-otp`
- `POST /auth/register/complete`
- `POST /auth/mfa/confirm`
- `POST /auth/mfa/verify-login`
- `POST /auth/forgot-password/request-otp`
- `POST /auth/forgot-password/verify-otp`
- `POST /auth/forgot-password/reset`
- `GET /auth/my-branches`
- `POST /auth/select-branch`
- `POST /auth/logout`
- `POST /audit/page-view`
- `GET/POST /tickets`
- `GET/PATCH /tickets/{ticket_id}`
- `POST /tickets/{ticket_id}/messages`
- `GET /notifications`
- `POST /notifications/{notification_id}/read`
- `GET /software/users`
- `GET /software/audit`
- `POST /software/users/{user_id}/reset-authenticator`

## New frontend pages

- Create Account
- Organization Email OTP
- Create CRM Password and Employee Profile
- Phone Authenticator QR Setup
- Authenticator Login Verification
- Forgot Password
- Branch Selection
- Employee Support Dashboard
- Raise Ticket
- My Tickets / Department Ticket Queue / Software Team Monitoring
- Ticket Conversation and Resolution
- Software Team User and Audit Dashboard

All pages reuse the existing NakshaTech welcome/login design language, layout, colors, typography, cards, buttons, and responsive behavior.

## Production environment settings

Do not commit real values to Git. Add secrets only to the cPanel Python App environment or the protected production `.env` file.

```dotenv
EMPLOYEE_PORTAL_ENABLED=true
ALLOWED_EMAIL_DOMAINS=nakshatech.com

EMAIL_DELIVERY_MODE=smtp
SMTP_HOST=mail-provider-host
SMTP_PORT=587
SMTP_USERNAME=no-reply@nakshatech.com
SMTP_PASSWORD=private-value
SMTP_FROM_EMAIL=no-reply@nakshatech.com
SMTP_FROM_NAME=NakshaTech CRM
SMTP_USE_TLS=true
SMTP_USE_SSL=false

EMAIL_OTP_EXPIRY_MINUTES=10
EMAIL_OTP_RESEND_SECONDS=60
EMAIL_OTP_MAX_ATTEMPTS=5
EMAIL_OTP_MAX_REQUESTS_PER_HOUR=5

TOTP_ISSUER=NakshaTech CRM
TOTP_ENCRYPTION_KEY=separate-random-secret-at-least-32-characters
TOTP_VALID_WINDOW=1
```

Use either STARTTLS (`SMTP_USE_TLS=true`, normally port 587) or implicit SSL (`SMTP_USE_SSL=true`, normally port 465), never both.

Production startup intentionally fails when the employee portal is enabled without SMTP or without a separate TOTP encryption key. This prevents a deployment where employees cannot receive OTPs or Authenticator secrets are inadequately protected.

## Branch configuration

The integration creates and preserves a default `Head Office` branch. Additional official branches must be inserted before production rollout so the branch-selection page contains the real choices. No branch names were guessed because the official branch list was not supplied.

## Database behavior

The release adds tables for branches, user-branch access, OTP challenges, Authenticator credentials, sessions, tickets, ticket messages, internal notifications, and audit events. It also adds nullable employee/security fields to the existing `users` table.

The initialization is non-destructive:

- existing users are not deleted;
- existing password hashes are not replaced;
- existing assets and departmental records are not changed;
- existing routes are retained;
- new tables are created with `create_all`;
- new user columns are added only when missing.

A complete database backup is still mandatory before production deployment.

## Local verification

Backend syntax:

```powershell
cd backend
python -m compileall -q app
```

Backend feature tests:

```powershell
python -m pytest -q `
  tests/test_end_to_end.py::test_employee_registration_authenticator_branch_and_ticket_routing `
  tests/test_end_to_end.py::test_employee_password_reset_and_software_ticket_handling
```

Frontend:

```powershell
cd frontend
npm install
npm run build
```

The frontend production build must pass on the development workstation before merging or deploying.

## Rollout order

1. Preserve the current Git branch and database backup.
2. Configure SMTP and a separate TOTP encryption key in staging/local environment.
3. Add the official branch records.
4. Run backend feature tests and the complete frontend production build.
5. Test all existing department logins and workflows.
6. Test registration, email OTP, QR enrollment, branch selection, ticket routing, Software Team read-only monitoring, Software Team ticket handling, and forgot password.
7. Merge into `main` only after review.
8. Deploy backend first, verify health/routes, then deploy the matching frontend.
9. Run a controlled test with one real NakshaTech employee account before enabling organization-wide registration.
