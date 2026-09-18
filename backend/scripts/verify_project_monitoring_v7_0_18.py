from __future__ import annotations

from pathlib import Path
import sys

from fastapi.routing import iter_route_contexts
from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.batch4_main import app
from app.core.database import engine
from app.modules.operations.monitoring_service import STATUS_PROGRESS_ESTIMATE, TECHNICAL_ROLES

expected_routes = {
    ("GET", "/api/operations/project-monitoring/dashboard"),
    ("PATCH", "/api/operations/project-monitoring/workstreams/{workstream_id}/progress"),
    ("PUT", "/api/operations/bd/project-monitoring/handovers/{handover_id}/schedule"),
}
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(expected_routes.difference(actual_routes))
assert not missing, f"Missing V7.0.18 routes: {missing}"
print("V718_PROJECT_MONITORING_ROUTES_OK")

inspector = inspect(engine)
tables = set(inspector.get_table_names())
required_tables = {
    "ops_v715_project_workstreams",
    "ops_v717_project_data_handovers",
    "ops_v718_project_workstream_progress",
    "ops_v718_project_handover_schedule",
}
missing_tables = sorted(required_tables.difference(tables))
assert not missing_tables, f"Missing V7.0.18 monitoring tables: {missing_tables}"
print("V718_PROJECT_MONITORING_TABLES_OK")

expected_technical = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert TECHNICAL_ROLES == expected_technical
assert STATUS_PROGRESS_ESTIMATE == {
    "planned": 0,
    "ready": 10,
    "in_progress": 50,
    "blocked": 50,
    "completed": 100,
}
print("V718_SIX_PEER_DEPARTMENTS_MONITORING_OK")
print("V718_PROGRESS_AGGREGATION_METHOD_OK")

service_source = (BACKEND_ROOT / "app/modules/operations/monitoring_service.py").read_text(encoding="utf-8")
required_source_markers = [
    "PM-reported percentage is used when available",
    "Phase 4 UAT progress updates are restricted",
    "bottleneck_department_label",
    "overdue_handovers",
    "Only the BD owner can manage this project's monitoring schedule",
]
for marker in required_source_markers:
    assert marker in service_source, f"Missing V7.0.18 monitoring source marker: {marker}"
print("V718_BOTTLENECK_AND_OVERDUE_LOGIC_SOURCE_OK")
print("V718_DEMO_PROGRESS_WRITE_GUARD_SOURCE_OK")

ops_router_source = (BACKEND_ROOT / "app/modules/operations/router.py").read_text(encoding="utf-8")
assert "phase4_monitoring_router" in ops_router_source
assert "phase3_handover_router" in ops_router_source
assert "phase2_sample_router" in ops_router_source
print("V718_PHASE2_PHASE3_PHASE4_ROUTER_CHAIN_OK")

print("V718_PHASE4_BACKEND_RUNTIME_OK")
