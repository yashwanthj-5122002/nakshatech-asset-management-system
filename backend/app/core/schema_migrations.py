"""Small, repeatable, non-destructive ERP schema migrations.

The FastAPI and cPanel/Passenger startup paths both use initialize_application().
This runner executes only the verified quantity precision migration, before the
production compatibility assertion. Never remove or re-create application data.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

QUANTITY_MIGRATION_ID = "20261125_work_package_quantity_numeric_20_9"
_TABLE = "work_package_item_activities"
_COLUMN = "quantity_completed"
_EXPECTED = (20, 9)
_LEGACY = (18, 6)
_MAX_INTEGER_ABS_EXCLUSIVE = 100_000_000_000  # NUMERIC(20,9) has 11 integer digits.


def _classify_precision(precision: int | None, scale: int | None) -> str:
    if (precision, scale) == _EXPECTED:
        return "current"
    if (precision, scale) == _LEGACY:
        return "legacy"
    raise RuntimeError(
        "Unsupported schema for work_package_item_activities.quantity_completed: "
        f"NUMERIC({precision},{scale}); expected NUMERIC(18,6) or NUMERIC(20,9). "
        "No database values were changed."
    )


def run_startup_schema_migrations(engine: Engine) -> None:
    """Migrate a supported PostgreSQL schema once; safe to call per process.

    PostgreSQL advisory transaction lock serializes simultaneous startup workers.
    The engine.begin() transaction rolls back the change if *any* check fails.
    """
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as connection:
        # Avoid blocking live transactions forever during deployment.
        connection.execute(text("SET LOCAL lock_timeout = '15s'"))
        connection.execute(text("SET LOCAL statement_timeout = '120s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(20261125, 209)"))

        column = connection.execute(
            text(
                """
                SELECT numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'work_package_item_activities'
                  AND column_name = 'quantity_completed'
                """
            )
        ).mappings().one_or_none()

        if column is None:
            # The existing compatibility checks remain responsible for missing
            # tables/columns. Do not try to fabricate a table here.
            logger.warning("Skipping %s: column not found in current schema", QUANTITY_MIGRATION_ID)
            return

        state = _classify_precision(column["numeric_precision"], column["numeric_scale"])

        if state == "legacy":
            # NUMERIC(18,6) supports 12 integer digits, but NUMERIC(20,9)
            # supports only 11. Abort rather than truncate or lose data.
            overflow = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM work_package_item_activities
                        WHERE quantity_completed >= 100000000000
                           OR quantity_completed <= -100000000000
                    )
                    """
                )
            ).scalar_one()
            if overflow:
                raise RuntimeError(
                    "Unsafe precision migration: existing quantity_completed values "
                    "do not fit NUMERIC(20,9). Database unchanged; contact the DBA."
                )

            connection.execute(
                text(
                    """
                    ALTER TABLE work_package_item_activities
                    ALTER COLUMN quantity_completed TYPE NUMERIC(20,9)
                    USING quantity_completed::NUMERIC(20,9)
                    """
                )
            )
            logger.info("Safely migrated %s.%s to NUMERIC(20,9)", _TABLE, _COLUMN)
        else:
            logger.info("%s.%s is already NUMERIC(20,9)", _TABLE, _COLUMN)

        # Re-read actual database metadata rather than trusting the ALTER statement.
        verified = connection.execute(
            text(
                """
                SELECT numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'work_package_item_activities'
                  AND column_name = 'quantity_completed'
                """
            )
        ).mappings().one_or_none()
        if verified is None or (
            verified["numeric_precision"], verified["numeric_scale"]
        ) != _EXPECTED:
            raise RuntimeError("Quantity precision verification failed; transaction rolled back")

        # A lightweight audit trail, committed together with the migration.
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS naksha_schema_migrations (
                    migration_id VARCHAR(160) PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO naksha_schema_migrations (migration_id)
                VALUES (:migration_id)
                ON CONFLICT (migration_id) DO NOTHING
                """
            ),
            {"migration_id": QUANTITY_MIGRATION_ID},
        )
