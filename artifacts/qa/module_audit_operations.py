"""Exercise the current BD review-only handoff and file workflow in isolation."""
import json
import os
from pathlib import Path
import sys
import traceback
from datetime import date
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'backend/tests')]
os.environ.update(DATABASE_URL='sqlite+pysqlite:///:memory:',
                  JWT_SECRET='module-audit-test-secret-only-32-characters',
                  ENVIRONMENT='development', APP_ENV='development',
                  EMAIL_DELIVERY_MODE='console', SEED_DEFAULT_USERS='false',
                  ENABLE_BACKGROUND_WATCHER='false', LOCAL_BACKUP_AGENT_ENABLED='false')
from app.batch4_main import app
from app.core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.modules.operations.workflow_service import create_bd_project, submit_project_to_finance, assign_project_manager
from app.modules.operations.schemas import WorkflowProjectCreate, WorkflowPMAssignment
from app.modules.commercial.schemas import ProjectCommercialInput
from app.modules.operations import production_items as service
from test_production_file_tracking_v8_2 import make_user, make_client, full_team
from test_production_master_excel_allocation_v8_3 import (
    MASTER_HEADERS, import_master, xlsx_bytes, packages_of, items_of,
    assign_all, run_production, run_review,
)

engine = create_engine('sqlite+pysqlite:///:memory:')
Base.metadata.create_all(engine)
Sessions = sessionmaker(bind=engine, expire_on_commit=False)
results = []

def record(name, fn):
    try:
        value = fn()
        results.append(dict(name=name, passed=True))
        return value
    except Exception:
        results.append(dict(name=name, passed=False, error=traceback.format_exc()))
        raise

def require(condition, message):
    assert condition, message

def blocked(fn):
    try:
        fn()
    except (ValueError, PermissionError):
        return
    raise AssertionError('Unauthorized or premature operation unexpectedly succeeded')

for rework in (False, True):
    label = 'with QC rework' if rework else 'normal flow'
    with Sessions() as db:
        try:
            code = f'AUDIT-{int(rework)}'
            bd = make_user(db, f'bd.{code}@example.com', 'bd')
            pm = make_user(db, f'pm.{code}@example.com', 'lidar', 'LiDAR')
            client = make_client(db, bd, code)
            project, workflow = record(f'{label}: create BD project', lambda: create_bd_project(
                db, actor=bd, payload=WorkflowProjectCreate(
                    client_id=client.id, project_code=code, project_name='Audit current workflow',
                    start_date=date(2026, 11, 14), end_date=date(2026, 12, 1),
                    scope_text='Audit survey', performing_department_code='lidar',
                    commercial=ProjectCommercialInput(scope_description='Audit survey',
                        billing_type='fixed_price', payment_terms='Net 30', currency_code='INR',
                        estimated_amount=Decimal('10000'), estimate_date=date(2026, 11, 14)))))
            record(f'{label}: BD shares with Finance', lambda: submit_project_to_finance(db, actor=bd, project_id=project.id))
            record(f'{label}: handoff requires no Finance approval', lambda: require(
                workflow.status == 'finance_approved' and workflow.finance_reviewed_at is None,
                f'Unexpected handoff state: {workflow.status}'))
            record(f'{label}: assign department PM', lambda: assign_project_manager(
                db, actor=bd, project_id=project.id, payload=WorkflowPMAssignment(project_manager_id=pm.id)))
            team = record(f'{label}: PM configures team', lambda: full_team(db, pm, project, code))
            ctx = dict(bd=bd, pm=pm, project=project, workflow=workflow, team=team)
            record(f'{label}: import planned files', lambda: import_master(db, ctx,
                xlsx_bytes(MASTER_HEADERS, [['LOT', code, 'Audit Area', 'F1', 3000, 'm', '']])))
            package, item = packages_of(db, ctx)[0], items_of(db, ctx)[0]
            record(f'{label}: allocate production QC QA', lambda: assign_all(db, ctx, package, [item.id]))
            record(f'{label}: premature delivery blocked', lambda: blocked(lambda: service.deliver_item(
                db, actor=team['tl'], role='employee', work_package_item_id=item.id)))
            record(f'{label}: complete production', lambda: run_production(db, ctx, item, quantity='3000'))
            original_area, original_unit = package.area, package.area_unit
            package.area, package.area_unit = Decimal('3000'), 'm'
            db.flush()
            record(f'{label}: tracking converts item kilometres to package metres', lambda: require(
                service.item_dashboard_context(db, [package])[package.id]['production_actual'] == 3000,
                'Production tracking did not normalize km to m'))
            package.area, package.area_unit = original_area, original_unit
            db.flush()
            if rework:
                record(f'{label}: QC rejects', lambda: run_review(db, ctx, item, 'qc', 'rejected', remarks='Correct geometry'))
                record(f'{label}: complete correction', lambda: run_production(db, ctx, item, quantity='3000'))
            record(f'{label}: QC passes', lambda: run_review(db, ctx, item, 'qc', 'passed'))
            record(f'{label}: QA passes', lambda: run_review(db, ctx, item, 'qa', 'passed'))
            record(f'{label}: ready for delivery', lambda: service.mark_ready_for_delivery(
                db, actor=team['tl'], role='employee', work_package_id=package.id))
            record(f'{label}: deliver file', lambda: service.deliver_item(
                db, actor=team['tl'], role='employee', work_package_item_id=item.id, reference='AUDIT'))
            row = service.build_item_rows(db, [package.id])[0]
            record(f'{label}: delivered once without Finance closure', lambda: require(
                row['delivery_status'] == 'delivered' and workflow.finance_closed_at is None,
                'Incorrect delivery or Finance closure state'))
        except Exception:
            pass
        finally:
            db.rollback()
output = ROOT / 'artifacts/qa/module-audit-operations.json'
output.write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'checks': len(results), 'passed': sum(r['passed'] for r in results),
                  'failures': [r for r in results if not r['passed']]}, indent=2))
engine.dispose()
sys.exit(1 if any(not row['passed'] for row in results) else 0)
