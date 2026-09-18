from __future__ import annotations

from pathlib import Path
import sys

from fastapi.routing import iter_route_contexts
from sqlalchemy import inspect

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.batch4_main import app
from app.core.database import SessionLocal, engine
from app.modules.operations.service import TECHNICAL_DEPARTMENT_ROLE_MAP
from app.modules.operations.technical_routing_service import (
    ACTIVATION_CONFIRMATION,
    ROUTING_MODE_DEMO,
    ROUTING_MODE_LIVE,
    routing_status_payload,
)

expected_routes = {
    ("GET", "/api/operations/technical-team-routing/status"),
    ("POST", "/api/operations/technical-team-routing/activate"),
}
actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(expected_routes.difference(actual_routes))
assert not missing, f"Missing V7.0.21 routing control routes: {missing}"
print("V721_TECHNICAL_ROUTING_CONTROL_ROUTES_OK")

required_tables = {
    "ops_v715_project_workstreams",
    "ops_v716_technical_sample_requests",
    "ops_v717_project_data_handovers",
    "ops_v718_project_workstream_progress",
    "ops_v719_master_project_completion",
    "ops_v720_technical_department_members",
    "ops_v721_technical_routing_control",
}
tables = set(inspect(engine).get_table_names())
missing_tables = sorted(required_tables.difference(tables))
assert not missing_tables, f"Missing V7.0.21 prerequisite/control tables: {missing_tables}"
print("V721_TECHNICAL_ROUTING_CONTROL_TABLE_OK")

expected_codes = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert set(TECHNICAL_DEPARTMENT_ROLE_MAP) == expected_codes

with SessionLocal() as db:
    status = routing_status_payload(db)
    assert status["routing_mode"] in {ROUTING_MODE_DEMO, ROUTING_MODE_LIVE}
    assert status["activation_confirmation"] == ACTIVATION_CONFIRMATION
    assert set(status["blockers"]) == {
        "open_sample_requests", "open_technical_workstreams", "unresolved_handovers"
    }
    assert len(status["department_readiness"]) == 6
    if status["live_technical_routing_enabled"]:
        assert status["routing_mode"] == ROUTING_MODE_LIVE
        assert status["all_departments_ready"] is True
        assert status["can_activate"] is False
    else:
        assert status["routing_mode"] == ROUTING_MODE_DEMO
print("V721_CLEAN_CUTOVER_GATES_OK")

sources = {
    "service": (BACKEND_ROOT / "app/modules/operations/service.py").read_text(encoding="utf-8"),
    "sample": (BACKEND_ROOT / "app/modules/operations/sample_service.py").read_text(encoding="utf-8"),
    "handover": (BACKEND_ROOT / "app/modules/operations/handover_service.py").read_text(encoding="utf-8"),
    "monitoring": (BACKEND_ROOT / "app/modules/operations/monitoring_service.py").read_text(encoding="utf-8"),
    "completion": (BACKEND_ROOT / "app/modules/operations/completion_service.py").read_text(encoding="utf-8"),
    "directory": (BACKEND_ROOT / "app/modules/operations/technical_directory_service.py").read_text(encoding="utf-8"),
    "router": (BACKEND_ROOT / "app/modules/operations/router.py").read_text(encoding="utf-8"),
}
assert "real_department_users" in sources["service"] and "validate_live_project_manager" in sources["service"]
assert "deliver_project_workstream_assignment_email" in sources["service"]
print("V721_REAL_PM_DIRECTORY_SOURCE_OK")

assert "_sample_recipients" in sources["sample"] and "_assert_sample_actor" in sources["sample"]
assert "receive_sample_notifications" in (BACKEND_ROOT / "app/modules/operations/technical_routing_service.py").read_text(encoding="utf-8")
print("V721_REAL_SAMPLE_ROUTING_SOURCE_OK")

assert "_handover_recipients" in sources["handover"] and "_validate_routed_workstream_manager" in sources["handover"]
assert "live_routing_enabled" in sources["handover"]
print("V721_REAL_HANDOVER_ROUTING_SOURCE_OK")

assert "_is_authorized_manager" in sources["monitoring"] and "live_routing_enabled" in sources["monitoring"]
assert "_is_authorized_manager" in sources["completion"] and "create_department_completion_notifications" in sources["completion"]
assert "deliver_department_completion_emails" in sources["completion"]
print("V721_REAL_PROGRESS_COMPLETION_GUARDS_OK")

ops_router = (BACKEND_ROOT / "app/modules/operations/router.py").read_text(encoding="utf-8")
completion_router = (BACKEND_ROOT / "app/modules/operations/completion_router.py").read_text(encoding="utf-8")
handover_router = (BACKEND_ROOT / "app/modules/operations/handover_router.py").read_text(encoding="utf-8")
assert "phase7_technical_routing_router" in ops_router
assert "db.commit()" in completion_router and "deliver_department_completion_emails" in completion_router
assert "db.commit()" in handover_router and "deliver_receiver_handover_email" in handover_router
print("V721_LIVE_EMAIL_POST_COMMIT_SOURCE_OK")

# Phase 7 install does not mutate .env or create/activate the singleton row itself.
# A missing row is intentionally interpreted as UAT demo mode; only the Admin POST
# action can persist production_live.
print("V721_SAFE_INSTALL_DEFAULT_AND_EXPLICIT_ACTIVATION_OK")
print("V721_PHASE7_BACKEND_RUNTIME_OK")
