from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# cPanel can execute this file outside the application root. Resolve and add
# the backend root explicitly so imports and .env loading work reliably.
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from app.main import app, initialize_application  # noqa: E402
from app.core.config import settings  # noqa: E402

REQUIRED = [
    "/auth/login",
    "/health",
    "/backups/status",
    "/backups/history",
    "/backups/export.xlsx",
    "/local-backup/health",
    "/local-backup/export.xlsx",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify required CRM API routes.")
    parser.add_argument(
        "--no-initialize",
        action="store_true",
        help="Inspect the imported route tree without running startup initialisation.",
    )
    args = parser.parse_args()

    if not args.no_initialize:
        initialize_application()

    paths = sorted(app.openapi()["paths"])
    prefix = (settings.api_prefix or "").rstrip("/")

    # API_PREFIX is handled once, at application level:
    #   native ASGI (systemd/uvicorn): API_PREFIX=/api   -> routes are /api/...
    #   Passenger mount at /api:      API_PREFIX=        -> routes are /...
    #     (Passenger supplies /api as SCRIPT_NAME; passenger_wsgi.py maps it.)
    expected = [f"{prefix}{path}" for path in REQUIRED]
    missing = [path for path in expected if path not in paths]
    unprefixed_present = [
        path for path in REQUIRED if path in paths and f"{prefix}{path}" != path
    ]

    print(f"Application root: {APP_ROOT}")
    print(f"API_PREFIX: {settings.api_prefix!r} (routes expected under {prefix or '/'})")
    print(f"Passenger mount hint ROOT_PATH: {settings.root_path!r}")
    print("Configured API_PREFIX routes:")
    for path in paths:
        if any(token in path for token in ("auth", "health", "backup")):
            print(path)

    if prefix and unprefixed_present:
        raise SystemExit(
            "Double API mount detected: routes exist both with and without "
            f"{prefix}. Use API_PREFIX={prefix} for native ASGI or an empty "
            "API_PREFIX for the Passenger /api mount, never both."
        )
    if missing:
        raise SystemExit(f"Missing routes: {missing}")
    print("All required routes are present for the configured runtime.")


if __name__ == "__main__":
    main()
