from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_auth
from app.core.database import get_db
from app.modules.operations import reporting_router as reporting


@pytest.mark.parametrize("path,attribute", [
    ("dashboard", "reporting_dashboard_payload"),
    ("powerbi/semantic-model", "powerbi_semantic_payload"),
    ("powerbi/projects.csv", "powerbi_semantic_payload"),
    ("powerbi/departments.csv", "powerbi_semantic_payload"),
])
@pytest.mark.parametrize("error,expected", [
    (PermissionError("Forbidden report"), 403),
    (ValueError("Invalid reporting period"), 422),
    (HTTPException(404, "Report missing"), 404),
    (RuntimeError("private database connection details"), 500),
])
def test_report_errors_keep_expected_status_and_hide_internal_details(monkeypatch, path, attribute, error, expected):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(reporting, attribute, fail)
    app = FastAPI()
    app.include_router(reporting.router)
    app.dependency_overrides[get_current_auth] = lambda: SimpleNamespace(effective_role="management", user=SimpleNamespace(id=1))
    app.dependency_overrides[get_db] = lambda: None
    response = TestClient(app).get(f"/reporting/{path}")
    assert response.status_code == expected
    if expected == 500:
        assert "private database" not in response.text
        assert response.json()["detail"] == "The report could not be generated. Please try again later."

