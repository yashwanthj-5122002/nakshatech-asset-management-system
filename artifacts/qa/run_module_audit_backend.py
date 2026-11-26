"""Run the full existing backend suite in four private database processes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'artifacts/qa'
jobs = []
for index in range(4):
    # Clear only this runner's prior report, so an in-progress rerun cannot look complete.
    (OUTPUT / f'module-audit-backend-{index}.xml').unlink(missing_ok=True)
    env = dict(os.environ, ERP_AUDIT_SHARD=str(index), ERP_AUDIT_SHARDS='4',
               ERP_AUDIT_PROGRESS=str(OUTPUT / f'module-audit-progress-{index}.jsonl'),
               PYTHONPATH=str(OUTPUT) + os.pathsep + os.environ.get('PYTHONPATH', ''),
               PYTHONUNBUFFERED='1')
    Path(env['ERP_AUDIT_PROGRESS']).write_text('', encoding='utf-8')
    log = (OUTPUT / f'module-audit-backend-{index}.log').open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-m', 'pytest', 'tests', '-q', '--tb=short',
        '-p', 'module_audit_partition', f'--junitxml={OUTPUT / f"module-audit-backend-{index}.xml"}'],
        cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT)
    jobs.append((index, process, log))
state = OUTPUT / 'module-audit-shards-state.json'
while True:
    rows = [dict(shard=index, pid=process.pid, exit_code=process.poll()) for index, process, _ in jobs]
    state.write_text(json.dumps(rows, indent=2), encoding='utf-8')
    if all(row['exit_code'] is not None for row in rows):
        break
    time.sleep(2)
for _, _, log in jobs:
    log.close()
print(json.dumps(rows, indent=2))
sys.exit(1 if any(row['exit_code'] != 0 for row in rows) else 0)
