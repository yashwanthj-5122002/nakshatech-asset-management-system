from __future__ import annotations

from types import SimpleNamespace

from app.core.database import SessionLocal
from app.modules.operations.reporting_service import (
    _department_scorecards,
    _project_facts,
    reporting_dashboard_payload,
)


def test_phase8_management_gets_executive_reporting_shape_without_mutating_routing():
    actor = SimpleNamespace(id=-722, role="management")
    with SessionLocal() as db:
        payload = reporting_dashboard_payload(db, actor=actor, effective_role="management")
        assert payload["viewer_mode"] == "executive"
        assert "routing" in payload
        assert "summary" in payload
        assert "department_scorecards" in payload
        assert "projects" in payload
        assert payload["powerbi"]["semantic_model_url"].endswith("/reporting/powerbi/semantic-model")


def test_phase8_project_fact_finance_closure_is_joined_without_raw_table_duplication():
    monitoring = {
        "projects": [{
            "project_id": 72,
            "project_code": "V722-P-001",
            "project_name": "Reporting Test",
            "client_name": "Client",
            "project_status": "active",
            "summary": {
                "health": "attention",
                "overall_progress_percent": 62.5,
                "total_workstreams": 2,
                "completed_workstreams": 1,
                "blocked_workstreams": 0,
                "unresolved_handovers": 1,
                "overdue_handovers": 0,
            },
        }]
    }
    completion = {
        "projects": [{
            "project_id": 72,
            "completion": {"finance_status": "billing_in_progress"},
        }]
    }
    rows = _project_facts(monitoring, completion)
    assert rows == [{
        "project_id": 72,
        "project_code": "V722-P-001",
        "project_name": "Reporting Test",
        "client_name": "Client",
        "project_status": "active",
        "health": "attention",
        "overall_progress_percent": 62.5,
        "total_workstreams": 2,
        "completed_workstreams": 1,
        "blocked_workstreams": 0,
        "unresolved_handovers": 1,
        "overdue_handovers": 0,
        "final_delivery_recorded": True,
        "finance_status": "billing_in_progress",
    }]


def test_phase8_department_scorecard_aggregates_progress_samples_handovers_and_readiness():
    monitoring = {"projects": [{
        "project_id": 1,
        "workstreams": [{"department_code": "ortho", "status": "in_progress", "progress_percent": 50}],
    }]}
    samples = {"sample_requests": [{"departments": [{"department_code": "ortho", "status": "in_progress"}]}]}
    handovers = {"projects": [{"handovers": [{
        "from_department_code": "ortho",
        "to_department_code": "lidar",
        "status": "pending_receipt",
        "overdue": True,
    }]}]}
    directory = {"departments": [{
        "department_code": "ortho",
        "readiness": {"configured_real_members": 2, "pm_candidates": 1, "live_ready": True},
    }]}
    rows = _department_scorecards(monitoring, samples, handovers, directory, restrict_department="ortho")
    assert len(rows) == 1
    row = rows[0]
    assert row["projects"] == 1
    assert row["average_progress_percent"] == 50.0
    assert row["open_samples"] == 1
    assert row["outgoing_handovers"] == 1
    assert row["unresolved_handovers"] == 1
    assert row["overdue_handovers"] == 1
    assert row["configured_real_members"] == 2
    assert row["pm_candidates"] == 1
    assert row["live_ready"] is True
