from __future__ import annotations

from types import SimpleNamespace

from app.core.database import SessionLocal
from app.modules.operations.hardening_service import (
    _json_value,
    audit_snapshot,
    hardening_overview_payload,
    notification_snapshot,
)
from app.modules.operations.technical_routing_service import routing_status_payload


def test_phase9_management_overview_is_read_only_and_preserves_routing_state():
    actor = SimpleNamespace(id=-723, role="management", full_name="Verifier", email="verifier@local.invalid")
    with SessionLocal() as db:
        before = routing_status_payload(db)
        payload = hardening_overview_payload(db, actor=actor, effective_role="management")
        after = routing_status_payload(db)
        assert payload["read_only"] is True
        assert payload["phase"] == "V7.0.23 Phase 9"
        assert before.get("routing_mode") == after.get("routing_mode")
        assert before.get("live_technical_routing_enabled") == after.get("live_technical_routing_enabled")


def test_phase9_audit_view_never_exposes_details_payload_blob():
    with SessionLocal() as db:
        payload = audit_snapshot(db, 10)
        assert payload["available"] is True
        assert payload["sensitive_payloads_exposed"] is False
        for row in payload["recent"]:
            assert "details" not in row
            assert "before_data" not in row
            assert "after_data" not in row


def test_phase9_notification_view_never_exposes_message_body():
    with SessionLocal() as db:
        payload = notification_snapshot(db, 10)
        assert payload["available"] is True
        assert payload["message_bodies_exposed"] is False
        for row in payload["recent"]:
            assert "message" not in row


def test_phase9_json_serializer_handles_dates_and_nested_values():
    from datetime import datetime, timezone
    value = {"at": datetime(2026, 9, 16, tzinfo=timezone.utc), "items": {1, 2}}
    result = _json_value(value)
    assert isinstance(result["at"], str)
    assert sorted(result["items"]) == [1, 2]
