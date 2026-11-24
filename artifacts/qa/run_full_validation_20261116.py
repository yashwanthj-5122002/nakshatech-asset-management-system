"""Run existing backend tests in isolated shards, preserving earlier audit reports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'artifacts/qa/validation-20261116'
OUTPUT.mkdir(parents=True, exist_ok=True)
jobs = []
for index in range(4):
    progress = OUTPUT / f'backend-progress-{index}.jsonl'
    progress.write_text('', encoding='utf-8')
    env = dict(os.environ, ERP_AUDIT_SHARD=str(index), ERP_AUDIT_SHARDS='4',
               ERP_AUDIT_PROGRESS=str(progress),
               PYTHONPATH=str(ROOT / 'artifacts/qa') + os.pathsep + os.environ.get('PYTHONPATH', ''),
               PYTHONUNBUFFERED='1')
    log = (OUTPUT / f'backend-{index}.log').open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable, '-m', 'pytest', 'tests', '-q', '--tb=short',
        '-p', 'module_audit_partition', f'--junitxml={OUTPUT / f"backend-{index}.xml"}'],
        cwd=ROOT / 'backend', env=env, stdout=log, stderr=subprocess.STDOUT)
    jobs.append((index, process, log))
while True:
    rows = [dict(shard=index, pid=process.pid, exit_code=process.poll()) for index, process, _ in jobs]
    (OUTPUT / 'backend-state.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    if all(row['exit_code'] is not None for row in rows):
        break
    time.sleep(2)
for _, _, log in jobs:
    log.close()
print(json.dumps(rows, indent=2))
sys.exit(1 if any(row['exit_code'] != 0 for row in rows) else 0)
