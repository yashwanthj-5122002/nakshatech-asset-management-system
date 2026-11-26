#!/usr/bin/env python3
"""Identify the real NakshaTech HRMS backend code without changing the project.

Usage:
  python NAKSHA_HRMS_FIND_REAL_BACKEND.py
  python NAKSHA_HRMS_FIND_REAL_BACKEND.py --collect

Run from the ERP root or put the script in the ERP root. The optional --collect
copies relevant SOURCE files to a separate local folder for inspection/upload;
it does not change project source files, database records, or Docker services.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

RULES = [
    (r'@router\.(?:get|post|put|patch|delete)\s*\(\s*[\'\"]/(?:hrms/)?(?:me/leave|hr/leave|hr/overview)', 90, 'leave route'),
    (r'/(?:hrms/)?me/leave', 65, 'employee leave API'),
    (r'/(?:hrms/)?hr/leave', 65, 'HR leave API'),
    (r'/(?:hrms/)?hr/overview', 50, 'HR overview API'),
    (r'\bclass\s+(?:\w*Leave\w*|\w*HRMS\w*)\s*\(', 65, 'HRMS/leave model or schema'),
    (r'\b(?:leave_requests|leave_applications|leave_balances|leave_policies)\b', 55, 'leave database entity'),
    (r'\b(?:approved_chargeable_days|requested_calendar_days|pending_chargeable_days)\b', 40, 'leave accounting'),
    (r'\b(?:pending_leaves|leave_history|leave_notifications)\b', 35, 'leave workflow'),
    (r'\b(?:calculate_leave|chargeable_leave|leave_policy|working_weekdays)\b', 25, 'leave calculation or policy'),
]
EXCLUDED = {'.venv', 'venv', 'node_modules', '.git', '__pycache__', 'site-packages', 'dist', 'build', 'backups', 'storage'}


def locate_root(script: Path, cwd: Path) -> Path:
    for start in (cwd, script.parent):
        for base in (start, *start.parents):
            if (base / 'backend' / 'app').is_dir() and (base / 'frontend').is_dir():
                return base
    raise SystemExit('ERP project root not found. Run from E:\\nakshatech-erp-shreeyansh1 (with backend/app and frontend).')


def eligible(path: Path, backend: Path) -> bool:
    rel = path.relative_to(backend)
    if any(part.lower() in EXCLUDED for part in rel.parts):
        return False
    if path.suffix.lower() not in {'.py', '.sql'}:
        return False
    if path.suffix.lower() == '.sql' and not any(k in path.as_posix().lower() for k in ('migration', 'alembic', 'version', 'schema')):
        return False
    return path.stat().st_size <= 1_000_000


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true', help='Copy relevant code files outside the ERP repository')
    args = parser.parse_args()
    root = locate_root(Path(__file__).resolve(), Path.cwd().resolve())
    backend = root / 'backend'
    found = []
    for path in backend.rglob('*'):
        if not path.is_file():
            continue
        try:
            if not eligible(path, backend):
                continue
            source = path.read_text(encoding='utf-8', errors='replace')
        except (OSError, UnicodeError):
            continue
        score = 0
        reasons = []
        for pattern, weight, label in RULES:
            if re.search(pattern, source, re.IGNORECASE):
                score += weight
                reasons.append(label)
        if 'hrms' in path.as_posix().lower() and score:
            score += 25
        if score >= 40:
            found.append((score, path, reasons))
    found.sort(key=lambda x: (-x[0], str(x[1])))
    print('NAKSHA HRMS SOURCE FINDER - READ ONLY')
    print('Project:', root)
    print('Relevant backend files:', len(found))
    print()
    for score, path, reasons in found[:20]:
        print(f'[{score:3d}] {path.relative_to(root)}')
        print('      Matches:', ', '.join(reasons))
    if not found:
        print('No matching HRMS leave backend files found. Confirm this is the running ERP checkout.')
        return 2
    print('\nNOTE: Employee Portal router.py is NOT necessarily the HRMS router.py.')
    if not args.collect:
        print('\nTo copy relevant source files for review, rerun with --collect.')
        return 0

    primary = [path for _, path, _ in found[:8]]
    # Include small sibling model/service/schema modules only where the candidate is HRMS-related.
    selected = set(primary)
    for path in primary:
        if 'hrms' not in path.as_posix().lower():
            continue
        for name in ('router.py', 'models.py', 'schemas.py', 'service.py', 'services.py', 'policies.py', 'calculations.py'):
            candidate = path.parent / name
            if candidate.is_file() and eligible(candidate, backend):
                selected.add(candidate)
    # Avoid accidentally copying dozens of other modules.
    ordered = sorted(selected, key=lambda p: str(p))[:14]
    local_appdata = os.environ.get('LOCALAPPDATA')
    base = (Path(local_appdata) / 'NakshaTech' / 'HRMS_source_review') if local_appdata else (Path.home() / 'NakshaTech' / 'HRMS_source_review')
    dest = base / datetime.now().strftime('%Y%m%d_%H%M%S')
    dest.mkdir(parents=True, exist_ok=False)
    manifest = {'project_root': str(root), 'files': []}
    for index, source in enumerate(ordered, start=1):
        relative = source.relative_to(root)
        # Prefix to avoid name collisions (several different router.py files).
        name = f'{index:02d}_' + '_'.join(relative.parts)
        target = dest / name
        shutil.copy2(source, target)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        manifest['files'].append({'original': str(relative), 'copied': name, 'sha256': digest})
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('\nFILES COPIED OUTSIDE THE REPOSITORY:')
    for item in manifest['files']:
        print(' ', item['original'], '=>', item['copied'])
    print('\nFolder:', dest)
    print('Upload the HRMS-related .py files from that folder for an exact backend patch.')
    print('Review source files before sharing; do not upload .env, passwords, or database dumps.')
    print('NO project source, database, or container was modified.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
