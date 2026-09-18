from __future__ import annotations

import inspect
from pathlib import Path

from fastapi.routing import iter_route_contexts
from sqlalchemy import inspect as sa_inspect, select

from app.batch4_main import app
from app.core.database import SessionLocal, engine
from app.models.entities import User
from app.modules.operations import router as operations_router
from app.modules.operations import sample_router, sample_service
from app.modules.operations.sample_models import TechnicalSampleRequest

routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
required = {
    ("GET", "/api/operations/samples/dashboard"),
    ("POST", "/api/operations/bd/opportunities/{opportunity_id}/samples"),
    ("POST", "/api/operations/samples/{sample_request_id}/start"),
    ("POST", "/api/operations/samples/{sample_request_id}/submit"),
    ("POST", "/api/operations/samples/{sample_request_id}/client-review"),
    ("POST", "/api/operations/samples/{sample_request_id}/client-decision"),
}
missing = sorted(required - routes)
assert not missing, f"Missing V7.0.16 Phase 2 routes: {missing}"
print("V716_SAMPLE_WORKFLOW_ROUTES_OK")

inspector = sa_inspect(engine)
tables = set(inspector.get_table_names())
required_tables = {
    "ops_v716_technical_sample_requests",
    "ops_v716_technical_sample_departments",
    "ops_v716_technical_sample_submissions",
}
assert required_tables.issubset(tables), f"Missing Phase 2 tables: {sorted(required_tables - tables)}"
print("V716_SAMPLE_WORKFLOW_TABLES_OK")

with SessionLocal() as db:
    for department_code, email in sample_service.DEMO_DEPARTMENT_EMAILS.items():
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None, f"Missing Phase 2 demo technical account: {email}"
        assert user.employee_id == sample_service.DEMO_EMPLOYEE_IDS[department_code]
        assert user.role == sample_service.TECHNICAL_DEPARTMENT_ROLE_MAP[department_code]
        assert user.is_active and user.account_status == "active"
print("V716_DEMO_TEAM_RECIPIENTS_OK")

create_source = inspect.getsource(operations_router.bd_create_opportunity)
assert "create_finance_bd_opportunity_notifications" not in create_source
assert "deliver_finance_bd_opportunity_emails" not in create_source
print("V716_FINANCE_NOTIFICATION_TIMING_OK")

sample_router_source = inspect.getsource(sample_router)
assert "create_finance_client_approved_notifications" in sample_router_source
assert "client-decision" in sample_router_source
assert "revision_notifications_created" in sample_router_source
print("V716_CLIENT_APPROVAL_FINANCE_HANDOFF_OK")

sample_service_source = inspect.getsource(sample_service)
for marker in (
    "DEMO_DEPARTMENT_EMAILS",
    "Phase 2 UAT",
    "client_sample_revision_requested",
    "client_sample_approved_finance_handoff",
    "finance.bd_opportunity.client_approved",
):
    assert marker in sample_service_source, marker
print("V716_DEMO_ONLY_SAMPLE_NOTIFICATION_SOURCE_OK")

print("V716_BACKEND_RUNTIME_OK")
