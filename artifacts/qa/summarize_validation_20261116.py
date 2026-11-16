"""Generate a current JSON/CSV snapshot from this validation run's evidence."""
import collections
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'artifacts/qa/validation-20261116'


def read_json(name, default=None):
    path = OUTPUT / name
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default


def xml_results(paths):
    counts = collections.Counter()
    files = collections.defaultdict(collections.Counter)
    failures = []
    for path in paths:
        for case in ET.parse(path).getroot().iter('testcase'):
            outcome = 'passed'
            for tag in ('failure', 'error', 'skipped'):
                element = case.find(tag)
                if element is not None:
                    outcome = tag
                    if tag != 'skipped':
                        message = element.get('message', '')
                        failures.append(dict(test_file=case.get('classname'), test=case.get('name'),
                            outcome=tag, message=message, traceback=(element.text or '')[:6000],
                            category='obsolete_finance_approval_fixture' if
                            'Finance approval/return is disabled for BD-origin projects' in (message + (element.text or ''))
                            else 'fixed_date_test_assumption' if case.get('name') ==
                            'test_advance_summary_reflects_saved_request_with_project_value_unchanged'
                            else 'requires_triage'))
                    break
            counts[outcome] += 1
            files[case.get('classname', '')][outcome] += 1
    return dict(outcomes=dict(counts), files=dict(files), failures=failures)


state = read_json('backend-state.json', [])
reports = sorted(OUTPUT.glob('backend-*.xml'))
backend = xml_results(reports)
progress = [json.loads(line) for path in OUTPUT.glob('backend-progress-*.jsonl')
            for line in path.read_text(encoding='utf-8').splitlines() if line]
backend.update(completed_reports=len(reports), progress=dict(collections.Counter(r['outcome'] for r in progress)),
               collected_tests=677,
               state=state, complete=len(state) == 4 and all(row['exit_code'] is not None for row in state))
backend['failure_categories'] = dict(collections.Counter(row['category'] for row in backend['failures']))
summary = dict(generated_at_utc=datetime.now(timezone.utc).isoformat(),
    complete=backend['complete'], overall_result='requires_corrections',
    tested_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    working_tree_changes_included=True, backend=backend,
    confirmed_findings=[
        dict(severity='high', title='Backend allows customer invoicing for a free pilot',
             evidence='Private free-pilot fixture accepted and raised a positive INR 1000 invoice.',
             source='backend/app/modules/operations/lifecycle_service.py:1372', report='management-smoke.json'),
        dict(severity='high', title='Purchase requests missing from Management approval notifications',
             evidence='Pending purchase request has no matching approval-category notification; independently reproduced.',
             source='backend/app/modules/notifications/approval_review.py:30', report='focused-rechecks.xml'),
        dict(severity='medium', title='Reapproval popup missing after revocation with an invoice draft',
             evidence='Revoke endpoint succeeds and tracking can_approve is true, but approval popup is empty.',
             source='backend/app/modules/notifications/approval_review.py:110', report='management-smoke.json'),
    ],
    triage_notes=[
        '177 backend failures/errors stop at the retired Finance approval step during setup.',
        'The advance-summary test assumes 2026-11-15 is in the future; that assumption is false on this run date.',
        'Bad-debt reproposal failed in the full suite and passed in an independent focused rerun; investigate nondeterminism.',
        'Other unclassified failures retain full messages/traces in backend.failures; a passing focused rerun does not erase a baseline failure.',
    ],
    python_syntax=read_json('python-syntax.json'),
    frontend=dict(static_verifications={'passed': 17, 'failed': 0}, typescript='passed',
                  production_build='passed; bundle-size warning', dependency_consistency='passed',
                  browser_routes=read_json('frontend-routes.json')),
    patch_tests=xml_results([OUTPUT / 'patch-tests.xml']) if (OUTPUT / 'patch-tests.xml').exists() else None,
    postgres_original=xml_results([OUTPUT / 'postgres-schema.xml']) if (OUTPUT / 'postgres-schema.xml').exists() else None,
    postgres_current_fixture=xml_results([OUTPUT / 'postgres-current.xml']) if (OUTPUT / 'postgres-current.xml').exists() else None,
    focused_rechecks=xml_results([OUTPUT / 'focused-rechecks.xml']) if (OUTPUT / 'focused-rechecks.xml').exists() else None,
    smoke_checks={name: read_json(f'{name}-smoke.json') for name in ('management', 'operations')},
    browser={name: (read_json(f'browser-{name}.json') or {}).get('stats') for name in ('original', 'current')},
    limitations=[
        'Full backend suite uses private SQLite databases; separate schema/concurrency checks use a disposable PostgreSQL container.',
        'Local backend checks run on Windows with Python 3.11.9; CI specifies Linux and Python 3.12.',
        'Current-workflow reruns change only test setup; original failing results remain available.',
        'Existing automated checks do not exercise every possible user interaction or prove full code coverage.',
        'External email delivery, production storage, real account integrations and production deployment are not validated.',
        'Legacy welcome-browser script references a description element absent from the current page; see welcome-browser.log.',
    ])
(OUTPUT / 'summary.json').write_text(json.dumps(summary, indent=2, default=dict), encoding='utf-8')
with (OUTPUT / 'backend-by-file.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.DictWriter(stream, fieldnames=['file', 'passed', 'failure', 'error', 'skipped'])
    writer.writeheader()
    writer.writerows(dict(file=name, **counts) for name, counts in sorted(backend['files'].items()))
print(json.dumps(dict(complete=backend['complete'], progress=backend['progress'],
                     completed_reports=len(reports), outcomes=backend['outcomes']), indent=2))
