
import ast
import re
import shutil
import tempfile

from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent

main_path = ROOT / "backend/app/main.py"
app_path = ROOT / "frontend/src/App.tsx"
layout_path = ROOT / "frontend/src/components/Layout.tsx"

module_path = (
    ROOT / "backend/app/modules/organisation_policies/router.py"
)

page_path = (
    ROOT
    / "frontend/src/features/organisation_policies/OrganisationPoliciesPage.tsx"
)

css_path = (
    ROOT
    / "frontend/src/features/organisation_policies/organisation-policies.css"
)

required_files = [
    main_path,
    app_path,
    layout_path,
    module_path,
    page_path,
    css_path,
]

for path in required_files:
    if not path.is_file():
        raise SystemExit(f"STOP: Required file missing: {path}")


def read(path):
    return path.read_text(encoding="utf-8-sig")


def unique_match(source, pattern, label):
    matches = list(re.finditer(pattern, source, re.MULTILINE))

    if len(matches) != 1:
        raise SystemExit(
            f"STOP: Expected one {label}, found {len(matches)}. "
            "No existing source files have been changed."
        )

    return matches[0]


def insert_after(source, pattern, addition, label):
    match = unique_match(source, pattern, label)

    return (
        source[:match.end()]
        + "\n"
        + addition
        + source[match.end():]
    )


main = read(main_path)
app = read(app_path)
layout = read(layout_path)

markers = [
    "NAKSHA_ORG_POLICIES_BACKEND" in main,
    "NAKSHA_ORG_POLICIES_ROUTE" in app,
    "NAKSHA_ORG_POLICIES_NAV" in layout,
]

if all(markers):
    raise SystemExit("Organisation Policies already wired.")

if any(markers):
    raise SystemExit(
        "STOP: Partial previous installation detected."
    )

if (
    "organisation_policies_router" in main
    or "OrganisationPoliciesPage" in app
    or "/organisation-policies" in layout
):
    raise SystemExit(
        "STOP: Existing Organisation Policies integration detected."
    )

# Validate the new Python module first.
ast.parse(read(module_path))

# ------------------------------------------------------------
# BACKEND IMPORT
# ------------------------------------------------------------

main = insert_after(
    main,
    r"^from app\.modules\.notifications\.router import router as notification_router[^\n]*$",
    (
        "from app.modules.organisation_policies.router import "
        "router as organisation_policies_router, with_policy_lifespan "
        "# NAKSHA_ORG_POLICIES_BACKEND"
    ),
    "notification router import",
)

# Register the new API.
main = insert_after(
    main,
    r"^app\.include_router\(notification_router,\s*prefix=settings\.api_prefix\)[^\n]*$",
    "app.include_router(organisation_policies_router, prefix=settings.api_prefix)",
    "notification router registration",
)

# Preserve the existing lifecycle and add the policy worker.
match = unique_match(
    main,
    r"^([ \t]*)lifespan=lifespan,[ \t]*$",
    "existing FastAPI lifespan",
)

main = (
    main[:match.start()]
    + match.group(1)
    + "lifespan=with_policy_lifespan(lifespan),"
    + main[match.end():]
)

ast.parse(main)

# ------------------------------------------------------------
# REACT IMPORT AND ROUTE
# ------------------------------------------------------------

app = (
    "import { OrganisationPoliciesPage } from "
    "'./features/organisation_policies/OrganisationPoliciesPage'\n"
    + app
)

if not re.search(
    r"import\s*\{[^}]*\bStrictProtectedRoute\b[^}]*\}\s*from",
    app,
):
    app = (
        "import { StrictProtectedRoute } from "
        "'./components/StrictProtectedRoute'\n"
        + app
    )

match = unique_match(
    app,
    r'^[ \t]*<Route\s+path=["\']/hrms/hr["\']',
    "existing HRMS route",
)

new_route = (
    "      {/* NAKSHA_ORG_POLICIES_ROUTE */}\n"
    '      <Route path="/organisation-policies" '
    "element={<StrictProtectedRoute roles={['hr', 'employee']}>"
    "<WithLayout><OrganisationPoliciesPage /></WithLayout>"
    "</StrictProtectedRoute>} />\n"
)

app = app[:match.start()] + new_route + app[match.start():]

# ------------------------------------------------------------
# SIDEBAR
# ------------------------------------------------------------

layout = insert_after(
    layout,
    r"^[ \t]*\{[^\n]*\bto:\s*['\"]/hrms/hr['\"][^\n]*$",
    (
        "  // NAKSHA_ORG_POLICIES_NAV\n"
        "  { to: '/organisation-policies', "
        "label: 'Organisation Policies', "
        "icon: FileCheck2, roles: ['hr', 'employee'], "
        "group: 'hr' },"
    ),
    "HR sidebar item",
)

# Exact role visibility, without affecting legacy permissions.
layout = insert_after(
    layout,
    r"^function canViewItem\(role: Role, item: NavItem\): boolean \{[ \t]*$",
    (
        "  if (item.to === '/organisation-policies') "
        "return role === 'hr' || role === 'employee'"
    ),
    "sidebar permission function",
)

# ------------------------------------------------------------
# BACKUP BEFORE WRITING
# ------------------------------------------------------------

backup = (
    Path(tempfile.gettempdir())
    / (
        "NakshaTech-organisation-policies-"
        + datetime.now().strftime("%Y%m%d-%H%M%S")
    )
)

for path in [main_path, app_path, layout_path]:
    destination = backup / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)

changes = [
    (main_path, main),
    (app_path, app),
    (layout_path, layout),
]

try:
    for path, source in changes:
        path.write_text(source, encoding="utf-8")
        print("PATCHED:", path.relative_to(ROOT))

except Exception:
    for path in [main_path, app_path, layout_path]:
        shutil.copy2(
            backup / path.relative_to(ROOT),
            path,
        )
    raise

print()
print("ORGANISATION POLICIES INTEGRATION COMPLETE")
print("Source backup:", backup)
print("Next: validate Python and build the frontend.")
