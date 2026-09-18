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
from app.modules.operations.service import TECHNICAL_DEPARTMENT_ROLE_MAP
from app.modules.operations.technical_directory_service import (
    LIVE_TECHNICAL_ROUTING_ENABLED,
    TECHNICAL_ROUTING_MODE,
)

expected_routes = {
    ("GET", "/api/operations/technical-team-directory/dashboard"),
    ("POST", "/api/operations/technical-team-directory/departments/{department_code}/members"),
    ("PATCH", "/api/operations/technical-team-directory/members/{member_id}"),
    ("DELETE", "/api/operations/technical-team-directory/members/{member_id}"),
}
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(expected_routes.difference(actual_routes))
assert not missing, f"Missing V7.0.20 routes: {missing}"
print("V720_TECHNICAL_DIRECTORY_ROUTES_OK")

required_tables = {
    "ops_v715_project_workstreams",
    "ops_v716_technical_sample_requests",
    "ops_v717_project_data_handovers",
    "ops_v718_project_workstream_progress",
    "ops_v719_master_project_completion",
    "ops_v720_technical_department_members",
}
tables = set(inspect(engine).get_table_names())
missing_tables = sorted(required_tables.difference(tables))
assert not missing_tables, f"Missing V7.0.20 prerequisite/directory tables: {missing_tables}"
print("V720_TECHNICAL_DIRECTORY_TABLE_OK")

expected_codes = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert set(TECHNICAL_DEPARTMENT_ROLE_MAP) == expected_codes
print("V720_SIX_PEER_DEPARTMENTS_DIRECTORY_OK")

assert LIVE_TECHNICAL_ROUTING_ENABLED is False
assert TECHNICAL_ROUTING_MODE == "uat_demo_locked"
print("V720_LIVE_ROUTING_STAYS_LOCKED_OK")

sample_source = (BACKEND_ROOT / "app/modules/operations/sample_service.py").read_text(encoding="utf-8")
handover_source = (BACKEND_ROOT / "app/modules/operations/handover_service.py").read_text(encoding="utf-8")
monitoring_source = (BACKEND_ROOT / "app/modules/operations/monitoring_service.py").read_text(encoding="utf-8")
completion_source = (BACKEND_ROOT / "app/modules/operations/completion_service.py").read_text(encoding="utf-8")
assert "DEMO_DEPARTMENT_EMAILS" in sample_source and "_demo_user_for_department" in sample_source
assert "DEMO_DEPARTMENT_EMAILS" in handover_source and "_demo_user_for_department" in handover_source
assert "_is_reserved_demo_manager" in monitoring_source
assert "_is_reserved_demo_manager" in completion_source
assert "technical_directory_service" not in sample_source
assert "technical_directory_service" not in handover_source
assert "technical_directory_service" not in monitoring_source
assert "technical_directory_service" not in completion_source
print("V720_EXISTING_DEMO_ROUTING_UNCHANGED_OK")

router_source = (BACKEND_ROOT / "app/modules/operations/technical_directory_router.py").read_text(encoding="utf-8")
assert '_exact_roles(auth, "admin")' in router_source
assert "live_routing_enabled\": False" in router_source
print("V720_ADMIN_WRITE_READONLY_OVERSIGHT_SOURCE_OK")

print("V720_PHASE6_BACKEND_RUNTIME_OK")
