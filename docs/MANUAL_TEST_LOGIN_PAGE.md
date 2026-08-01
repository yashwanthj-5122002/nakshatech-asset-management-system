# Login Page Manual Test

## Apply

1. Back up the database with `BACKUP_DATABASE_WINDOWS.cmd`.
2. Run `APPLY_LOGIN_PAGE_WINDOWS.cmd`.
3. Open `http://localhost:3100/login`.
4. Press `Ctrl + Shift + R` once.

## Desktop tests

Test at 1920 x 1080, 1440 x 900 and 1366 x 768.

- NakshaTech logo is fully visible.
- Left heading and description are readable.
- Login glass panel is fully visible.
- No control is cut off at the bottom.
- Role selector contains Admin, Management, IT and Drone.
- Back to Welcome returns to `/`.

## Mobile tests

Test Chrome responsive mode at 390 x 844 and 360 x 800.

- Page has no horizontal scrolling.
- Logo fits the header.
- Branding text remains readable.
- Role selector becomes a 2 x 2 grid.
- Email, password and Login controls fit the screen.
- Password eye button works.
- Page can scroll vertically on short screens.

## Authentication tests

Use each existing role and confirm the destination:

- Admin -> Admin dashboard
- Management -> Management dashboard
- IT -> IT dashboard
- Drone -> Drone dashboard

Also confirm:

- Incorrect password displays the backend error.
- Remember Me can be selected and cleared.
- Logout still returns to the unauthenticated application.
- A signed-in user opening `/login` is redirected to their dashboard.

## Regression tests

After login, confirm these routes still open according to role permissions:

- Asset Register
- Add/Edit Asset
- Work Records
- Replacements
- Excel & Reports
- Management dashboard
- Drone dashboard
- Admin dashboard
