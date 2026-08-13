"""Batch 3 runtime entry point.

This preserves the existing application and replaces only the endpoints whose
Batch 3 behavior must be authoritative. Keeping the overrides isolated makes
rollback simple and prevents unrelated colleague features from being rewritten.
"""

from fastapi.routing import APIRoute

from app.main import app
from app.core.config import settings
from app.modules.batch3.router import router as batch3_router


_existing_routes = list(app.router.routes)
app.include_router(batch3_router, prefix=settings.api_prefix)
_batch3_routes = app.router.routes[len(_existing_routes):]


def _route_key(route):
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


_override_keys = {_route_key(route) for route in _batch3_routes}
_override_keys.discard(None)
_kept_routes = []
for route in _existing_routes:
    key = _route_key(route)
    if key is not None and key in _override_keys:
        continue
    _kept_routes.append(route)

# New authoritative Batch 3 handlers are unique in the final route table, so
# runtime dispatch and generated OpenAPI describe the same implementation.
app.router.routes[:] = [*_kept_routes, *_batch3_routes]
