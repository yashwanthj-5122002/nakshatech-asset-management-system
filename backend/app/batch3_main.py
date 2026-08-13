"""Batch 3 runtime entry point.

Batch 3 is cumulative. FastAPI 0.137+ keeps included APIRouters as a live
router tree instead of flattening every APIRoute into app.router.routes. Batch
3 therefore replaces conflicting handlers at their source APIRouter before
including the authoritative Batch 3 router. This preserves every unrelated
application route and avoids depending on FastAPI's internal top-level route
representation.
"""

from fastapi.routing import APIRoute

from app.main import app
from app.api.router import router as base_api_router
from app.core.config import settings
from app.modules.batch3.router import router as batch3_router
from app.modules.it_activity.router import router as it_activity_router


def _route_key(route: object) -> tuple[str, frozenset[str]] | None:
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


def _remove_exact_route(router, path: str, methods: frozenset[str]) -> None:
    """Remove one superseded source-router operation before request serving.

    FastAPI 0.137+ keeps references to included APIRouters. Mutating these
    source routers during application import therefore changes the effective
    route tree without deleting unrelated included routers from the app.
    """
    router.routes[:] = [
        route
        for route in router.routes
        if _route_key(route) != (path, methods)
    ]


# Batch 3 routes under /it-activity supersede endpoints from the dedicated IT
# Activity router. The remaining Batch 3 operational routes supersede matching
# endpoints from the main API router. /batch3/* routes are new and have no
# predecessor to remove.
for route in batch3_router.routes:
    key = _route_key(route)
    if key is None:
        continue
    path, methods = key
    if path.startswith("/batch3/"):
        continue
    if path.startswith("/it-activity/"):
        source_path = path.removeprefix("/it-activity")
        _remove_exact_route(it_activity_router, source_path, methods)
    else:
        _remove_exact_route(base_api_router, path, methods)

# Include Batch 3 exactly once. With FastAPI 0.137+ this becomes one included
# router branch whose original APIRouter remains live for cumulative Batch 4.
app.include_router(batch3_router, prefix=settings.api_prefix)
