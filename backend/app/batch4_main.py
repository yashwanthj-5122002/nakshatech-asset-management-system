"""Batch 4 runtime entry point.

Batch 4 is cumulative: it starts from the authoritative Batch 3 application and
adds the final Management authority model. Management has read-only operational
visibility and final approval authority only for Purchase Requests.

FastAPI 0.137+ preserves included APIRouters as a live router tree. Batch 4
therefore removes superseded operations from their source routers and then
includes its authoritative router once. It does not rewrite app.router.routes.
"""

from fastapi.routing import APIRoute, iter_route_contexts

from app.batch3_main import app
from app.api.router import router as base_api_router
from app.core.config import settings
from app.modules.batch3.router import router as batch3_router
from app.modules.batch4.router import router as batch4_router


def _route_key(route: object) -> tuple[str, frozenset[str]] | None:
    if not isinstance(route, APIRoute):
        return None
    return route.path, frozenset(route.methods or set())


def _remove_exact_route(router, path: str, methods: frozenset[str]) -> None:
    router.routes[:] = [
        route
        for route in router.routes
        if _route_key(route) != (path, methods)
    ]


# Remove the old operational handlers at their source. Replacement operations
# can exist in both the original API router and Batch 3 router; IT Work lives in
# the original API router. Unique Management control endpoints simply remove
# nothing here.
for route in batch4_router.routes:
    key = _route_key(route)
    if key is None:
        continue
    path, methods = key
    _remove_exact_route(batch3_router, path, methods)
    _remove_exact_route(base_api_router, path, methods)

app.include_router(batch4_router, prefix=settings.api_prefix)


# Public FastAPI route-context traversal is the supported way to inspect the
# effective route tree in FastAPI 0.137.2+. Fail startup if any authoritative
# Batch 4 operation is missing or duplicated.
prefix = (settings.api_prefix or "").rstrip("/")
for route in batch4_router.routes:
    key = _route_key(route)
    if key is None:
        continue
    path, methods = key
    effective_path = f"{prefix}{path}" or "/"
    matches = [
        context
        for context in iter_route_contexts(app.router.routes)
        if context.path == effective_path
        and frozenset(context.methods or set()) == methods
    ]
    if len(matches) != 1:
        raise RuntimeError(
            "Batch 4 authoritative route registration failed: "
            f"{effective_path} {sorted(methods)} count={len(matches)}"
        )
