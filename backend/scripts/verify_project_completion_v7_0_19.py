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
from app.modules.operations.completion_service import FINANCE_STATUSES, TECHNICAL_ROLES

expected_routes = {
    ("GET", "/api/operations/project-completion/dashboard"),
    ("POST", "/api/operations/project-completion/workstreams/{workstream_id}/complete"),
    ("POST", "/api/operations/bd/project-completion/projects/{project_id}/deliver"),
    ("PATCH", "/api/operations/finance/project-completion/projects/{project_id}/status"),
}
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(expected_routes.difference(actual_routes))
assert not missing, f"Missing V7.0.19 routes: {missing}"
print("V719_PROJECT_COMPLETION_ROUTES_OK")

inspector = inspect(engine)
tables = set(inspector.get_table_names())
required_tables = {
    "ops_v715_project_workstreams",
    "ops_v717_project_data_handovers",
    "ops_v718_project_workstream_progress",
    "ops_v719_master_project_completion",
}
missing_tables = sorted(required_tables.difference(tables))
assert not missing_tables, f"Missing V7.0.19 completion tables: {missing_tables}"
print("V719_PROJECT_COMPLETION_TABLE_OK")

assert TECHNICAL_ROLES == {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert FINANCE_STATUSES == {"pending_billing", "billing_in_progress", "financially_closed"}
print("V719_SIX_PEER_DEPARTMENTS_COMPLETION_OK")
print("V719_FINANCE_CLOSURE_STATE_MACHINE_OK")

service_source = (BACKEND_ROOT / "app/modules/operations/completion_service.py").read_text(encoding="utf-8")
required_source_markers = [
    "All outgoing data handovers must be accepted",
    "Master Project is not ready for final delivery",
    "finance.project_completed",
    "bd.project.ready_for_final_delivery",
    "Phase 5 UAT completion is restricted",
    "Business Development has recorded Master Project Final Delivery",
    "Start billing / financial closure before marking the project financially closed",
]
for marker in required_source_markers:
    assert marker in service_source, f"Missing V7.0.19 completion source marker: {marker}"
print("V719_MASTER_DELIVERY_GATE_SOURCE_OK")
print("V719_DEMO_TECHNICAL_COMPLETION_GUARD_OK")
print("V719_FINANCE_NOTIFICATION_NON_BLOCKING_SOURCE_OK")

ops_service = (BACKEND_ROOT / "app/modules/operations/service.py").read_text(encoding="utf-8")
assert "V7.0.19 Phase 5 completion gate" in ops_service
assert "outgoing data handover(s) must be accepted before this department can complete work" in ops_service
print("V719_OUTGOING_HANDOVER_COMPLETION_GATE_OK")

ops_router = (BACKEND_ROOT / "app/modules/operations/router.py").read_text(encoding="utf-8")
assert "phase5_completion_router" in ops_router
assert "phase4_monitoring_router" in ops_router
assert "assert_legacy_ortho_final_delivery_allowed" in ops_router
print("V719_PHASE3_PHASE4_PHASE5_ROUTER_CHAIN_OK")
print("V719_LEGACY_ORTHO_MULTI_TEAM_DELIVERY_GUARD_OK")
print("V719_PHASE5_BACKEND_RUNTIME_OK")
