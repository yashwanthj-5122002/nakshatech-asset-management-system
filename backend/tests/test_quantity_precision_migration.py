"""Contract checks for the one-time, data-preserving precision migration."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.schema_migrations import _classify_precision, run_startup_schema_migrations


def test_old_and_new_precision_are_the_only_supported_states():
    assert _classify_precision(18, 6) == "legacy"
    assert _classify_precision(20, 9) == "current"
    with pytest.raises(RuntimeError, match="Unsupported schema"):
        _classify_precision(18, 9)


def test_non_postgres_database_is_not_modified():
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"), begin=MagicMock())
    run_startup_schema_migrations(engine)
    engine.begin.assert_not_called()


class _Result:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class _FakeConnection:
    def __init__(self, state=(18, 6), overflow=False):
        self.state = state
        self.overflow = overflow
        self.alter_count = 0
        self.history_count = 0

    def execute(self, statement, params=None):
        sql = str(statement).strip().lower()
        if "select numeric_precision, numeric_scale" in sql:
            if self.state is None:
                return _Result(None)
            p, s = self.state
            return _Result({"numeric_precision": p, "numeric_scale": s})
        if "select exists" in sql:
            return _Result(self.overflow)
        if sql.startswith("alter table"):
            self.alter_count += 1
            self.state = (20, 9)
        if sql.startswith("insert into naksha_schema_migrations"):
            self.history_count += 1
        return _Result(None)


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection):
        self.connection = connection

    def begin(self):
        return _FakeBegin(self.connection)


def test_old_precision_is_migrated_once():
    conn = _FakeConnection()
    engine = _FakeEngine(conn)
    run_startup_schema_migrations(engine)
    run_startup_schema_migrations(engine)
    assert conn.alter_count == 1
    assert conn.history_count == 2  # ON CONFLICT DO NOTHING on second startup


def test_existing_quantity_values_that_do_not_fit_are_rejected():
    conn = _FakeConnection(overflow=True)
    with pytest.raises(RuntimeError, match="Unsafe precision migration"):
        run_startup_schema_migrations(_FakeEngine(conn))
    assert conn.alter_count == 0
    assert conn.history_count == 0


def test_unexpected_precision_is_rejected_without_alteration():
    conn = _FakeConnection(state=(12, 3))
    with pytest.raises(RuntimeError, match="Unsupported schema"):
        run_startup_schema_migrations(_FakeEngine(conn))
    assert conn.alter_count == 0


def test_missing_column_is_left_for_existing_schema_checks():
    conn = _FakeConnection(state=None)
    run_startup_schema_migrations(_FakeEngine(conn))
    assert conn.alter_count == 0
