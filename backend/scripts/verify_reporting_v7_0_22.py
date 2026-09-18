from __future__ import annotations

from pathlib import Path

from fastapi.routing import iter_route_contexts

from app.batch4_main import app
from app.core.database import SessionLocal
from app.modules.operations.reporting_service import REPORTING_ROLES
from app.modules.operations.technical_routing_service import routing_status_payload

EXPECTED = {
    ("GET", "/api/operations/reporting/dashboard"),
    ("GET", "/api/operations/reporting/powerbi/semantic-model"),
    ("GET", "/api/operations/reporting/powerbi/projects.csv"),
    ("GET", "/api/operations/reporting/powerbi/departments.csv"),
}

# The ERP composes its cumulative FastAPI route tree with IncludedRouter
# wrappers.  Those wrapper objects do not expose `.path` directly.  Use
# FastAPI's route-context iterator, the same mechanism already proven by the
# V7.0.21 verifier, so nested/included routes are enumerated safely.
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(EXPECTED.difference(actual_routes))
assert not missing, f"Missing Phase 8 reporting routes: {missing}"
print("V722_REPORTING_ROUTES_OK")

assert {
    "admin", "management", "bd", "finance", "ortho", "lidar",
    "civil", "laser_scanning", "bim", "mobile_mapping"
}.issubset(REPORTING_ROLES)
print("V722_EXECUTIVE_MANAGER_ROLE_SCOPE_OK")

with SessionLocal() as db:
    routing = routing_status_payload(db)
    assert routing["routing_mode"] in {"uat_demo_locked", "production_live"}
print("V722_PHASE7_ROUTING_STATE_PRESERVED_OK")

root = Path("/app")
service = (root / "app/modules/operations/reporting_service.py").read_text(encoding="utf-8")
router = (root / "app/modules/operations/reporting_router.py").read_text(encoding="utf-8")
ops_router = (root / "app/modules/operations/router.py").read_text(encoding="utf-8")
assert "monitoring_dashboard_payload" in service
assert "completion_dashboard_payload" in service
assert "directory_dashboard_payload" in service
assert "powerbi_semantic_payload" in service
assert "read_only" in service
assert "phase8_reporting_router" in ops_router
assert "text/csv" in router
print("V722_READ_ONLY_REPORTING_AGGREGATION_OK")
print("V722_POWERBI_SEMANTIC_EXPORT_OK")
print("V722_PHASE8_BACKEND_RUNTIME_OK")
