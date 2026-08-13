"""Batch 3 runtime entry point.

This preserves the existing application and replaces only the endpoints whose
Batch 3 behavior must be authoritative. Keeping the overrides isolated makes
rollback simple and prevents unrelated colleague features from being rewritten.
"""

from fastapi.routing import APIRoute

from app.main import app
from app.core.config import settings
from app.modules.batch3.router import router as batch3_router


def _route_key(route):
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


def _prefixed_route_key(route):
    if not isinstance(route, APIRoute):
        return None
    prefix = (settings.api_prefix or "").rstrip("/")
    path = route.path if route.path.startswith("/") else f"/{route.path}"
    return f"{prefix}{path}" or "/", frozenset(route.methods or set())


# Determine Batch 3 override keys from the APIRouter itself before mutating the
# application. The earlier implementation sliced app.router.routes after
# include_router(); in the cumulative Batch 4 runtime that could discard the
# application's normal route table. Computing keys first preserves all unrelated
# colleague routes while still replacing only exact path+method conflicts.
_override_keys = {
    key
    for route in batch3_router.routes
    if (key := _prefixed_route_key(route)) is not None
}

app.router.routes[:] = [
    route
    for route in app.router.routes
    if _route_key(route) not in _override_keys
]

# Register authoritative Batch 3 handlers exactly once after conflicts are
# removed. Batch 4 can safely build cumulatively on this preserved application.
app.include_router(batch3_router, prefix=settings.api_prefix)
