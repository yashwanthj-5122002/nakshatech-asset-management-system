# NakshaTech Login Page Integration

## Scope

The existing login presentation was replaced with the approved dark geospatial login experience while keeping the application authentication and role-routing workflow intact.

## Integrated design

- Same dark world-map background used by the confirmed welcome page
- Updated horizontal NakshaTech logo and Asset Management System label
- Left-side Smart Internal Asset Management branding
- Right-side glassmorphism login panel
- Back to Welcome navigation
- Admin, Management, IT and Drone role selection
- Email/username and password inputs
- Password show/hide control
- Remember Me option
- Helpful password-reset guidance without introducing a non-functional reset API
- Dynamic copyright year

## Preserved workflow

- Existing `/auth/login` API request
- Existing role credentials and role selection behaviour
- Existing JWT and authenticated-user handling
- Existing redirects:
  - Admin -> `/admin`
  - Management -> `/management`
  - IT -> `/it`
  - Drone -> `/drone`
- Existing protected routes and permissions
- Existing welcome page route at `/`
- Existing dashboards, asset register, work records, replacements and reports

## Responsive behaviour

- Desktop: branding on the left and login panel on the right
- Tablet: reduced spacing with the complete panel retained
- Mobile: stacked layout, compact brand header, glass branding block and a 2 x 2 role selector
- No horizontal page expansion below the supported 320 px minimum width
- Short desktop screens receive reduced panel spacing to keep the submit button visible

## Files changed

- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/styles.css`

## Files added

- `APPLY_LOGIN_PAGE_WINDOWS.cmd`
- `docs/LOGIN_PAGE_INTEGRATION.md`
- `docs/MANUAL_TEST_LOGIN_PAGE.md`
- `VERIFICATION_LOGIN_PAGE.txt`

## Approved visual reference

The design reference supplied for this integration is retained at:

- `docs/LOGIN_PAGE_APPROVED_REFERENCE.png`
