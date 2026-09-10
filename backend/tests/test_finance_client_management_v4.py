from __future__ import annotations

from datetime import date

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.schemas import (
    ExpenseClaimCreateRequest,
    FinanceClientCreateRequest,
    FinanceClientProjectCreateRequest,
    FinanceClientUpdateRequest,
)
from app.modules.finance.service import (
    client_payload,
    create_claim,
    create_client_project,
    create_finance_client,
    project_expense_allowed,
    project_payload,
    update_finance_client,
)


def user(db, email: str, role: str) -> User:
    row = User(
        email=email,
        full_name=email.split('@')[0],
        password_hash='x',
        role=role,
        branch='Head Office',
        email_verified=True,
        account_status='active',
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def client_request(code: str = 'NT1055', name: str = 'ABC Infrastructure Pvt Ltd') -> FinanceClientCreateRequest:
    return FinanceClientCreateRequest(
        client_code=code,
        client_name=name,
        primary_phone='080-40000000',
        client_email='finance@abcinfra.example',
        contact_person_name='Rajesh Kumar',
        contact_person_phone='9876543210',
        address='Bengaluru, Karnataka',
        description='Government infrastructure and GIS client.',
        country='India',
        gst_number='29abcde1234f1z5',
        source_team='bd_team',
        source_person_name='Naksha BD Executive',
        is_active=True,
    )


def project_request(code: str, name: str) -> FinanceClientProjectCreateRequest:
    return FinanceClientProjectCreateRequest(
        project_code=code,
        project_name=name,
        project_source_team='software_team',
        project_source_person_name='Naksha Project Lead',
        client_awarded_by_name='Rajesh Kumar',
        project_award_date=date(2025, 12, 20),
        description=f'{name} production project.',
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )


def test_client_and_project_master_keeps_manual_ids_and_acquisition_details():
    with SessionLocal() as db:
        finance = user(db, 'finance.client.v4@nakshatech.com', 'finance')
        first = create_finance_client(db, actor=finance, payload=client_request())
        p1 = create_client_project(db, client=first, actor=finance, payload=project_request('NT1055-P1', 'Bengaluru Road Survey'))
        p2 = create_client_project(db, client=first, actor=finance, payload=project_request('SPECIAL-PROJECT-22', 'Mysuru GIS Mapping'))
        second = create_finance_client(db, actor=finance, payload=client_request('CLIENT-WATER-07', 'XYZ Water Solutions'))
        p3 = create_client_project(db, client=second, actor=finance, payload=project_request('WATER-RIVER-01', 'River Asset Survey'))
        db.commit()

        assert first.client_code == 'NT1055'
        assert second.client_code == 'CLIENT-WATER-07'
        assert p1.project_code == 'NT1055-P1'
        assert p2.project_code == 'SPECIAL-PROJECT-22'
        assert p3.project_code == 'WATER-RIVER-01'
        assert first.gst_number == '29ABCDE1234F1Z5'
        assert first.client_email == 'finance@abcinfra.example'
        assert p1.project_source_team == 'software_team'
        assert p1.project_source_person_name == 'Naksha Project Lead'
        assert p1.client_awarded_by_name == 'Rajesh Kumar'
        assert client_payload(first)['project_count'] == 2
        assert project_payload(p1)['client_code'] == 'NT1055'
        assert project_payload(p1)['client_name'] == 'ABC Infrastructure Pvt Ltd'


def test_client_project_is_the_employee_expense_project_master():
    with SessionLocal() as db:
        finance = user(db, 'finance.master.v4@nakshatech.com', 'finance')
        employee = user(db, 'employee.master.v4@nakshatech.com', 'employee')
        client = create_finance_client(db, actor=finance, payload=client_request())
        project = create_client_project(db, client=client, actor=finance, payload=project_request('NT1055-P1', 'Drone Topographic Survey'))
        db.commit()

        claim = create_claim(
            db,
            requester=employee,
            payload=ExpenseClaimCreateRequest(
                project_id=project.id,
                claim_type='advance',
                purpose_description='Field survey advance linked to the manual client project master.',
                requested_work_start_date=date(2026, 8, 28),
                requested_work_end_date=date(2026, 8, 30),
                items=[{'category': 'travel', 'description': 'Project field travel', 'amount': 5000}],
            ),
        )
        assert claim.project.project_code == 'NT1055-P1'
        assert claim.project.client.client_code == 'NT1055'

        update_payload = client_request().model_dump()
        update_payload.pop('client_code')
        update_finance_client(
            db,
            client=client,
            actor=finance,
            payload=FinanceClientUpdateRequest(**{**update_payload, 'is_active': False}),
        )
        allowed, reason = project_expense_allowed(project, on_date=date(2026, 8, 28))
        assert allowed is False
        assert 'client is inactive' in (reason or '').lower()
