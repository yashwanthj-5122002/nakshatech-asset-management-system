import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentAuth, get_current_auth
from app.models.entities import User
from app.modules.asset_return.router import router


@pytest.mark.parametrize("url", [
    f"/api/reports/{report}.xlsx?month={month}"
    for report in ("monthly-assets", "monthly-summary", "complete-monthly")
    for month in ("not-a-month", "2026-13")
] + ["/api/reports/complete-yearly.xlsx?year=2026&period=quarterly"])
def test_report_period_errors_are_client_errors_instead_of_server_errors(url):
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    user = User(id=1, email="report.it@nakshatech.com", full_name="IT QA", role="it")
    test_app.dependency_overrides[get_current_auth] = lambda: CurrentAuth(user=user, claims={"role": "it"}, session=None)
    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get(url)
        assert response.status_code == 400, response.text
        assert response.json()["detail"]
