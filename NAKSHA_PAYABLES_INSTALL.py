#!/usr/bin/env python3
"""Safe additive NakshaTech Payables installer.

Usage on Windows (copy this script and payables_bundle.zip into ERP root):
  py NAKSHA_PAYABLES_INSTALL.py --check
  py NAKSHA_PAYABLES_INSTALL.py --apply
  py NAKSHA_PAYABLES_INSTALL.py --restore "C:\\Users\\...\\payables-backups\\..."

--check is read-only. --apply preflights ALL edits before writing and saves backup of
three original integration files. No database access and no existing tables changed.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import time
import zipfile

BUNDLE = 'payables_bundle.zip'
NEW_FILES = (
    'backend/app/modules/payables/__init__.py',
    'backend/app/modules/payables/models.py',
    'backend/app/modules/payables/schemas.py',
    'backend/app/modules/payables/service.py',
    'backend/app/modules/payables/router.py',
    'backend/app/modules/payables/migrate.py',
    'frontend/src/features/payables/PayablesPage.tsx',
    'frontend/src/features/payables/payables.css',
)
MAIN = 'backend/app/main.py'
APP = 'frontend/src/App.tsx'
LAYOUT = 'frontend/src/components/Layout.tsx'
OLD_FILES = (MAIN, APP, LAYOUT)


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def add_before(txt: str, anchor: str, snippet: str, *, marker: str) -> str:
    if marker in txt:
        return txt
    if txt.count(anchor) != 1:
        raise RuntimeError(f'Expected one anchor {anchor!r}; found {txt.count(anchor)}. Refusing to overwrite newer layout.')
    return txt.replace(anchor, snippet + anchor, 1)


def patched_main(text: str) -> str:
    text = add_before(text, 'from app.modules.notifications.router import router as notification_router',
        'from app.modules.payables.router import router as payables_router  # NAKSHA_PAYABLES_INTEGRATION\n', marker='NAKSHA_PAYABLES_INTEGRATION')
    text = add_before(text, 'app.include_router(notification_router, prefix=settings.api_prefix)',
        'app.include_router(payables_router, prefix=settings.api_prefix)  # NAKSHA_PAYABLES_ROUTE\n', marker='NAKSHA_PAYABLES_ROUTE')
    return text


def patched_app(text: str) -> str:
    text = add_before(text, "import { Layout } from './components/Layout'", "import { PayablesListPage, PayableNewPage, PayableDetailPage } from './features/payables/PayablesPage' // NAKSHA_PAYABLES_IMPORT\n", marker='NAKSHA_PAYABLES_IMPORT')
    text = add_before(text, '      <Route path="/finance"', '''      {/* NAKSHA_PAYABLES_ROUTES: independent module; existing paths untouched */}
      <Route path="/payables" element={<ProtectedRoute roles={['admin','finance','management']}><WithLayout><PayablesListPage /></WithLayout></ProtectedRoute>} />
      <Route path="/payables/new" element={<ProtectedRoute roles={['admin','finance']}><WithLayout><PayableNewPage /></WithLayout></ProtectedRoute>} />
      <Route path="/payables/:id" element={<ProtectedRoute roles={['admin','finance','management']}><WithLayout><PayableDetailPage /></WithLayout></ProtectedRoute>} />
''', marker='NAKSHA_PAYABLES_ROUTES')
    return text


def patched_layout(text: str) -> str:
    text = add_before(text, "  { to: '/finance', label: 'Finance Dashboard'", "  { to: '/payables', label: 'Payables', icon: FileCheck2, roles: ['admin', 'finance', 'management'], group: 'finance', managementGroup: 'finance', managementLabel: 'Payables' }, // NAKSHA_PAYABLES_NAV\n", marker='NAKSHA_PAYABLES_NAV')
    # Only the two management accounts should see the new sidebar link.
    original = 'const visibleItems = navItems.filter(item => canShowInSidebar(currentUser.role, item))'
    replacement = '''const visibleItems = navItems.filter(item =>
    (item.to !== '/payables' || currentUser.role !== 'management' || ['vinod@nakshatech.com', 'chethan@nakshatech.com'].includes(currentUser.email.toLowerCase())) &&
    canShowInSidebar(currentUser.role, item)
  ) // NAKSHA_PAYABLES_MANAGER_VISIBILITY'''
    if 'NAKSHA_PAYABLES_MANAGER_VISIBILITY' not in text:
        if text.count(original) != 1:
            raise RuntimeError('Layout sidebar-filter anchor missing/changed; no modifications made')
        text = text.replace(original, replacement, 1)
    return text


def calc_plan(root: Path, zip_path: Path):
    for rel in OLD_FILES:
        if not (root / rel).is_file():
            raise RuntimeError('Missing required ERP source: ' + rel)
    with zipfile.ZipFile(zip_path, 'r') as zipped:
        proposed = {}
        for rel in NEW_FILES:
            if rel not in zipped.namelist():
                raise RuntimeError('Bundle missing ' + rel)
            data = zipped.read(rel)
            target = root / rel
            if target.exists() and target.read_bytes() != data:
                raise RuntimeError(f'Refusing to overwrite an existing different file: {rel}')
            if rel.endswith('.py'):
                compile(data, rel, 'exec')
            proposed[rel] = data
    for rel, function in ((MAIN,patched_main),(APP,patched_app),(LAYOUT,patched_layout)):
        original_bytes = (root / rel).read_bytes()
        original = original_bytes.decode('utf-8-sig')
        updated = function(original)
        if updated != original:
            encoded = ('\ufeff' if original_bytes.startswith(b'\xef\xbb\xbf') else '') + updated
            proposed[rel] = encoded.encode('utf-8')
        else:
            proposed[rel] = original_bytes
        if rel.endswith('.py'):
            compile(proposed[rel], rel, 'exec')
    return proposed


def base_backup_dir() -> Path:
    if os.name == 'nt':
        return Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'NakshaTech' / 'payables-backups'
    return Path.home() / '.local' / 'share' / 'NakshaTech' / 'payables-backups'


def do_apply(root: Path, proposed: dict[str,bytes]):
    updates = [rel for rel, data in proposed.items() if not (root/rel).exists() or (root/rel).read_bytes() != data]
    if not updates:
        print('Payables integration already installed. No files changed.')
        return
    stamp = time.strftime('%Y%m%d-%H%M%S')
    backup = base_backup_dir() / f'payables-{stamp}'
    if backup.exists():
        raise RuntimeError('Backup collision; retry a moment later')
    backup.mkdir(parents=True)
    manifest = {'root': str(root), 'updated': updates, 'existing': {}, 'created_by': 'NAKSHA_PAYABLES_INSTALL.py'}
    for rel in updates:
        path = root / rel
        if path.exists():
            manifest['existing'][rel] = hash_bytes(path.read_bytes())
            dest = backup / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    (backup/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    written = []
    try:
        for rel in updates:
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + '.payables-temp')
            if temp.exists():
                raise RuntimeError(f'Staging conflict: {temp}')
            with temp.open('xb') as f:
                f.write(proposed[rel])
            temp.replace(dest)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            dest = root / rel
            if rel in manifest['existing']:
                shutil.copy2(backup / rel, dest)
            else:
                dest.unlink(missing_ok=True)
        raise
    print('PAYABLES FILES APPLIED. Backup:', backup)
    print('Changed:', ', '.join(updates))
    print('Database NOT migrated by this installer; test in a backed-up UAT environment first.')


def restore(root: Path, location: Path):
    manifest_path = location / 'manifest.json'
    if not manifest_path.exists():
        raise RuntimeError('No valid backup manifest in ' + str(location))
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if str(root) != manifest['root']:
        raise RuntimeError('Backup belongs to a different project root')
    for rel in manifest['updated']:
        path = root / rel
        if rel in manifest['existing']:
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(location / rel, path)
        else:
            path.unlink(missing_ok=True)
    print('Original source files restored from', location)
    print('Database not altered by restore.')


def main() -> int:
    ap = argparse.ArgumentParser()
    act = ap.add_mutually_exclusive_group(required=True)
    act.add_argument('--check', action='store_true')
    act.add_argument('--apply', action='store_true')
    act.add_argument('--restore', metavar='BACKUP_DIRECTORY')
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    opts = ap.parse_args()
    root = opts.root.resolve()
    try:
        if opts.restore:
            restore(root, Path(opts.restore).resolve());return 0
        proposed = calc_plan(root, root / BUNDLE if (root / BUNDLE).is_file() else Path(__file__).resolve().parent / BUNDLE)
        updates = [rel for rel,data in proposed.items() if not (root / rel).exists() or (root / rel).read_bytes() != data]
        print('Preflight OK:', len(proposed), 'files checked;', len(updates), 'will change.')
        for rel in updates:
            print(('NEW ' if not (root / rel).exists() else 'EDIT') + '  ' + rel)
        if opts.apply:
            do_apply(root, proposed)
        else:
            print('Read-only check complete. Use --apply to install (no DB changes).')
        return 0
    except Exception as exc:
        print('STOP - NO UNSAFE OVERWRITE:', exc, file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
