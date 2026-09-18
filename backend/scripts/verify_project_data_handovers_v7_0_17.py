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
from app.modules.operations.handover_service import (
    DEMO_DEPARTMENT_EMAILS,
    DEMO_EMPLOYEE_IDS,
    HANDOVER_STATUSES,
)

expected_routes = {
    ("GET", "/api/operations/project-handovers/dashboard"),
    ("POST", "/api/operations/bd/project-handovers"),
    ("DELETE", "/api/operations/bd/project-handovers/{handover_id}"),
    ("POST", "/api/operations/project-handovers/{handover_id}/submit"),
    ("POST", "/api/operations/project-handovers/{handover_id}/decision"),
}
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(expected_routes.difference(actual_routes))
assert not missing, f"Missing V7.0.17 routes: {missing}"
print("V717_PROJECT_HANDOVER_ROUTES_OK")

inspector = inspect(engine)
tables = set(inspector.get_table_names())
required_tables = {
    "ops_v715_project_workstreams",
    "ops_v716_technical_sample_requests",
    "ops_v717_project_data_handovers",
    "ops_v717_project_data_handover_attempts",
}
missing_tables = sorted(required_tables.difference(tables))
assert not missing_tables, f"Missing V7.0.17/required tables: {missing_tables}"
print("V717_PROJECT_HANDOVER_TABLES_OK")

expected_codes = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert set(DEMO_DEPARTMENT_EMAILS) == expected_codes
assert set(DEMO_EMPLOYEE_IDS) == expected_codes
assert all(email.endswith(".demo@nakshatech.com") or ".demo@" in email for email in DEMO_DEPARTMENT_EMAILS.values())
print("V717_DEMO_TECHNICAL_RECIPIENT_GUARD_OK")

assert HANDOVER_STATUSES == {"waiting_for_source", "pending_receipt", "revision_requested", "accepted"}
print("V717_HANDOVER_STATE_MACHINE_OK")

service_source = (BACKEND_ROOT / "app/modules/operations/service.py").read_text(encoding="utf-8")
required_source_markers = [
    "V7.0.17 Phase 3 dependency gate",
    "upstream data handover(s) must be accepted",
]
for marker in required_source_markers:
    assert marker in service_source, f"Missing workstream dependency source marker: {marker}"
print("V717_DOWNSTREAM_START_GATE_OK")

router_source = (BACKEND_ROOT / "app/modules/operations/handover_router.py").read_text(encoding="utf-8")
assert "Handover business state commits first" in router_source
assert "db.commit()" in router_source
assert "deliver_receiver_handover_email" in router_source
assert "deliver_sender_decision_email" in router_source
print("V717_NOTIFICATION_EMAIL_NON_BLOCKING_SOURCE_OK")

ops_router_source = (BACKEND_ROOT / "app/modules/operations/router.py").read_text(encoding="utf-8")
assert "phase3_handover_router" in ops_router_source
assert "phase2_sample_router" in ops_router_source
print("V717_PHASE2_AND_PHASE3_ROUTER_CHAIN_OK")

print("V717_PHASE3_BACKEND_RUNTIME_OK")
