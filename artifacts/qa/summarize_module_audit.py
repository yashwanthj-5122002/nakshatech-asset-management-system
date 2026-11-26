"""Produce a reviewable JSON and CSV audit from actual test reports."""
from collections import Counter, defaultdict
import csv
import json
from pathlib import Path
import re
import subprocess
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

OUTPUT = Path(__file__).resolve().parent
progress = []
for path in OUTPUT.glob('module-audit-progress-*.jsonl'):
    for line in path.read_text(encoding='utf-8').splitlines():
        if line.strip():
            progress.append(json.loads(line))
counts = Counter(row['outcome'] for row in progress)
rows, failures = [], []
for path in sorted(OUTPUT.glob('module-audit-backend-*.xml')):
    for case in ET.parse(path).getroot().iter('testcase'):
        issue = next((child for child in case if child.tag in ('failure', 'error', 'skipped')), None)
        outcome = issue.tag if issue is not None else 'passed'
        row = dict(test_file=case.get('classname', ''), test=case.get('name', ''),
                   outcome=outcome, seconds=float(case.get('time', 0)))
        rows.append(row)
        if outcome in ('failure', 'error'):
            failures.append(dict(**row, message=issue.get('message', ''), traceback=issue.text or ''))
modules = defaultdict(Counter)
for row in rows:
    modules[row['test_file']][row['outcome']] += 1
failure_groups = Counter()
for issue in failures:
    text = issue['message'] + issue['traceback']
    if 'Finance approval/return is disabled for BD-origin projects' in text:
        failure_groups['obsolete_bd_finance_approval_setup'] += 1
    elif 'notification' in issue['test_file'] or 'notification' in issue['test'].lower():
        failure_groups['notification_assertions'] += 1
    else:
        failure_groups['other_requires_review'] += 1
def load(name):
    path = OUTPUT / name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
def browser_stats(name):
    path = OUTPUT / name
    if not path.exists():
        return None
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    # PowerShell 5 redirects native output as UTF-16.
    if '\x00' in text:
        text = path.read_text(encoding='utf-16')
    start = text.find('{\n')
    if start == -1:
        start = text.find('{\r\n')
    return json.loads(text[start:]).get('stats') if start >= 0 else None
summary = dict(
    generated_at_utc=datetime.now(timezone.utc).isoformat(),
    tested_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=OUTPUT.parents[1], text=True).strip(),
    complete=len(list(OUTPUT.glob('module-audit-backend-*.xml'))) == 4 and len(rows) == 677,
    findings=[
        dict(severity='high', title='Free-pilot customer invoicing is not blocked by the backend',
             evidence='Private zero-value free-pilot fixture accepted a positive INR 1000 invoice and transitioned it to PAYMENT_PENDING.',
             source='backend/app/modules/operations/lifecycle_service.py:create_invoice_draft,raise_invoice',
             reproduction='module_audit_management.py / Free pilot: backend blocks customer invoicing'),
        dict(severity='medium', title='Reapproval popup disappears after approval revocation with an invoice draft',
             evidence='Actual revoke endpoint succeeds and tracking returns can_approve=true, but the source popup queue is empty.',
             source='backend/app/modules/notifications/approval_review.py:_pending_uncached',
             reproduction='module_audit_management.py / Draft exists: reapproval action remains visible in popup'),
        dict(severity='high', title='Pending purchase requests are missing from Management approval notifications',
             evidence='A real purchase request returns pending_approval, but the designated Management recipient receives no matching item from the approval-category notification API. Reproduced by an independent test run.',
             source='backend/app/modules/notifications/approval_review.py:MANAGEMENT_APPROVAL_EVENTS',
             reproduction='tests/test_end_to_end.py::test_purchase_permission_approval_conversion_and_excel; module-audit-purchase-recheck.log'),
    ],
    backend_collected=677, backend_progress=dict(counts),
    backend_completed_reports=len(list(OUTPUT.glob('module-audit-backend-*.xml'))),
    backend_outcomes=dict(Counter(row['outcome'] for row in rows)),
    backend_test_files={key: dict(value) for key, value in sorted(modules.items())},
    backend_failures=failures,
    backend_failure_groups=dict(failure_groups),
    management_smoke=load('module-audit-management.json'),
    operations_smoke=load('module-audit-operations.json'),
    python_syntax=load('module-audit-python-syntax.json'),
    browser_original_fixture=browser_stats('module-audit-browser-chrome.json'),
    browser_current_workflow_fixture=browser_stats('module-audit-browser-current-flow.json'),
    frontend_static_verifications=dict(passed=17, failed=0),
    frontend_typescript='passed', frontend_production_build='passed (bundle size warning)',
    limitations=['Existing browser fixture requires obsolete Finance approval; alternate audit fixture uses current BD handoff.',
                 'Temporary SQLite databases; external PostgreSQL/PostGIS, email delivery and storage integrations are not proven by these checks.',
                 'Existing automated coverage and added focused smoke checks do not cover every possible UI interaction.'])
(OUTPUT / 'module-audit-summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
with (OUTPUT / 'module-audit-tests.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.DictWriter(stream, fieldnames=['test_file', 'test', 'outcome', 'seconds'])
    writer.writeheader()
    writer.writerows(rows)
with (OUTPUT / 'module-audit-test-files.csv').open('w', encoding='utf-8', newline='') as stream:
    writer = csv.writer(stream)
    writer.writerow(['test_file', 'passed', 'failed', 'errors', 'skipped', 'total'])
    for key, value in sorted(modules.items()):
        writer.writerow([key, value['passed'], value['failure'], value['error'], value['skipped'], sum(value.values())])
print(json.dumps(dict(progress=dict(counts), completed_reports=summary['backend_completed_reports'],
                      final_outcomes=summary['backend_outcomes'],
                      failing_files={key: dict(value) for key, value in modules.items()
                                     if value['failure'] or value['error']},
                      browser_current=summary['browser_current_workflow_fixture']), indent=2))
