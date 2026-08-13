"""Shared pytest bootstrap and database isolation for backend tests.

The backend test suite imports modules from the top-level ``app`` package.
When pytest is invoked through its console entry point inside the Docker
container, the repository backend root is not guaranteed to be present on
``sys.path`` during test-module collection. Add it once here before pytest
imports individual test modules.

More importantly, some test modules import application code during collection.
If the application database engine is first created from the normal Docker
``DATABASE_URL``, later tests can accidentally share local application data and
become order-dependent. Pin the application engine to one throwaway SQLite file
before any test module is imported, then rebuild that schema before every test.
This keeps tests deterministic and prevents QA fixtures from touching the normal
local database.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import uuid

import pytest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

PYTEST_DB = Path(tempfile.gettempdir()) / f"nakshatech_pytest_{uuid.uuid4().hex}.db"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{PYTEST_DB}"
os.environ.setdefault("JWT_SECRET", "pytest-suite-secret-only-change-me-32-characters")
os.environ.setdefault("EMAIL_DELIVERY_MODE", "console")
os.environ.setdefault("NAKSHA_COPILOT_ENABLED", "false")
os.environ.setdefault("LOCAL_BACKUP_AGENT_ENABLED", "false")

# Import the database module now, before test-module collection can import any
# application router/service and bind the global engine to another DATABASE_URL.
from app.core.database import Base, engine  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_application_database():
    """Give every backend test a clean application schema.

    Tests that create their own independent SQLAlchemy engine remain unaffected;
    this fixture only resets the application's shared ``app.core.database``
    engine used by runtime-level tests.
    """

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    engine.dispose()
    PYTEST_DB.unlink(missing_ok=True)
