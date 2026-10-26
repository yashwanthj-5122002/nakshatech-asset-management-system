"""Company HRMS policy tests. Isolated in-memory SQLite only."""
from __future__ import annotations
import os
os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')
from datetime import date, timedelta
from types import SimpleNamespace
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.api.dependencies import get_current_auth
from app.core.database import get_db
from app.models.entities import User
from app.modules.hrms.models import AttendanceDay, AbsenceExplanation, LeaveRequest, LeaveEntitlement, HRHoliday, HRLeaveNoticeRead, HRLeavePolicy, HRWorkerProfile
from app.modules.hrms.router import router, today_ist
from app.modules.hrms.policy import add_months, chargeable_days, paid_entitlement


def test_period_boundaries_and_weekdays():
    ref = date(2026, 10, 19)
    intern = SimpleNamespace(joining_date=date(2026, 7, 19), employment_category='intern')
    staff = SimpleNamespace(joining_date=date(2026, 5, 19), employment_category='staff')
    policy = SimpleNamespace(intern_monthly_days=1, probation_first_six_month_days=5,
                             months_seven_to_twelve_extra_days=3, full_time_annual_days=15)
    assert paid_entitlement(policy, intern, ref)[0] == 3
    assert paid_entitlement(policy, staff, ref)[0:2] == (5, 'probation_first_six_months')
    assert paid_entitlement(policy, staff, date(2026, 11, 19))[0:2] == (8, 'months_seven_to_twelve')
    assert paid_entitlement(policy, staff, date(2027, 5, 19))[0:2] == (15, 'full_time')
    assert paid_entitlement(policy, staff, date(2027, 5, 19))[2:] == (date(2027, 1, 1), date(2027, 12, 31))
    assert chargeable_days(date(2026, 10, 17), date(2026, 10, 19), {0,1,2,3,4}, set()) == 1
    assert chargeable_days(date(2026, 10, 17), date(2026, 10, 19), {0,1,2,3,4}, {date(2026, 10, 19)}) == 0
    assert add_months(date(2024, 8, 31), 6) == date(2025, 2, 28)


def test_hr_policy_bulk_roles_notifications_balances_and_approval_guard():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    User.__table__.create(engine)
    for model in (AttendanceDay, AbsenceExplanation, LeaveRequest, LeaveEntitlement, HRHoliday,
                  HRLeaveNoticeRead, HRLeavePolicy, HRWorkerProfile):
        model.__table__.create(engine)
    now = today_ist()
    with Session(engine) as db:
        first = User(email='employee@example.test', full_name='Probation Employee', password_hash='none',
                     role='employee', branch='HO', is_active=True, joining_date=add_months(now, -3))
        intern = User(email='intern@example.test', full_name='Intern', password_hash='none',
                      role='employee', branch='HO', is_active=True, joining_date=add_months(now, -4))
        hr = User(email='hr@example.test', full_name='HR Reviewer', password_hash='none',
                  role='hr', branch='HO', is_active=True)
        db.add_all([first, intern, hr]); db.commit()
        staff_id, intern_id, hr_id = first.id, intern.id, hr.id
    identity = {'id': staff_id, 'role': 'employee'}
    app = FastAPI(); app.include_router(router, prefix='/api')
    def db_override():
        with Session(engine) as db: yield db
    def auth():
        with Session(engine) as db:
            user = db.get(User, identity['id']); db.expunge(user)
            return SimpleNamespace(user=user, effective_role=identity['role'])
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_auth] = auth
    with TestClient(app) as client:
        current = now.year
        assert client.get(f'/api/hrms/me/balance?year={current}').status_code == 200
        assert client.put('/api/hrms/hr/policy', json={'year':current, 'intern_monthly_days':1,
                    'probation_first_six_month_days':5,'months_seven_to_twelve_extra_days':3,
                    'full_time_annual_days':15,'working_weekdays':[0,1,2,3,4,5]}).status_code == 403
        identity.update(id=hr_id, role='hr')
        payload = {'year':current,'intern_monthly_days':1,'probation_first_six_month_days':5,
                   'months_seven_to_twelve_extra_days':3,'full_time_annual_days':15,
                   'working_weekdays':[0,1,2,3,4,5]}
        assert client.put('/api/hrms/hr/policy',json=payload).status_code == 200
        assert client.get(f'/api/hrms/hr/policy?year={current}').json()['configured']
        missing = client.put('/api/hrms/hr/employees/classifications/bulk',json={
            'user_ids':[hr_id], 'employment_category':'staff'})
        assert missing.status_code == 422
        assert client.put('/api/hrms/hr/employees/classifications/bulk',json={
            'user_ids':[staff_id],'employment_category':'staff'}).status_code == 200
        assert client.put('/api/hrms/hr/employees/classifications/bulk',json={
            'user_ids':[intern_id],'employment_category':'intern'}).status_code == 200
        classes = client.get('/api/hrms/hr/employees/classifications').json()
        assert next(x for x in classes if x['user_id'] == staff_id)['employment_category'] == 'staff'
        assert client.get(f'/api/hrms/hr/employees/{staff_id}/balance?year={current}').json()['employment_stage'] == 'probation_first_six_months'
        identity.update(id=staff_id, role='employee')
        balance = client.get(f'/api/hrms/me/balance?year={current}').json()
        assert balance['balances'][0]['entitled'] == 5
        assert balance['employment_category'] == 'staff'
        # Large request should remain pending but cannot be approved over entitlement.
        leave = client.post('/api/hrms/me/leave',json={'leave_type':'paid','from_date':str(now),
            'to_date':str(now+timedelta(days=20)), 'reason':'Extended vacation request'})
        assert leave.status_code == 201, leave.text
        identity.update(id=hr_id, role='hr')
        alert = client.get('/api/hrms/hr/leave-notifications').json()
        assert alert['unread_count'] == 1
        denial = client.post(f"/api/hrms/hr/leave/{leave.json()['id']}/decision", json={'status':'approved'})
        assert denial.status_code == 409
        assert client.post(f"/api/hrms/hr/leave/{leave.json()['id']}/decision", json={'status':'rejected'}).status_code == 200
        identity.update(id=intern_id, role='employee')
        intern_balance = client.get(f'/api/hrms/me/balance?year={current}').json()
        assert intern_balance['employment_stage'] == 'intern'
        assert intern_balance['balances'][0]['entitled'] >= 4
    engine.dispose()
