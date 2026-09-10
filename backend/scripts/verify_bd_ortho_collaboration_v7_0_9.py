"""Runtime verifier for V7.0.9 Ortho role collaboration.

Runs inside the existing backend container after the V7.0.9 source is installed.
It verifies the actual Batch-4 route tree, the additive daily-update table and the
existing ERP email delivery mode without printing SMTP credentials.
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
backend_root_text = str(BACKEND_ROOT)
if backend_root_text not in sys.path:
    sys.path.insert(0, backend_root_text)

from fastapi.routing import iter_route_contexts  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.batch4_main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import engine  # noqa: E402
from app.modules.operations.models import OrthoDailyUpdate  # noqa: E402

EXPECTED = {
    "/api/operations/ortho/dashboard",
    "/api/operations/ortho/projects",
    "/api/operations/ortho/projects/{project_id}/members",
    "/api/operations/ortho/work-packages/{work_package_id}/daily-update",
    "/api/operations/ortho/work-packages/{work_package_id}/work-action",
    "/api/operations/ortho/work-packages/{work_package_id}/submit-qc",
    "/api/operations/ortho/work-packages/{work_package_id}/qc",
    "/api/operations/ortho/work-packages/{work_package_id}/qa",
    "/api/operations/ortho/projects/{project_id}/final-delivery",
}

paths = {context.path for context in iter_route_contexts(app.router.routes)}
missing = sorted(EXPECTED.difference(paths))
if missing:
    raise SystemExit("V709_ORTHO_COLLABORATION_ROUTES_MISSING: " + ", ".join(missing))

if OrthoDailyUpdate.__tablename__ != "ops_v709_ortho_daily_updates":
    raise SystemExit("V709_DAILY_UPDATE_MODEL_TABLE_MISMATCH")

with engine.connect() as connection:
    tables = set(inspect(connection).get_table_names())
if OrthoDailyUpdate.__tablename__ not in tables:
    raise SystemExit("V709_DAILY_UPDATE_TABLE_MISSING")

mode = settings.email_delivery_mode.strip().lower()
if mode not in {"smtp", "console", "log"}:
    raise SystemExit(f"V709_ORTHO_ASSIGNMENT_EMAIL_MODE_INVALID: {mode or '<empty>'}")

print("V709_ORTHO_ROLE_COLLABORATION_ROUTES_OK")
print("V709_DAILY_UPDATE_TABLE_OK")
if mode == "smtp":
    print("V709_ORTHO_ASSIGNMENT_EMAIL_MODE_OK: smtp")
else:
    print(f"V709_ORTHO_ASSIGNMENT_EMAIL_MODE_WARNING: {mode} (assignment emails are logged instead of delivered)")
