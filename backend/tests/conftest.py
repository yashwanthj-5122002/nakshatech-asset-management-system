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
os.environ["EMAIL_DELIVERY_MODE"] = "console"
os.environ.setdefault("NAKSHA_COPILOT_ENABLED", "false")
os.environ.setdefault("LOCAL_BACKUP_AGENT_ENABLED", "false")
# The auth rate limiter is per-IP and process-local. The suite logs in far more
# often than any human would from a single address, so keep it off by default;
# test_auth_rate_limiting.py turns it on for the requests it asserts on.
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")

# NOTE: the application package must NOT be imported at module scope here.
# ``app.core.config`` builds ``settings`` as a module-level singleton on first
# import, and ``app.core.database`` imports it. Importing the app while this
# file is being loaded would freeze ``settings`` *before* test modules are
# collected, so any ``SEED_*`` environment variable a test module assigns at
# import time would arrive too late to take effect. Test modules legitimately
# disagree on those values (for example ``SEED_ADMIN_PASSWORD``), so freezing
# them by collection order makes the suite order-dependent. Deferring the
# import into a fixture lets collection finish first, so the values a test
# module actually sets are the ones the application reads.


@pytest.fixture(scope="session")
def application_engine():
    """Import the application once the test modules have been collected."""

    from app.core.database import Base, engine
    from app.modules.drone import models as drone_models  # noqa: F401

    # Importing the application (not just its engine) is what registers every
    # model mapper on Base.metadata. Without it, create_all only builds the
    # tables a test module happened to import, and a request that touches any
    # other table - the login flow writing audit_events, for example - fails
    # with "no such table". This runs after collection, so settings stay
    # unfrozen until every test module has set its own environment.
    import app.main  # noqa: F401

    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def isolated_application_database(application_engine):
    """Give every backend test a clean application schema.

    Tests that create their own independent SQLAlchemy engine remain unaffected;
    this fixture only resets the application's shared ``app.core.database``
    engine used by runtime-level tests.
    """

    from app.core.database import Base

    Base.metadata.drop_all(bind=application_engine)
    Base.metadata.create_all(bind=application_engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=application_engine)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    PYTEST_DB.unlink(missing_ok=True)

