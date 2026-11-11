"""Run the unchanged suite with faster disposable SQLite schema setup.

Disable disk durability only for conftest's UUID-named database in the system
temporary directory. Transactions and per-test schema isolation remain active.
No application or permanent database receives these connection settings.
"""
from pathlib import Path
import sqlite3
import tempfile
import sys

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
TEMP = Path(tempfile.gettempdir()).resolve()


@event.listens_for(Engine, "connect")
def disposable_database_settings(connection, record):
    if not isinstance(connection, sqlite3.Connection):
        return
    cursor = connection.cursor()
    try:
        databases = cursor.execute("PRAGMA database_list").fetchall()
        main = next((row[2] for row in databases if row[1] == "main"), "")
        if not main:
            return
        path = Path(main).resolve()
        if path.parent == TEMP and path.name.startswith("nakshatech_pytest_"):
            cursor.execute("PRAGMA synchronous=OFF")
            cursor.execute("PRAGMA journal_mode=MEMORY")
    finally:
        cursor.close()


if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:] or [
        str(ROOT / "backend/tests"), "-v", "--tb=short",
        f"--junitxml={HERE / 'backend-results.xml'}",
    ]))
