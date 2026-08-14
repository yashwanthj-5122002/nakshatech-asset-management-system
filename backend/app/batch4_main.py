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


def _batch4_effective_route_contexts():
    """Return every leaf operation in Batch 4, including nested routers.

    FastAPI 0.137+ no longer flattens ``include_router()`` into direct
    ``APIRoute`` entries. The Asset Return module is nested under Batch 4, so
    iterating ``batch4_router.routes`` directly misses its /assets,
    /dashboard/it and report overrides and leaves the older handlers able to
    win request dispatch by route order.
    """
    return list(iter_route_contexts(batch4_router.routes))


# Remove older handlers at their source before Batch 4 is included. This must
# traverse the complete nested Batch 4 route tree: the Return / Remove module,
# its mutation guards and its active-inventory dashboard/report handlers are
# included routers rather than direct APIRoute objects on FastAPI 0.137.2.
for context in _batch4_effective_route_contexts():
    methods = frozenset(context.methods or set())
    _remove_exact_route(batch3_router, context.path, methods)
    _remove_exact_route(base_api_router, context.path, methods)

app.include_router(batch4_router, prefix=settings.api_prefix)


# Public FastAPI route-context traversal is the supported way to inspect the
# effective route tree in FastAPI 0.137.2+. Fail startup if any authoritative
# Batch 4 operation -- including nested Return / Remove routes -- is missing,
# duplicated or shadowed by an older endpoint.
prefix = (settings.api_prefix or "").rstrip("/")
for expected in _batch4_effective_route_contexts():
    methods = frozenset(expected.methods or set())
    effective_path = f"{prefix}{expected.path}" or "/"
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
    if matches[0].endpoint is not expected.endpoint:
        actual_name = getattr(matches[0].endpoint, "__name__", repr(matches[0].endpoint))
        expected_name = getattr(expected.endpoint, "__name__", repr(expected.endpoint))
        raise RuntimeError(
            "Batch 4 route shadowing detected: "
            f"{effective_path} {sorted(methods)} expected={expected_name} actual={actual_name}"
        )
