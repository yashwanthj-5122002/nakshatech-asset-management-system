from __future__ import annotations

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

initialize_application()
paths = sorted(app.openapi()["paths"])
required = [
    "/auth/login",
    "/health",
    "/backups/status",
    "/backups/history",
    "/backups/export.xlsx",
    "/local-backup/health",
    "/local-backup/export.xlsx",
]
missing = [path for path in required if path not in paths]
print(f"Application root: {APP_ROOT}")
print("Configured API_PREFIX routes:")
for path in paths:
    if any(token in path for token in ("auth", "health", "backup")):
        print(path)
if missing:
    raise SystemExit(f"Missing routes: {missing}")
print("All required cPanel routes are present.")
