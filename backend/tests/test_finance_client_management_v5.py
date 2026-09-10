from __future__ import annotations

from datetime import date

import pytest

from app.core.database import SessionLocal
from app.models.entities import User
from app.modules.finance.schemas import FinanceClientCreateRequest, FinanceClientProjectCreateRequest
from app.modules.finance.service import create_client_project, create_finance_client, project_payload


def actor(db, email: str = 'finance.v5@nakshatech.com') -> User:
    row = User(
        email=email,
        full_name='Finance V5',
        password_hash='x',
        role='finance',
        branch='Head Office',
        email_verified=True,
        account_status='active',
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def client_payload(code: str, email: str = ' Accounts@Client.COM ') -> FinanceClientCreateRequest:
    return FinanceClientCreateRequest(
        client_code=code,
        client_name='Manual ID Client Pvt Ltd',
        primary_phone='08040000000',
        client_email=email,
        contact_person_name='Client Contact',
        contact_person_phone='9000000001',
        address='Bengaluru',
        description='Manual ID test client',
        country='India',
        gst_number='29ABCDE1234F1Z5',
        source_team='bd_team',
        source_person_name='BD Owner',
        is_active=True,
    )


def project_payload_input(code: str) -> FinanceClientProjectCreateRequest:
    return FinanceClientProjectCreateRequest(
        project_code=code,
        project_name='Manual Project ID Test',
        project_source_team='management',
        project_source_person_name='Project Owner Name',
        client_awarded_by_name='Client Decision Maker',
        project_award_date=date(2026, 7, 1),
        description='Project acquisition history test',
        start_date=date(2026, 8, 1),
        end_date=date(2026, 12, 31),
        is_active=True,
    )


def test_manual_client_and_project_ids_are_normalized_and_preserved():
    with SessionLocal() as db:
        finance = actor(db)
        client = create_finance_client(db, actor=finance, payload=client_payload(' nt1055 '))
        project = create_client_project(db, client=client, actor=finance, payload=project_payload_input(' nt1055-p27 '))
        db.commit()

        assert client.client_code == 'NT1055'
        assert client.client_email == 'accounts@client.com'
        assert project.project_code == 'NT1055-P27'
        assert project.project_number is None
        data = project_payload(project)
        assert data['project_source_team'] == 'management'
        assert data['project_source_person_name'] == 'Project Owner Name'
        assert data['client_awarded_by_name'] == 'Client Decision Maker'
        assert data['project_award_date'] == date(2026, 7, 1)


def test_duplicate_manual_ids_are_rejected_case_insensitively():
    with SessionLocal() as db:
        finance = actor(db)
        first = create_finance_client(db, actor=finance, payload=client_payload('CLIENT-001'))
        db.flush()
        with pytest.raises(ValueError, match='already exists'):
            create_finance_client(db, actor=finance, payload=client_payload('client-001'))

    with SessionLocal() as db:
        finance = actor(db, 'finance.v5.project@nakshatech.com')
        client1 = create_finance_client(db, actor=finance, payload=client_payload('CLIENT-A'))
        client2 = create_finance_client(db, actor=finance, payload=client_payload('CLIENT-B', 'other@client.com'))
        create_client_project(db, client=client1, actor=finance, payload=project_payload_input('PROJECT-OFFICIAL-9'))
        db.flush()
        with pytest.raises(ValueError, match='already exists'):
            create_client_project(db, client=client2, actor=finance, payload=project_payload_input('project-official-9'))
