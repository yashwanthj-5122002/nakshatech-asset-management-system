from __future__ import annotations

from pathlib import Path
import sys

from fastapi.routing import iter_route_contexts
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.batch4_main import app
from app.core.database import SessionLocal, engine
from app.core.roles import VALID_ROLES
from app.models.entities import User
from app.modules.operations.models import ProjectWorkstream
from app.modules.operations.service import TECHNICAL_DEPARTMENT_ROLE_MAP

required_roles = {"ortho", "lidar", "civil", "laser_scanning", "bim", "mobile_mapping"}
assert required_roles.issubset(VALID_ROLES), f"Missing technical roles: {sorted(required_roles - VALID_ROLES)}"
print("V715_TECHNICAL_LOGIN_ROLES_OK")

routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
required_routes = {
    ("GET", "/api/operations/project-workstreams/dashboard"),
    ("PUT", "/api/operations/bd/opportunities/{opportunity_id}/workstreams"),
    ("PATCH", "/api/operations/project-workstreams/{workstream_id}/status"),
}
missing = sorted(required_routes - routes)
assert not missing, f"Missing Phase 1 routes: {missing}"
print("V715_PROJECT_WORKSTREAM_ROUTES_OK")

assert inspect(engine).has_table(ProjectWorkstream.__tablename__), "Project workstream table was not created"
print("V715_PROJECT_WORKSTREAM_TABLE_OK")

expected = {
    "ortho": "ortho",
    "lidar": "lidar",
    "civil": "civil",
    "laser_scanning": "laser_scanning",
    "bim": "bim",
    "mobile_mapping": "mobile_mapping",
}
assert TECHNICAL_DEPARTMENT_ROLE_MAP == expected
assert TECHNICAL_DEPARTMENT_ROLE_MAP["ortho"] != TECHNICAL_DEPARTMENT_ROLE_MAP["lidar"]
print("V715_DEPARTMENT_ROLE_MAPPING_OK")
print("V715_ORTHO_LIDAR_SEPARATE_OK")

demo_ids = {
    "DEMO-V715-ORTHO-PM": ("ortho.demo@nakshatech.com", "ortho"),
    "DEMO-V715-LIDAR-PM": ("lidar.demo@nakshatech.com", "lidar"),
    "DEMO-V715-CIVIL-PM": ("civil.demo@nakshatech.com", "civil"),
    "DEMO-V715-LASER-PM": ("laser.scanning.demo@nakshatech.com", "laser_scanning"),
    "DEMO-V715-BIM-PM": ("bim.demo@nakshatech.com", "bim"),
    "DEMO-V715-MOBILE-PM": ("mobile.mapping.demo@nakshatech.com", "mobile_mapping"),
}
with SessionLocal() as db:
    rows = list(db.scalars(select(User).where(User.employee_id.in_(demo_ids))).all())
    found = {row.employee_id: (row.email, row.role) for row in rows}
    assert found == demo_ids, f"Demo technical accounts missing/mismatched: {found}"
print("V715_DEMO_TECHNICAL_USERS_OK")

# Validate the real login endpoint for every reserved demo technical identity.
client = TestClient(app)
for _employee_id, (email, role) in demo_ids.items():
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Phase1Demo@2026!"},
    )
    assert response.status_code == 200, f"Demo login failed for {email}: {response.status_code} {response.text}"
    payload = response.json()
    assert payload.get("user", {}).get("role") == role, f"Unexpected role for {email}: {payload}"
    assert payload.get("access_token"), f"No access token issued for {email}"
print("V715_ALL_SIX_DEMO_LOGINS_OK")
print("V715_PHASE1_RUNTIME_OK")
