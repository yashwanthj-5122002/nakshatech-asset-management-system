from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app

EXPECTED_PATHS = {
    "/api/dashboard/it/assets",
    "/api/reports/it-dashboard-assets.xlsx",
}


def collect_route_paths(routes: Iterable[object]) -> set[str]:
    """Collect paths safely, including nested/custom router wrappers."""
    found: set[str] = set()
    for route in routes:
        path = getattr(route, "path", None)
        if isinstance(path, str) and path:
            found.add(path)
        nested = getattr(route, "routes", None)
        if nested:
            found.update(collect_route_paths(nested))
    return found


def main() -> None:
    discovered = collect_route_paths(app.routes)
    openapi_error: str | None = None
    try:
        discovered.update(app.openapi().get("paths", {}).keys())
    except Exception as exc:  # route-tree inspection above remains available
        openapi_error = f"{type(exc).__name__}: {exc}"

    missing = EXPECTED_PATHS - discovered
    if missing:
        details = f" Missing routes: {sorted(missing)}."
        if openapi_error:
            details += f" OpenAPI inspection error: {openapi_error}."
        raise SystemExit("DRILL-DOWN API ROUTE VERIFICATION FAILED." + details)

    print("DRILL-DOWN API ROUTES REGISTERED")
    for path in sorted(EXPECTED_PATHS):
        print(f"- {path}")


if __name__ == "__main__":
    main()
