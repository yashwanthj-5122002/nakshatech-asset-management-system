from __future__ import annotations

import inspect

from app.batch4_main import app
from app.modules.finance import service as finance_service
from app.modules.operations import router as operations_router
from app.modules.operations import service as operations_service

routes = {(method, route.path) for route in app.routes for method in getattr(route, "methods", set())}
required = {
    ("POST", "/api/operations/bd/opportunities"),
    ("POST", "/api/operations/bd/opportunities/{opportunity_id}/link-project"),
    ("PATCH", "/api/operations/bd/opportunities/{opportunity_id}/project-manager"),
    ("POST", "/api/operations/ortho/projects/{project_id}/final-delivery"),
}
missing = sorted(required - routes)
assert not missing, f"Missing V7.0.14 routes: {missing}"
print("V714_BD_PROJECT_MANAGER_ROUTES_OK")

fin_src = inspect.getsource(finance_service)
assert "Project Manager is BD-owned" in fin_src
assert "Preserve the existing BD-owned Project Manager" in fin_src
assert "project_manager_id=None" in fin_src
print("V714_FINANCE_PM_WRITE_BLOCKED_OK")

ops_src = inspect.getsource(operations_service)
assert "finance.bd_opportunity.created" in ops_src
assert "finance.project_completed" in ops_src
assert "def assign_bd_project_manager" in ops_src
print("V714_BD_FINANCE_NOTIFICATION_SOURCE_OK")
print("V714_PROJECT_COMPLETION_FINANCE_NOTIFICATION_OK")

router_src = inspect.getsource(operations_router)
assert "deliver_finance_bd_opportunity_emails" in router_src
assert "deliver_finance_project_completion_emails" in router_src
assert "db.commit()" in router_src
print("V714_NOTIFICATION_EMAIL_NON_BLOCKING_SOURCE_OK")
