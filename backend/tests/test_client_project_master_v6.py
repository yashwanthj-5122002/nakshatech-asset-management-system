from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.schemas import (
    FinanceClientCreateRequest,
    FinanceClientProjectCreateRequest,
    FinanceClientProjectUpdateRequest,
)
from app.modules.finance.service import (
    assigned_projects_for_user,
    client_payload,
    create_client_project,
    create_finance_client,
    employee_project_payload,
    project_is_assigned_to_user,
    project_payload,
    update_client_project,
)
from app.modules.travel_km.schemas import TravelKmClaimCreateRequest
from app.modules.travel_km.emailing import _claim_email_content
from app.modules.travel_km.router import _employee_safe_verification_payload
from app.modules.travel_km.service import claim_payload as travel_claim_payload, create_claim as create_travel_claim


def _user(db, email: str, role: str, name: str) -> User:
    row = User(
        email=email,
        full_name=name,
        password_hash="x",
        role=role,
        branch="Head Office",
        employee_id=(email.split("@")[0].upper() if role == "employee" else None),
        department="Civil" if role == "employee" else "Management",
        email_verified=True,
        account_status="active",
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _client_request() -> FinanceClientCreateRequest:
    return FinanceClientCreateRequest(
        client_code="CL-IND-001",
        vendor_code="NV-001",
        client_type="client",
        client_name="Confidential Client Pvt Ltd",
        task="Drone LiDAR and GIS mapping",
        bd_name="BD Owner",
        contact_person_name="Client Contact",
        contact_person_email="contact@client.example",
        country="India",
        source_team="bd_team",
        source_person_name="BD Owner",
        is_active=True,
    )


def _project_request(employee_id: int, manager_id: int, reporting_id: int) -> FinanceClientProjectCreateRequest:
    return FinanceClientProjectCreateRequest(
        project_code="NT-PROJ-2026-014",
        project_name="Confidential Internal Project Name",
        task="Field survey and asset mapping",
        project_status="active",
        project_manager_id=manager_id,
        reporting_manager_id=reporting_id,
        assigned_employee_ids=[employee_id],
        project_source_team="bd_team",
        project_source_person_name="BD Owner",
        client_awarded_by_name="Client Contact",
        project_award_date=date(2026, 8, 1),
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )


def test_v6_client_project_master_assignment_and_employee_safe_visibility():
    with SessionLocal() as db:
        admin = _user(db, "v6.admin@nakshatech.com", "admin", "V6 Admin")
        manager = _user(db, "v6.manager@nakshatech.com", "management", "Project Manager")
        reporting = _user(db, "v6.reporting@nakshatech.com", "admin", "Reporting Manager")
        employee = _user(db, "v6.employee@nakshatech.com", "employee", "Assigned Employee")
        other_employee = _user(db, "v6.other@nakshatech.com", "employee", "Other Employee")

        client = create_finance_client(db, actor=admin, payload=_client_request())
        project = create_client_project(
            db,
            client=client,
            actor=admin,
            payload=_project_request(employee.id, manager.id, reporting.id),
        )
        db.commit()

        client_data = client_payload(client)
        assert client_data["client_code"] == "CL-IND-001"
        assert client_data["vendor_code"] == "NV-001"
        assert client_data["client_type"] == "client"
        assert client_data["task"] == "Drone LiDAR and GIS mapping"
        assert client_data["bd_name"] == "BD Owner"
        assert client_data["contact_person_email"] == "contact@client.example"
        assert client_data["contact_person_phone"] is None

        project_data = project_payload(project)
        assert project_data["project_code"] == "NT-PROJ-2026-014"
        assert project_data["project_status"] == "active"
        assert project_data["project_manager_id"] == manager.id
        assert project_data["reporting_manager_id"] == reporting.id
        assert project_data["assigned_employee_ids"] == [employee.id]

        assert project_is_assigned_to_user(db, project_id=project.id, user_id=employee.id) is True
        assert project_is_assigned_to_user(db, project_id=project.id, user_id=other_employee.id) is False
        assert [row.id for row in assigned_projects_for_user(db, user_id=employee.id)] == [project.id]
        assert assigned_projects_for_user(db, user_id=other_employee.id) == []

        safe = employee_project_payload(project)
        assert safe["project_code"] == "NT-PROJ-2026-014"
        assert safe["project_name"] == "Confidential Internal Project Name"
        assert safe["client_id"] is None
        assert safe["client_code"] is None
        assert safe["client_name"] == "Confidential Client Pvt Ltd"
        assert safe["task"] == "Field survey and asset mapping"
        assert safe["project_manager_name"] is None
        assert safe["assigned_employees"] == []

        claim = create_travel_claim(
            db,
            requester=employee,
            payload=TravelKmClaimCreateRequest(
                project_id=project.id,
                travel_date=date(2026, 9, 2),
                purpose_description="Assigned project field visit",
                start_km=Decimal("1200.00"),
                start_latitude=12.9716,
                start_longitude=77.5946,
                start_accuracy_m=10.0,
                start_captured_at=datetime(2026, 9, 2, 9, 0, 0),
            ),
        )
        employee_claim = travel_claim_payload(db, claim, viewer=employee, effective_role="employee")
        assert employee_claim["project_code"] == "NT-PROJ-2026-014"
        assert employee_claim["project_name"] == "Confidential Internal Project Name"
        assert employee_claim["client_name"] == "Confidential Client Pvt Ltd"

        staff_claim = travel_claim_payload(db, claim, viewer=admin, effective_role="admin")
        assert staff_claim["project_name"] == "Confidential Internal Project Name"
        assert staff_claim["client_name"] == "Confidential Client Pvt Ltd"

        redacted_verification = _employee_safe_verification_payload({
            "score": 92,
            "geofence": {
                "configured": True,
                "site_name": "Confidential Client Main Gate",
                "center_latitude": 12.9716,
                "center_longitude": 77.5946,
                "radius_m": 500,
                "site_entered": True,
                "nearest_distance_m": 18.5,
            },
        })
        assert redacted_verification["geofence"]["site_name"] == "Assigned Project Site"
        assert redacted_verification["geofence"]["center_latitude"] is None
        assert redacted_verification["geofence"]["center_longitude"] is None
        assert redacted_verification["geofence"]["site_entered"] is True
        assert redacted_verification["geofence"]["radius_m"] == 500

        subject, text_body, html_body = _claim_email_content(claim, employee, "http://localhost:8088")
        assert "NT-PROJ-2026-014" in subject
        assert "Project Number: NT-PROJ-2026-014" in text_body
        assert "Confidential Internal Project Name" not in text_body
        assert "Confidential Internal Project Name" not in html_body
        assert "Confidential Client Pvt Ltd" not in text_body
        assert "Confidential Client Pvt Ltd" not in html_body


def test_v6_project_status_and_assignment_update_are_soft_and_auditable_friendly():
    with SessionLocal() as db:
        admin = _user(db, "v6.admin2@nakshatech.com", "admin", "V6 Admin Two")
        manager = _user(db, "v6.manager2@nakshatech.com", "management", "Project Manager Two")
        employee = _user(db, "v6.employee2@nakshatech.com", "employee", "Assigned Employee Two")
        replacement = _user(db, "v6.employee3@nakshatech.com", "employee", "Replacement Employee")
        client = create_finance_client(db, actor=admin, payload=FinanceClientCreateRequest(**{
            **_client_request().model_dump(),
            "client_code": "CL-IND-002",
            "client_name": "Second Confidential Client",
        }))
        project = create_client_project(
            db,
            client=client,
            actor=admin,
            payload=_project_request(employee.id, manager.id, admin.id),
        )
        db.flush()

        update = FinanceClientProjectUpdateRequest(
            project_name=project.project_name,
            task="Updated scope",
            project_status="on_hold",
            project_manager_id=manager.id,
            reporting_manager_id=admin.id,
            assigned_employee_ids=[replacement.id],
            project_source_team="bd_team",
            project_source_person_name="BD Owner",
            client_awarded_by_name="Client Contact",
            project_award_date=date(2026, 8, 1),
            description="On hold for client instruction",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 12, 31),
            is_active=True,
        )
        update_client_project(db, project=project, actor=admin, payload=update)
        db.commit()

        assert project.is_active is False
        assert project.master_profile is not None
        assert project.master_profile.project_status == "on_hold"
        assert project_is_assigned_to_user(db, project_id=project.id, user_id=employee.id) is False
        assert project_is_assigned_to_user(db, project_id=project.id, user_id=replacement.id) is True
        assert assigned_projects_for_user(db, user_id=replacement.id) == []
