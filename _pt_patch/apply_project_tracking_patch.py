"""Safe, repeatable patch installer for NakshaTech ERP Project Tracking.

Never changes Docker volumes, env files, database schemas, production/QC/QA,
Finance or Sales modules. Tested against the Nov 3 integration snapshot.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import sys

BASE = Path(__file__).resolve().parent
PAYLOAD = BASE / 'payload'
PAYLOAD_FILES = [
    Path('frontend/src/pages/ProjectTrackingPage.tsx'),
    Path('frontend/src/pages/projectTracking.css'),
    Path('backend/app/routers/management_project_tracking.py'),
    Path('backend/app/routers/project_tracking_progress.py'),
]
WIRED_FILES = [
    Path('frontend/src/App.tsx'),
    Path('frontend/src/components/Layout.tsx'),
    Path('backend/app/main.py'),
]


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def edit_app(text: str) -> str:
    if '<Routes>' not in text or 'WithLayout' not in text or 'ProtectedRoute' not in text:
        raise ValueError('App.tsx does not match the expected React Router layout. Aborting rather than guessing.')
    # Current installations may already import the old page, including via lazy().
    if 'pages/ProjectTrackingSalesPage' in text:
        text = text.replace('pages/ProjectTrackingSalesPage', 'pages/ProjectTrackingPage')
        # A named import will no longer be correct since the new page is a default export.
        text = re.sub(
            r'import\s*\{\s*ProjectTrackingSalesPage\s*\}\s*from\s*([\'\"])\./pages/ProjectTrackingPage\1',
            "import ProjectTrackingSalesPage from './pages/ProjectTrackingPage'", text)
    if "import ProjectTrackingPage from './pages/ProjectTrackingPage'" not in text:
        # Additional route uses this name independently from the old route's alias.
        text = "import ProjectTrackingPage from './pages/ProjectTrackingPage'\n" + text
    for url in ('/management/project-tracking', '/management/project-tracking-sales'):
        if f'path="{url}"' not in text and f"path='{url}'" not in text:
            route = (f'      <Route path="{url}" '
                     "element={<ProtectedRoute roles={['management']}><WithLayout><ProjectTrackingPage /></WithLayout></ProtectedRoute>} />")
            marker = '</Routes>'
            if marker not in text: raise ValueError('Could not locate closing Routes tag')
            # Place before wildcard/catch-all routes when present.
            catchall = re.search(r'^\s*<Route\s+path=[\'\"]\*[\'\"][^\n]*\n', text, flags=re.MULTILINE)
            if catchall:
                text = text[:catchall.start()] + route + '\n' + text[catchall.start():]
            else:
                text = text.replace(marker, route + '\n    ' + marker, 1)
    return text


def edit_layout(text: str) -> str:
    if 'const navItems' not in text or "to: '/management/project-360'" not in text:
        raise ValueError('Layout.tsx management navigation anchor missing. Aborting.')
    lines = text.splitlines(keepends=True)
    output = []
    found_existing = False
    for line in lines:
        if "to: '/management/project-tracking-sales'" in line or 'to: "/management/project-tracking-sales"' in line or "to: '/management/project-tracking'" in line:
            found_existing = True
            line = line.replace('/management/project-tracking-sales', '/management/project-tracking')
            line = re.sub(r"label:\s*'[^']+'", "label: 'Project Tracking'", line, count=1)
            line = re.sub(r"managementLabel:\s*'[^']+'", "managementLabel: 'Project Tracking'", line, count=1)
            line = re.sub(r"managementGroup:\s*'(finance|executive|governance)'", "managementGroup: 'operations'", line, count=1)
            line = re.sub(r"roles:\s*\[[^]]*\]", "roles: ['management']", line, count=1)
        output.append(line)
    text = ''.join(output)
    if not found_existing:
        nav = ("  { to: '/management/project-tracking', label: 'Project Tracking', icon: FolderKanban, "
               "roles: ['management'], group: 'management', managementGroup: 'operations', "
               "managementLabel: 'Project Tracking' },\n")
        lines = text.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if "to: '/management/project-360'" in line:
                lines.insert(i+1, nav)
                break
        else: raise ValueError('Management Project 360 navigation anchor missing')
        text = ''.join(lines)
    return text


def edit_backend_main(text: str) -> str:
    if 'app.include_router(' not in text or 'FastAPI(' not in text:
        raise ValueError('backend/app/main.py does not look like the expected FastAPI app.')
    imp = 'from app.routers.management_project_tracking import router as management_project_tracking_router'
    if imp not in text:
        match = re.search(r'^from app\.\S+\s+import\s+[^\n]+$', text, flags=re.MULTILINE)
        if not match: raise ValueError('Could not locate main.py import insertion point')
        text = text[:match.start()] + imp + '\n' + text[match.start():]
    registration = 'app.include_router(management_project_tracking_router)'
    if registration not in text:
        matches = list(re.finditer(r'^app\.include_router\([^\n]*\)\s*$', text, re.MULTILINE))
        if not matches: raise ValueError('Could not locate FastAPI router registration block')
        m = matches[-1]
        text = text[:m.end()] + '\n' + registration + text[m.end():]
    return text


def changes_for(root: Path):
    for required in WIRED_FILES:
        if not (root / required).is_file():
            raise ValueError(f'Missing expected ERP source: {root / required}')
    # Existing legacy page must be present so this is not applied to the wrong ERP checkout.
    if not (root / 'frontend/src/pages/ProjectTrackingSalesPage.tsx').is_file():
        raise ValueError('Legacy ProjectTrackingSalesPage.tsx was not found. Use the matching ERP source checkout.')
    editors = {
        WIRED_FILES[0]: edit_app,
        WIRED_FILES[1]: edit_layout,
        WIRED_FILES[2]: edit_backend_main,
    }
    result = {}
    for path, func in editors.items():
        original = (root / path).read_bytes()
        # Existing app source is UTF-8/UTF-8 BOM in the ERP checkout.
        encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
        txt = original.decode(encoding)
        rendered = func(txt).encode('utf-8')
        if original.startswith(b'\xef\xbb\xbf'):
            rendered = b'\xef\xbb\xbf' + rendered
        result[path] = (original, rendered)
    for path in PAYLOAD_FILES:
        source = PAYLOAD / path
        if not source.is_file(): raise ValueError(f'Patch payload is missing: {source}')
        original = (root / path).read_bytes() if (root / path).exists() else None
        after = source.read_bytes()
        if original is not None and original != after:
            raise ValueError(f'Patch would replace an unrelated existing file: {root / path}. Aborting.')
        result[path] = (original, after)
    return result


def apply(root: Path, dry_run: bool):
    changes = changes_for(root)
    modified = [(path, before, after) for path, (before, after) in changes.items() if before != after]
    print('Verified ERP root:', root)
    print('Files requiring changes:', len(modified))
    for p, before, after in modified:
        print(' ', 'CREATE' if before is None else 'UPDATE', p.as_posix())
        if dry_run and p in WIRED_FILES:
            a = (before or b'').decode('utf-8-sig').splitlines()
            b = after.decode('utf-8-sig').splitlines()
            print('\n'.join(list(difflib.unified_diff(a, b, fromfile='before', tofile='after', lineterm=''))[:45]))
    if dry_run:
        print('CHECK ONLY: no source files were modified.')
        return
    if not modified:
        print('Already installed: nothing to change.')
        return
    parent = root / '.project_tracking_patch_backups'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = parent / stamp
    backup.mkdir(parents=True, exist_ok=False)
    manifest = []
    for path, before, after in modified:
        if before is not None:
            copy = backup / path
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(before)
        manifest.append({'path': path.as_posix(), 'existed': before is not None,
                         'before_sha256': digest(before) if before is not None else None,
                         'after_sha256': digest(after)})
    (backup / 'manifest.json').write_text(json.dumps({'files': manifest}, indent=2), encoding='utf-8')
    changed = []
    try:
        for path, _, after in modified:
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + '.ptm-tmp')
            tmp.write_bytes(after)
            tmp.replace(target)
            changed.append(path)
    except Exception:
        for path in reversed(changed):
            original = next(item[1] for item in modified if item[0] == path)
            if original is None:
                (root / path).unlink(missing_ok=True)
            else:
                (root / path).write_bytes(original)
        raise
    print('\nPATCH APPLIED. Backups:', backup)
    print('Docker containers and database were NOT touched.')
    print('Next: build backend/frontend with the same Compose configuration you normally use.')


def revert(root: Path, backup: Path):
    manifest_path = backup / 'manifest.json'
    if not manifest_path.is_file(): raise ValueError('Cannot locate backup manifest.')
    data = json.loads(manifest_path.read_text(encoding='utf-8'))
    # Refuse to undo if someone modified one of the patched files afterward.
    for item in data['files']:
        target = root / item['path']
        if not target.is_file() or digest(target.read_bytes()) != item['after_sha256']:
            raise ValueError(f'File has been changed since install: {target}. Nothing reverted.')
    for item in data['files']:
        target = root / item['path']
        if not item['existed']:
            target.unlink()
        else:
            saved = backup / item['path']
            if digest(saved.read_bytes()) != item['before_sha256']:
                raise ValueError(f'Backup verification failed: {saved}')
            shutil.copy2(saved, target)
    print('Patch reversed from:', backup)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, type=Path)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument('--check', action='store_true')
    group.add_argument('--apply', action='store_true')
    group.add_argument('--revert', type=Path)
    args = ap.parse_args()
    root = args.root.expanduser().resolve()
    if not root.is_dir(): raise ValueError(f'ERP root does not exist: {root}')
    if args.revert: revert(root, args.revert.resolve())
    else: apply(root, dry_run=args.check)


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print('PATCH ABORTED:', exc, file=sys.stderr)
        raise SystemExit(1)
