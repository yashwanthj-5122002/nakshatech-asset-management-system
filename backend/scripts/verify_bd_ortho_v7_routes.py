"""Runtime route verifier for NAKSHA ERP V7.0.4.

Why this bootstrap exists:
- V7 used inline ``python -c`` and Windows/PowerShell quoting stripped route quotes.
- V7.0.1 moved verification to this standalone script, but invoking
  ``python /app/scripts/verify_bd_ortho_v7_routes.py`` makes Python place
  ``/app/scripts`` (not ``/app``) at ``sys.path[0]``. That made
  ``from app.batch4_main import app`` fail even though the running backend was
  healthy and already serving ``app.batch4_main:app``.

V7.0.4 explicitly inserts the backend root (the parent of ``scripts``) into
``sys.path`` before importing the application. This makes the verifier
independent of the caller's working directory and avoids shell quoting hacks.
"""

from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
backend_root_text = str(BACKEND_ROOT)
if backend_root_text not in sys.path:
    sys.path.insert(0, backend_root_text)

from fastapi.routing import iter_route_contexts  # noqa: E402
from app.batch4_main import app  # noqa: E402

EXPECTED = {
    "/api/operations/bd/dashboard",
    "/api/operations/ortho/dashboard",
    "/api/operations/ortho/projects",
    "/api/operations/corporate-summary",
}

paths = {context.path for context in iter_route_contexts(app.router.routes)}
missing = sorted(EXPECTED.difference(paths))
if missing:
    raise SystemExit("BD_ORTHO_RUNTIME_ROUTES_MISSING: " + ", ".join(missing))

print("BD_ORTHO_RUNTIME_IMPORT_ROOT_OK:", BACKEND_ROOT)
print("BD_ORTHO_RUNTIME_ROUTES_OK")
