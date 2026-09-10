from __future__ import annotations

from datetime import date

from app.api.dependencies import CurrentAuth
from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.router import list_projects
from app.modules.finance.schemas import FinanceClientCreateRequest, FinanceClientProjectCreateRequest
from app.modules.finance.service import create_client_project, create_finance_client, project_expense_allowed
from app.modules.travel_km.router import employee_project_numbers


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="x",
        role=role,
        branch="Head Office",
        employee_id=(email.split("@")[0].upper() if role == "employee" else None),
        department="Survey" if role == "employee" else "Finance",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _project_request(code: str, name: str, *, status: str, assigned_employee_ids: list[int]) -> FinanceClientProjectCreateRequest:
    return FinanceClientProjectCreateRequest(
        project_code=code,
        project_name=name,
        task="Live project selector verification",
        project_status=status,
        project_manager_id=None,
        reporting_manager_id=None,
        assigned_employee_ids=assigned_employee_ids,
        project_source_team="bd_team",
        project_source_person_name="Finance",
        client_awarded_by_name="Client Contact",
        project_award_date=date(2026, 8, 1),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 31),
        is_active=status == "active",
    )


def test_v6_1_3_employee_sees_all_projects_but_only_ongoing_projects_are_claimable():
    with SessionLocal() as db:
        finance = _user(db, "selector.finance@nakshatech.com", "finance", "Selector Finance")
        assigned_employee = _user(db, "selector.assigned@nakshatech.com", "employee", "Assigned Employee")
        other_employee = _user(db, "selector.other@nakshatech.com", "employee", "Other Employee")

        client = create_finance_client(
            db,
            actor=finance,
            payload=FinanceClientCreateRequest(
                client_code="SEL-CLIENT-001",
                vendor_code="NV-SEL-001",
                client_type="client",
                client_name="Selector Client",
                task="Survey and mapping",
                bd_name="Private BD Owner",
                contact_person_name="Private Contact",
                contact_person_email="private@example.com",
                country="India",
                source_team="bd_team",
                source_person_name="Finance",
                is_active=True,
            ),
        )
        active = create_client_project(
            db,
            client=client,
            actor=finance,
            payload=_project_request(
                "SEL-ACTIVE-001",
                "Ongoing Survey Project",
                status="active",
                assigned_employee_ids=[assigned_employee.id],
            ),
        )
        completed = create_client_project(
            db,
            client=client,
            actor=finance,
            payload=_project_request(
                "SEL-COMPLETE-001",
                "Completed Survey Project",
                status="completed",
                assigned_employee_ids=[],
            ),
        )
        db.commit()

        # The second employee is intentionally NOT assigned to the active project.
        auth = CurrentAuth(user=other_employee, claims={"role": "employee"}, session=None)

        finance_selector = list_projects(db=db, auth=auth)
        finance_by_code = {row["project_code"]: row for row in finance_selector}
        assert finance_by_code[active.project_code]["expense_allowed"] is True
        assert finance_by_code[active.project_code]["client_name"] == "Selector Client"
        assert finance_by_code[active.project_code]["project_name"] == "Ongoing Survey Project"
        assert finance_by_code[active.project_code]["client_code"] is None
        assert finance_by_code[active.project_code]["project_manager_name"] is None

        assert finance_by_code[completed.project_code]["expense_allowed"] is False
        assert finance_by_code[completed.project_code]["lifecycle_status"] == "completed"
        assert "completed" in (finance_by_code[completed.project_code]["expense_block_reason"] or "").lower()

        travel_selector = employee_project_numbers(db=db, auth=auth)
        travel_by_code = {row["project_number"]: row for row in travel_selector}
        assert travel_by_code[active.project_code]["claim_allowed"] is True
        assert travel_by_code[active.project_code]["client_name"] == "Selector Client"
        assert travel_by_code[active.project_code]["project_name"] == "Ongoing Survey Project"
        assert travel_by_code[completed.project_code]["claim_allowed"] is False
        assert travel_by_code[completed.project_code]["lifecycle_status"] == "completed"
        assert "completed" in (travel_by_code[completed.project_code]["claim_block_reason"] or "").lower()

        allowed, reason = project_expense_allowed(completed, on_date=date(2026, 9, 2))
        assert allowed is False
        assert "completed" in (reason or "").lower()
