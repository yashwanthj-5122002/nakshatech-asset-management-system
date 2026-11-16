"""Standalone API smoke checks using a private in-memory database."""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
os.environ.update(DATABASE_URL='sqlite+pysqlite:///:memory:',
                  JWT_SECRET='module-audit-test-secret-only-32-characters',
                  ENVIRONMENT='development', APP_ENV='development',
                  EMAIL_DELIVERY_MODE='console', SEED_DEFAULT_USERS='false',
                  ENABLE_BACKGROUND_WATCHER='false', LOCAL_BACKUP_AGENT_ENABLED='false')

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.batch4_main import app as registered_app  # register all database models
from app.api.dependencies import CurrentAuth, get_current_auth
from app.core.database import Base, get_db
from app.models.entities import User, utc_now
from app.modules.management_clients.router import router as clients_router
from app.modules.management_projects.router import router as projects_router
from app.modules.notifications.router import router as notifications_router
from app.modules.operations.models import ProjectWorkflow, ProjectWorkflowEvent, OrthoWorkPackage
from app.modules.operations.lifecycle_service import create_invoice_draft, raise_invoice, READY_FOR_BILLING, MANAGEMENT_SOURCE_APPROVED_EVENT
from app.modules.operations.lifecycle_schemas import InvoiceDraftCreate, InvoiceRaise
from app.modules.notifications.service import create_global_notification

engine = create_engine('sqlite+pysqlite://', poolclass=StaticPool,
                       connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)
Sessions = sessionmaker(bind=engine, expire_on_commit=False)
ids = {}
with Sessions() as db:
    for key, email, role in [('management', 'vinod@nakshatech.com', 'management'),
                             ('finance', 'audit.finance@example.com', 'finance'),
                             ('bd', 'audit.bd@example.com', 'bd'),
                             ('lidar_pm', 'audit.lidar@example.com', 'lidar'),
                             ('ortho_pm', 'audit.ortho@example.com', 'ortho')]:
        user = User(email=email, full_name=key.title(), password_hash='test-only',
                    role=role, is_active=True, email_verified=True, account_status='active')
        db.add(user)
        db.flush()
        ids[key] = user.id
    db.commit()

app = FastAPI()
app.include_router(clients_router, prefix='/api')
app.include_router(projects_router, prefix='/api')
app.include_router(notifications_router, prefix='/api')
actor = 'management'

def database():
    with Sessions() as db:
        yield db

def authentication():
    with Sessions() as db:
        user = db.get(User, ids[actor])
        db.expunge(user)
        return CurrentAuth(user=user, claims={'role': user.role}, session=None)

app.dependency_overrides[get_db] = database
app.dependency_overrides[get_current_auth] = authentication
client = TestClient(app, raise_server_exceptions=False)
results = []
project_ids = {}

def check(name, method, url, expected, body=None, role=None):
    global actor
    if role:
        actor = role
    response = client.request(method, '/api' + url, json=body) if body is not None else client.request(method, '/api' + url)
    try:
        data = response.json()
    except ValueError:
        data = response.text[:500]
    results.append(dict(name=name, passed=response.status_code == expected,
                        expected_status=expected, actual_status=response.status_code,
                        response=data))
    return data if response.status_code == expected else None

try:
    check('Finance cannot register Management clients', 'GET', '/management/client-register', 403, role='finance')
    check('BD cannot read Finance Management projects', 'GET', '/finance/management-projects', 403, role='bd')
    for kind in ('regular', 'pilot'):
        body = dict(client_code=f'AUDIT-{kind.upper()}', client_name=f'Audit {kind}',
                    contact_person_name='Audit Contact', contact_person_phone='9999999999',
                    work_description='Isolated automated module check', project_type=kind)
        intake = check(f'{kind}: register client', 'POST', '/management/client-register', 201, body, 'management')
        check(f'{kind}: duplicate client blocked', 'POST', '/management/client-register', 409, body)
        if not intake:
            continue
        check(f'{kind}: Management department options', 'GET', '/management/client-register/department-change-options', 200)
        requests = check(f'{kind}: Finance request queue', 'GET', '/finance/management-projects/additional-project-requests', 200, role='finance')
        queue = check(f'{kind}: Finance action popup', 'GET', '/notifications/global/popup-queue', 200)
        results.append(dict(name=f'{kind}: real request appears in action popup',
                            passed=bool(queue and any(row.get('event_type') == 'management.additional_project.requested' for row in queue))))
        request_id = next(row['id'] for row in requests if row['management_client_id'] == intake['id'])
        payload = dict(management_client_id=intake['id'], project_code=f'AUDIT-PROJECT-{kind.upper()}',
                       additional_request_id=request_id,
                       project_name=f'Audit {kind} project', start_date='2026-11-14', end_date='2026-11-20',
                       scope_text='Audit survey deliverables', performing_department_code='ortho', priority='high',
                       project_type=kind, pilot_payment_type='free' if kind == 'pilot' else None,
                       commercial=dict(estimated_amount=0 if kind == 'pilot' else 10000,
                                       currency_code='INR', scope_description='Audit survey deliverables',
                                       estimate_date='2026-11-14', payment_terms='Net 30'))
        project = check(f'{kind}: Finance creates project', 'POST', '/finance/management-projects', 201, payload)
        if project:
            pid = project['project_id']
            project_ids[kind] = pid
            check(f'{kind}: fulfilled request cannot be replayed', 'POST', '/finance/management-projects', 409, payload)
            pending = check(f'{kind}: Finance pending count after fulfillment', 'GET', '/notifications/global/pending-count', 200)
            results.append(dict(name=f'{kind}: fulfilled action no longer pending', passed=pending == {'pending_count': 0}))
            check(f'{kind}: Finance changes department before work', 'POST',
                  f'/finance/management-projects/{pid}/change-department', 200,
                  dict(performing_department_code='lidar', project_manager_id=ids['lidar_pm'], reason='Audit pre-start correction'))
            check(f'{kind}: source changes department before work', 'POST',
                  f'/management/client-register/projects/{pid}/change-department', 200,
                  dict(performing_department_code='ortho', project_manager_id=ids['ortho_pm'], reason='Audit pre-start correction'), 'management')
            actor = 'finance'
            check(f'{kind}: Finance file tracking', 'GET', f'/finance/management-projects/{pid}/tracking', 200)
            check(f'{kind}: Management tracking', 'GET', '/management/client-register/project-tracking', 200, role='management')
            check(f'{kind}: premature approval blocked', 'POST', f'/management/client-register/projects/{pid}/approve', 409)
            check(f'{kind}: premature revocation blocked', 'POST', f'/management/client-register/projects/{pid}/revoke-approval', 409)
            check(f'{kind}: BD project details blocked', 'GET', f'/finance/management-projects/{pid}/tracking', 403, role='bd')
    check('Finance project list', 'GET', '/finance/management-projects', 200, role='finance')
    check('Finance tracking rollup', 'GET', '/finance/management-projects/tracking', 200)
    check('Finance summary', 'GET', '/finance/management-projects/summary', 200)
    regular_id = project_ids['regular']
    with Sessions() as db:
        workflow = db.get(ProjectWorkflow, regular_id)
        workflow.status = 'APPROVAL_PENDING'
        workflow.operational_completed_at = utc_now()
        db.add(OrthoWorkPackage(project_id=regular_id, package_code='AUDIT-DELIVERED',
                               package_name='Delivered legacy area', current_stage='delivered',
                               production_state='completed', qc_state='passed', qa_state='passed',
                               delivered_at=utc_now(), created_by_id=ids['finance']))
        create_global_notification(db, event_type='lifecycle.management_approval_requested',
            title='Management approval required', message='Audit delivered project',
            recipient_user_ids=[ids['management']], category='approval', requires_action=True,
            dedupe_key=f'lifecycle:management-approval:{regular_id}', target_url='/management/project-management')
        db.commit()
    before = check('Delivered project: Management approval popup', 'GET', '/notifications/global/popup-queue', 200, role='management')
    results.append(dict(name='Delivered project: source sees approval action', passed=bool(before)))
    check('Delivered project: source approves', 'POST', f'/management/client-register/projects/{regular_id}/approve', 200)
    with Sessions() as db:
        invoice = create_invoice_draft(db, actor=db.get(User, ids['finance']), project_id=regular_id,
            payload=InvoiceDraftCreate(invoice_number='AUDIT-REGULAR-DRAFT', invoice_date='2026-11-14',
                                       due_date='2026-12-14', amount=1000, currency='INR'))
        db.commit()
        regular_invoice_id = invoice.id
    check('Draft exists: source revokes approval', 'POST', f'/management/client-register/projects/{regular_id}/revoke-approval', 200)
    with Sessions() as db:
        try:
            raise_invoice(db, actor=db.get(User, ids['finance']), invoice_id=regular_invoice_id, payload=InvoiceRaise())
            results.append(dict(name='Revoked approval blocks raising draft', passed=False))
        except (ValueError, PermissionError) as exc:
            results.append(dict(name='Revoked approval blocks raising draft', passed='approval' in str(exc).lower()))
        finally:
            db.rollback()
    tracking = check('Draft exists: source tracking after revocation', 'GET', '/management/client-register/project-tracking', 200)
    can_approve = next(row['can_approve'] for row in tracking['projects'] if row['id'] == regular_id)
    after = check('Draft exists: source popup after revocation', 'GET', '/notifications/global/popup-queue', 200)
    results.append(dict(name='Draft exists: reapproval action remains visible in popup',
                        passed=bool(can_approve and after), response={'can_approve': can_approve, 'popup_count': len(after)}))
    check('Draft exists: source can approve again', 'POST', f'/management/client-register/projects/{regular_id}/approve', 200)
    with Sessions() as db:
        raise_invoice(db, actor=db.get(User, ids['finance']), invoice_id=regular_invoice_id, payload=InvoiceRaise())
        db.commit()
    check('Issued invoice locks approval revocation', 'POST', f'/management/client-register/projects/{regular_id}/revoke-approval', 409)
    # Model a delivered/source-approved pilot to test the invoice policy itself.
    # This is private fixture state, never a mutation of application data.
    with Sessions() as db:
        workflow = db.get(ProjectWorkflow, pid)
        workflow.status = READY_FOR_BILLING
        db.add(ProjectWorkflowEvent(project_id=pid, event_type=MANAGEMENT_SOURCE_APPROVED_EVENT,
                                    actor_user_id=ids['management'], to_status=READY_FOR_BILLING))
        db.flush()
        finance = db.get(User, ids['finance'])
        try:
            invoice = create_invoice_draft(db, actor=finance, project_id=pid,
                payload=InvoiceDraftCreate(invoice_number='AUDIT-FREE-PILOT', invoice_date='2026-11-14',
                                           due_date='2026-12-14', amount=1000, currency='INR'))
            raise_invoice(db, actor=finance, invoice_id=invoice.id, payload=InvoiceRaise())
            results.append(dict(name='Free pilot: backend blocks customer invoicing', passed=False,
                                response={'invoice_id': invoice.id, 'status': invoice.status, 'amount': str(invoice.amount)},
                                detail='A positive customer invoice was drafted and raised for a zero-value free pilot in a private fixture.'))
        except (ValueError, PermissionError) as exc:
            results.append(dict(name='Free pilot: backend blocks customer invoicing',
                                passed='pilot' in str(exc).lower(), response=str(exc)))
        finally:
            db.rollback()
except Exception:
    results.append(dict(name='Smoke runner exception', passed=False, error=traceback.format_exc()))
finally:
    output = ROOT / 'artifacts/qa/module-audit-management.json'
    output.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')
    print(json.dumps({'checks': len(results), 'passed': sum(r['passed'] for r in results),
                      'failures': [r for r in results if not r['passed']]}, indent=2))
    engine.dispose()
sys.exit(1 if any(not row['passed'] for row in results) else 0)
