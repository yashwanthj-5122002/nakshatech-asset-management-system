"""Cross-module registration and unauthenticated boundary checks."""
from collections import Counter

from fastapi.routing import APIRoute, iter_route_contexts
from fastapi.testclient import TestClient

from app.batch4_main import app


def _dependencies(dependant):
    yield dependant.call
    for dependency in dependant.dependencies:
        yield from _dependencies(dependency)


def test_every_effective_http_route_has_a_unique_method_and_path():
    operations = Counter(
        (method, context.path)
        for context in iter_route_contexts(app.router.routes)
        if isinstance(context.route, APIRoute)
        for method in context.methods or ()
    )
    duplicates = {f"{method} {path}": count for (method, path), count in operations.items() if count > 1}
    assert not duplicates, duplicates


def test_all_bearer_protected_operations_reject_missing_and_invalid_tokens():
    errors = []
    checked = 0
    with TestClient(app, raise_server_exceptions=False) as client:
        for context in iter_route_contexts(app.router.routes):
            if not isinstance(context.route, APIRoute):
                continue
            names = {getattr(call, "__name__", "") for call in _dependencies(context.route.dependant)}
            if "get_current_auth" not in names:
                continue
            path = context.path
            for parameter in context.route.param_convertors:
                converter = context.route.param_convertors[parameter]
                value = "999999" if type(converter).__name__ in {"IntegerConvertor", "FloatConvertor"} else "qa-missing-record"
                path = path.replace("{" + parameter + "}", value)
                path = path.replace("{" + parameter + ":path}", value)
            for method in context.methods or ():
                for headers in ({}, {"Authorization": "Bearer invalid-qa-token"}):
                    response = client.request(method, path, headers=headers)
                    checked += 1
                    if response.status_code not in {401, 403}:
                        errors.append((method, context.path, response.status_code))
    assert checked > 500, f"Unexpectedly few auth boundary checks: {checked}"
    assert not errors, errors


def test_openapi_can_describe_every_registered_http_operation():
    schema = app.openapi()
    assert schema["openapi"].startswith("3.")
    missing = []
    for context in iter_route_contexts(app.router.routes):
        if not isinstance(context.route, APIRoute) or not context.route.include_in_schema:
            continue
        for method in context.methods or ():
            if method.lower() not in schema["paths"].get(context.path, {}):
                missing.append((method, context.path))
    assert not missing, missing
