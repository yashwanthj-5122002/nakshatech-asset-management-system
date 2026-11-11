"""Loopback-only browser fixture server; always uses a fresh temporary database.

This is a test entry point, never imported by the application. No configured
database, accounts, or credentials are used. Closing the process removes fixtures.
"""
import os
from pathlib import Path
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
temporary = tempfile.TemporaryDirectory(prefix="naksha_browser_")
os.environ.update({
    "DATABASE_URL": f"sqlite+pysqlite:///{Path(temporary.name) / 'browser.db'}",
    "JWT_SECRET": uuid.uuid4().hex + uuid.uuid4().hex,
    "TOTP_ENCRYPTION_KEY": uuid.uuid4().hex + uuid.uuid4().hex,
    "ENVIRONMENT": "development", "APP_ENV": "development",
    "SEED_DEFAULT_USERS": "false", "EMAIL_DELIVERY_MODE": "console",
    "ENABLE_BACKGROUND_WATCHER": "false", "LOCAL_BACKUP_AGENT_ENABLED": "false",
    "SEED_OPERATIONS_TEST_USERS_ENABLED": "false", "ENABLE_TEST_EMPLOYEE_SEED": "false",
    "NAKSHA_COPILOT_ENABLED": "false", "LOCAL_TEST_AUTH_BYPASS": "false",
    "CORS_ORIGINS": "http://127.0.0.1:34110", "API_PREFIX": "/api",
    "TRUSTED_HOSTS": "127.0.0.1,localhost", "ROOT_PATH": "",
})

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.batch4_main import app  # noqa: E402
from app.modules.operations import production_items  # noqa: E402
from test_production_master_excel_allocation_v8_3 import (  # noqa: E402
    MASTER_HEADERS, assign_all, import_master, items_of, packages_of, setup_project, xlsx_bytes,
)

Base.metadata.create_all(engine)


@app.post("/__test__/fixture")
def create_browser_fixture(draft: bool = False):
    with SessionLocal() as db:
        ctx = setup_project(db, f"BROWSER{uuid.uuid4().hex[:10]}")
        import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, [["LOT", "CODE", "AREA", "F1", 3000, "m", ""]]))
        package = packages_of(db, ctx)[0]
        item = items_of(db, ctx)[0]
        assign_all(db, ctx, package, [item.id])
        draft_id = None
        if draft:
            draft_item = production_items.add_items(db, actor=ctx["team"]["tl"], role="employee",
                                                    work_package_id=package.id, entries=[{"item_number": "DRAFT"}])[0]
            draft_id = draft_item.id
        actors = {key: {"id": user.id, "token": create_access_token(user.email, user.role)}
                  for key, user in ctx["team"].items()}
        result = {"projectId": ctx["project"].id, "packageId": package.id,
                  "itemId": item.id, "draftId": draft_id, "actors": actors}
        db.commit()
        return result


if __name__ == "__main__":
    import uvicorn
    try:
        uvicorn.run(app, host="127.0.0.1", port=38111)
    finally:
        engine.dispose()
        temporary.cleanup()
