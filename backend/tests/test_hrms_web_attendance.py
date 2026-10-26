"""Isolated HRMS tests. Uses in-memory SQLite; never touches ERP PostgreSQL."""
from __future__ import annotations
import os
os.environ.setdefault('DATABASE_URL', 'sqlite+pysqlite:///:memory:')

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


def test_attendance_and_leave_and_hr_permissions():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    User.__table__.create(engine)
    for model in (AttendanceDay, AbsenceExplanation, LeaveRequest, LeaveEntitlement, HRHoliday, HRLeaveNoticeRead, HRLeavePolicy, HRWorkerProfile):
        model.__table__.create(engine)
    with Session(engine) as db:
        employee = User(email='staff@example.test', full_name='Example Employee', password_hash='none', role='employee', branch='HO', is_active=True)
        hr = User(email='hr@example.test', full_name='HR Reviewer', password_hash='none', role='hr', branch='HO', is_active=True)
        db.add_all([employee, hr]); db.commit()
        emp_id, hr_id = employee.id, hr.id
    app = FastAPI()
    app.include_router(router, prefix='/api')
    identity = {'id': emp_id, 'role': 'employee'}
    def auth():
        with Session(engine) as db:
            u = db.get(User, identity['id'])
            db.expunge(u)
            return SimpleNamespace(user=u, effective_role=identity['role'])
    def db_override():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_auth] = auth
    client = TestClient(app)
    try:
        r = client.post('/api/hrms/me/check-in')
        assert r.status_code == 201, r.text
        assert client.post('/api/hrms/me/check-in').status_code == 409
        assert client.post('/api/hrms/me/check-out').status_code == 200
        assert client.post('/api/hrms/me/check-out').status_code == 409
        assert client.get('/api/hrms/hr/overview').status_code == 403
        assert client.get(f'/api/hrms/me/attendance?month={today_ist():%Y-%m}').json()['punches']
        r = client.post('/api/hrms/me/leave', json={'leave_type':'casual', 'from_date':str(today_ist()), 'to_date':str(today_ist()), 'reason':'Approved personal appointment'})
        assert r.status_code == 201, r.text
        leave_id = r.json()['id']
        assert client.post('/api/hrms/me/leave', json={'leave_type':'casual', 'from_date':str(today_ist()), 'to_date':str(today_ist()), 'reason':'Overlapping request'}).status_code == 409
        assert client.get(f'/api/hrms/me/balance?year={today_ist().year}').json()['balances'][0]['entitled'] is None
        identity.update(id=hr_id, role='hr')
        data=client.get('/api/hrms/hr/overview').json()
        assert any(x['user_id']==emp_id for x in data['employees'])
        assert len(data['pending_leaves'])==1
        assert client.post(f'/api/hrms/hr/leave/{leave_id}/decision', json={'status':'approved'}).status_code == 200
        assert client.put('/api/hrms/hr/entitlement', json={'user_id':emp_id,'year':today_ist().year,'leave_type':'casual','days':12}).status_code == 200
        assert client.post('/api/hrms/hr/holidays', json={'holiday_date':str(today_ist()),'name':'HR Test Holiday','official_source_url':'https://example.gov/notice','hr_verified':True}).status_code == 200
        identity.update(id=emp_id, role='employee')
        balances=client.get(f'/api/hrms/me/balance?year={today_ist().year}').json()
        assert balances['balances'][0]['remaining_provisional']==11
        assert client.get(f'/api/hrms/holidays?year={today_ist().year}').json()[0]['name']=='HR Test Holiday'
    finally:
        client.close()
        engine.dispose()


def test_hr_only_notifications_employee_history_and_email_leave_policy():
    engine = create_engine('sqlite+pysqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    User.__table__.create(engine)
    for model in (AttendanceDay, AbsenceExplanation, LeaveRequest, LeaveEntitlement, HRHoliday, HRLeaveNoticeRead, HRLeavePolicy, HRWorkerProfile):
        model.__table__.create(engine)
    with Session(engine) as db:
        employee = User(email='worker@example.test', full_name='Worker', password_hash='none', role='employee', branch='HO', is_active=True)
        hr = User(email='hr@example.test', full_name='HR Manager', password_hash='none', role='hr', branch='HO', is_active=True)
        db.add_all([employee, hr]); db.commit()
        employee_id, hr_id = employee.id, hr.id
    app = FastAPI()
    app.include_router(router, prefix='/api')
    identity = {'id': employee_id, 'role': 'employee'}
    def auth():
        with Session(engine) as db:
            u = db.get(User, identity['id']); db.expunge(u)
            return SimpleNamespace(user=u, effective_role=identity['role'])
    def db_override():
        with Session(engine) as db: yield db
    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_auth] = auth
    client = TestClient(app)
    try:
        request = {'leave_type':'casual','from_date':str(today_ist()),'to_date':str(today_ist()),'reason':'Personal medical appointment'}
        assert client.get('/api/hrms/hr/leave-notifications').status_code == 403
        assert client.get(f'/api/hrms/hr/employees/{employee_id}/leave-history').status_code == 403
        leave = client.post('/api/hrms/me/leave', json=request)
        assert leave.status_code == 201, leave.text
        leave_id = leave.json()['id']
        identity.update(id=hr_id, role='hr')
        assert client.post('/api/hrms/me/leave', json=request).status_code == 403
        alerts = client.get('/api/hrms/hr/leave-notifications').json()
        assert alerts['unread_count'] == 1 and alerts['pending_count'] == 1
        assert alerts['notifications'][0]['user_id'] == employee_id
        assert client.post(f'/api/hrms/hr/leave-notifications/{leave_id}/read').status_code == 200
        assert client.post(f'/api/hrms/hr/leave-notifications/{leave_id}/read').status_code == 200
        assert client.get('/api/hrms/hr/leave-notifications').json()['unread_count'] == 0
        history = client.get(f'/api/hrms/hr/employees/{employee_id}/leave-history').json()
        assert history['summary']['total_requests'] == 1 and history['summary']['pending_requests'] == 1
        assert client.post(f'/api/hrms/hr/leave/{leave_id}/decision', json={'status':'approved'}).status_code == 200
        history = client.get(f'/api/hrms/hr/employees/{employee_id}/leave-history?year={today_ist().year}').json()
        assert history['summary']['approved_calendar_days'] == 1
        assert client.get('/api/hrms/hr/leave-notifications').json()['pending_count'] == 0
    finally:
        client.close(); engine.dispose()
