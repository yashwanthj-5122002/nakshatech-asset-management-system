from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.routing import iter_route_contexts

from app.batch4_main import app
from app.core.database import SessionLocal
from app.modules.operations.hardening_service import HARDENING_ROLES, hardening_overview_payload
from app.modules.operations.technical_routing_service import routing_status_payload

EXPECTED = {
    ("GET", "/api/operations/hardening/overview"),
    ("GET", "/api/operations/hardening/audit"),
    ("GET", "/api/operations/hardening/notifications"),
    ("POST", "/api/operations/hardening/smtp-check"),
}

actual_routes = {
    (method, context.path)
    for context in iter_route_contexts(app.router.routes)
    for method in (context.methods or set())
}
missing = sorted(EXPECTED.difference(actual_routes))
assert not missing, f"Missing Phase 9 hardening routes: {missing}"
print("V723_HARDENING_ROUTES_OK")

assert {"admin", "management", "software_team"}.issubset(HARDENING_ROLES)
print("V723_HARDENING_ROLE_SCOPE_OK")

with SessionLocal() as db:
    before = routing_status_payload(db)
    actor = SimpleNamespace(id=-723, role="management", full_name="Phase 9 Verifier", email="phase9-verifier@local.invalid")
    payload = hardening_overview_payload(db, actor=actor, effective_role="management")
    after = routing_status_payload(db)
    assert payload["read_only"] is True
    assert payload["services"]["database"]["ok"] is True
    assert payload["audit"]["available"] is True
    assert payload["notifications"]["available"] is True
    assert before.get("routing_mode") == after.get("routing_mode")
    assert before.get("live_technical_routing_enabled") == after.get("live_technical_routing_enabled")
    assert payload["optimization"]["count"] > 0
print("V723_AUDIT_VISIBILITY_OK")
print("V723_NOTIFICATION_HEALTH_OK")
print("V723_OPTIMIZATION_INDEXES_OK")
print("V723_PHASE7_ROUTING_PRESERVED_OK")

root = Path("/app")
service = (root / "app/modules/operations/hardening_service.py").read_text(encoding="utf-8")
router = (root / "app/modules/operations/hardening_router.py").read_text(encoding="utf-8")
ops_router = (root / "app/modules/operations/router.py").read_text(encoding="utf-8")
assert "reporting_service.py" in service
assert "smtp_auth_probe" in service
assert "audit_snapshot" in service
assert "notification_snapshot" in service
assert "PHASE9_SMTP_AUTH_DIAGNOSTIC" in router
assert "phase9_hardening_router" in ops_router
assert (root / "app/modules/operations/reporting_service.py").exists()
print("V723_PHASE8_REPORTING_PRESERVED_OK")
print("V723_SECURITY_READINESS_SOURCE_OK")
print("V723_PHASE9_BACKEND_RUNTIME_OK")
