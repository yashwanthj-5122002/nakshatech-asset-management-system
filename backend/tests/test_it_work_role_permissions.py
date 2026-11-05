import pytest
from fastapi import HTTPException

from app.core.database import SessionLocal
from app.models.entities import User, WorkRecord
from app.modules.batch4.it_control import update_work_without_management_approval
from app.schemas.work import WorkRecordUpdate


@pytest.mark.parametrize("role,allowed", [("it", True), ("admin", True),
                                        ("software_team", True), ("management", False)])
def test_it_work_edit_preserves_admin_equivalent_permissions(role, allowed):
    with SessionLocal() as db:
        user = User(email=f"work.{role}@nakshatech.com", full_name="QA Work Viewer",
                    password_hash="test-only", role=role, is_active=True)
        work = WorkRecord(work_code="QA-WORK-ROLE", module="it", title="QA role check", status="open")
        db.add_all([user, work])
        db.commit()
        payload = WorkRecordUpdate(status="in_progress")
        if allowed:
            result = update_work_without_management_approval(db, work.id, payload, user)
            assert result["status"] == "in_progress"
        else:
            with pytest.raises(HTTPException) as error:
                update_work_without_management_approval(db, work.id, payload, user)
            assert error.value.status_code == 403
