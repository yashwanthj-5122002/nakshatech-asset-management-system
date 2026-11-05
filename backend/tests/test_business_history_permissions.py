"""Business history must follow the same visibility as its overview."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.business.models import BusinessRecord, BusinessRecordHistory
from app.modules.business.router import router
from app.modules.finance.models import FinanceProject, FinanceProjectMasterProfile


@pytest.mark.parametrize("role,owns_project,expected", [
    ("employee", False, 403), ("it", False, 403), ("hr", False, 403),
    ("ortho", False, 403), ("ortho", True, 200),
    ("finance", False, 200), ("management", False, 200),
    ("admin", False, 200), ("software_team", False, 200), ("bd", False, 200),
])
def test_business_history_is_scoped_to_authorized_roles_or_assigned_pm(role, owns_project, expected):
    with SessionLocal() as db:
        actor = User(email="history.viewer@nakshatech.com", full_name="History Viewer",
                     role=role, password_hash="test-only", is_active=True)
        owner = User(email="history.owner@nakshatech.com", full_name="Project Owner",
                     role="ortho", password_hash="test-only", is_active=True)
        db.add_all([actor, owner])
        db.flush()
        project = FinanceProject(project_code="HISTORY-P1", project_name="History Project",
                                 client_name="History Client", project_source_team="bd_team")
        db.add(project)
        db.flush()
        owner_id = actor.id if owns_project else owner.id
        db.add(FinanceProjectMasterProfile(project_id=project.id, project_manager_id=owner_id))
        record = BusinessRecord(project_id=project.id, reporting_month="2026-11",
                                department_code="ortho", project_manager_user_id=owner_id)
        db.add(record)
        db.flush()
        db.add(BusinessRecordHistory(record_id=record.id, reporting_month="2026-11",
                                    project_id=project.id, action="created",
                                    changes='{"amount_total":{"from":null,"to":"250000.00"}}'))
        db.commit()
        record_id, actor_id = record.id, actor.id

    def auth():
        with SessionLocal() as db:
            user = db.get(User, actor_id)
            db.expunge(user)
            return CurrentAuth(user=user, claims={"role": role}, session=None)

    test_app = FastAPI()
    test_app.include_router(router, prefix="/api")
    test_app.dependency_overrides[get_current_auth] = auth
    with TestClient(test_app) as client:
        response = client.get(f"/api/business/records/{record_id}/history")
        assert response.status_code == expected, response.text
        if expected == 200:
            assert response.json()[0]["changes"]["amount_total"]["to"] == "250000.00"
