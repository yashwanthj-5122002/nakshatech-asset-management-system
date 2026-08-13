from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.it_activity.router import add_handover_record
from app.modules.it_activity.schemas import HandoverCreate


class _StubSession:
    def __init__(self, asset):
        self.asset = asset

    def get(self, _model, _asset_id):
        return self.asset


def _payload(*, asset_id: int = 1, device_category: str = "desktop") -> HandoverCreate:
    return HandoverCreate(
        asset_id=asset_id,
        device_category=device_category,
        employee_name="QA Custodian",
        dc_number="QA-WS-001",
        department="IT",
        work_mode="office",
        action_type="handover",
        activity_date=date.today(),
    )


def test_live_custody_rejects_non_laptop_desktop_asset() -> None:
    db = _StubSession(SimpleNamespace(device_type="Smartphone"))
    user = SimpleNamespace()

    with pytest.raises(HTTPException) as exc:
        add_handover_record(_payload(device_category="desktop"), db, user)

    assert exc.value.status_code == 400
    assert "only Laptop and Desktop / Computer assets" in exc.value.detail


def test_live_custody_rejects_mismatched_device_category() -> None:
    db = _StubSession(SimpleNamespace(device_type="Laptop"))
    user = SimpleNamespace()

    with pytest.raises(HTTPException) as exc:
        add_handover_record(_payload(device_category="desktop"), db, user)

    assert exc.value.status_code == 400
    assert exc.value.detail == "Device category must be laptop for the selected asset"
