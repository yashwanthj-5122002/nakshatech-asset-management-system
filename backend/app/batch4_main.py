"""Batch 4 runtime entry point.

Batch 4 is cumulative: it starts from the authoritative Batch 3 application and
adds the final Management authority model. Management has read-only operational
visibility and final approval authority only for Purchase Requests.
"""

from fastapi import APIRouter
from fastapi.routing import APIRoute

from app.batch3_main import app
from app.core.config import settings
from app.modules.batch4.router import router as batch4_router


def _route_key(route):
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


# Stage prefixed copies of the Batch 4 routes in an isolated APIRouter first.
# This avoids relying on FastAPI.include_router() while the live route table is
# also being rewritten for authoritative endpoint overrides.
_staged_router = APIRouter()
_staged_router.include_router(batch4_router, prefix=settings.api_prefix)
_staged_routes = list(_staged_router.routes)
_override_keys = {
    key
    for route in _staged_routes
    if (key := _route_key(route)) is not None
}

# Remove only exact path+method conflicts from Batch 3/main. Every unrelated
# colleague route remains untouched.
app.router.routes[:] = [
    route
    for route in app.router.routes
    if _route_key(route) not in _override_keys
]

# Append the already-prefixed authoritative Batch 4 APIRoutes directly. This is
# deterministic and avoids route-loss behavior observed when include_router()
# and route-table mutation were combined in the same runtime module.
app.router.routes.extend(_staged_routes)

# Fail loudly during startup/test import if an authoritative Batch 4 route is
# missing or duplicated. A silent fallback to an older approval workflow is a
# security/business-rule defect, so the application must not start in that
# state.
_final_counts: dict[tuple[str, frozenset[str]], int] = {}
for route in app.router.routes:
    key = _route_key(route)
    if key is not None:
        _final_counts[key] = _final_counts.get(key, 0) + 1

_invalid = {
    key: _final_counts.get(key, 0)
    for key in _override_keys
    if _final_counts.get(key, 0) != 1
}
if _invalid:
    detail = ", ".join(
        f"{path} {sorted(methods)} count={count}"
        for (path, methods), count in sorted(_invalid.items(), key=lambda item: item[0][0])
    )
    raise RuntimeError(f"Batch 4 authoritative route registration failed: {detail}")
