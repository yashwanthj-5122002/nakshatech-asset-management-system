from __future__ import annotations

import importlib.util
from pathlib import Path
import shutil

INSTALLER = Path(__file__).resolve().parents[1] / 'apply_project_tracking_patch.py'
spec = importlib.util.spec_from_file_location('project_tracking_installer', INSTALLER)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_installer_registers_route_once_and_avoids_duplicate_nav():
    app = "import type { ReactNode } from 'react'\nconst a = 1\nfunction WithLayout(){return null}\nconst x = <Routes><Route path=\"*\" /></Routes>\n/* ProtectedRoute */"
    updated = mod.edit_app(app)
    assert updated.count('path="/management/project-tracking"') == 1
    assert updated.count('path="/management/project-tracking-sales"') == 1
    assert mod.edit_app(updated) == updated


def test_backend_main_router_is_registered_once():
    original = 'from app.modules.foo import router\napp = FastAPI()\napp.include_router(router)\n'
    updated = mod.edit_backend_main(original)
    assert updated.count('app.include_router(management_project_tracking_router)') == 1
    assert mod.edit_backend_main(updated) == updated


def test_patch_does_not_modify_sales_module(tmp_path: Path):
    old = Path(__file__).resolve().parents[2] / 'repo'
    if not old.is_dir():
        return  # Only available for the local source snapshot smoke test.
    root = tmp_path / 'test_repo'
    shutil.copytree(old, root, ignore=shutil.ignore_patterns('.project_tracking_patch_backups'))
    sales = root / 'backend/app/routers/project_tracking_sales.py'
    before = sales.read_bytes()
    mod.apply(root, dry_run=False)
    assert sales.read_bytes() == before
    assert 'project-tracking' in (root / 'frontend/src/App.tsx').read_text()
    back = sorted((root / '.project_tracking_patch_backups').iterdir())[-1]
    mod.revert(root, back)
    assert sales.read_bytes() == before
