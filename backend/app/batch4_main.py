"""Batch 4 runtime entry point.

Batch 4 is cumulative: it starts from the authoritative Batch 3 application and
adds the final Management authority model. Management has read-only operational
visibility and final approval authority only for Purchase Requests.
"""

from fastapi.routing import APIRoute

from app.batch3_main import app
from app.core.config import settings
from app.modules.batch4.router import router as batch4_router


_existing_routes = list(app.router.routes)
app.include_router(batch4_router, prefix=settings.api_prefix)
_batch4_routes = app.router.routes[len(_existing_routes):]


def _route_key(route):
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


_override_keys = {_route_key(route) for route in _batch4_routes}
_override_keys.discard(None)
_kept_routes = []
for route in _existing_routes:
    key = _route_key(route)
    if key is not None and key in _override_keys:
        continue
    _kept_routes.append(route)

# Batch 4 handlers replace the old IT Work / Replacement approval endpoints so
# runtime dispatch and OpenAPI expose one unambiguous authority model.
app.router.routes[:] = [*_kept_routes, *_batch4_routes]
