"""Batch 4 runtime entry point.

Batch 4 is cumulative: it starts from the authoritative Batch 3 application and
adds the final Management authority model. Management has read-only operational
visibility and final approval authority only for Purchase Requests.
"""

from fastapi.routing import APIRoute

from app.batch3_main import app
from app.core.config import settings
from app.modules.batch4.router import router as batch4_router


def _route_key(route):
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


def _prefixed_route_key(route):
    """Return the final FastAPI route key after applying the application prefix."""
    if not isinstance(route, APIRoute):
        return None
    prefix = (settings.api_prefix or "").rstrip("/")
    path = route.path if route.path.startswith("/") else f"/{route.path}"
    return f"{prefix}{path}" or "/", frozenset(route.methods or set())


# Determine exactly which existing Batch 3/main handlers Batch 4 supersedes
# before mutating the FastAPI route table. This is more reliable than slicing
# app.router.routes after include_router(), and prevents both missing routes and
# duplicate route-order ambiguity.
_override_keys = {
    key
    for route in batch4_router.routes
    if (key := _prefixed_route_key(route)) is not None
}

app.router.routes[:] = [
    route
    for route in app.router.routes
    if _route_key(route) not in _override_keys
]

# Include the authoritative Batch 4 handlers exactly once after old conflicts
# have been removed. Non-conflicting Batch 3 and colleague routes are preserved.
app.include_router(batch4_router, prefix=settings.api_prefix)
