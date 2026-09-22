from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine
from app.modules.business.models import BusinessRecord, BusinessRecordHistory


def _add_column_if_missing(connection, table: str, existing: set[str], column: str, ddl: str) -> None:
    if column not in existing:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def ensure_business_schema_compatibility() -> None:
    """Idempotently create/patch the Business tracking tables.

    Fresh databases are already handled by ``Base.metadata.create_all``; this
    routine covers existing databases and future additive columns without ever
    dropping the monthly figures or their history.
    """
    BusinessRecord.__table__.create(bind=engine, checkfirst=True)
    BusinessRecordHistory.__table__.create(bind=engine, checkfirst=True)

    inspector = inspect(engine)
    if "business_records" in set(inspector.get_table_names()):
        columns = {column["name"] for column in inspector.get_columns("business_records")}
        with engine.begin() as connection:
            _add_column_if_missing(connection, "business_records", columns, "department_code", "VARCHAR(40) DEFAULT 'ortho'")
            _add_column_if_missing(connection, "business_records", columns, "project_manager_name", "VARCHAR(255)")
            _add_column_if_missing(connection, "business_records", columns, "verified_by_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL")
            _add_column_if_missing(connection, "business_records", columns, "verified_at", "TIMESTAMP")
            # The figures now come from Billing & Invoices; Decided had no source and is gone.
            # Existence checked in Python (not "IF EXISTS") so this also works against SQLite test databases.
            if "amount_decided" in columns:
                connection.execute(text("ALTER TABLE business_records DROP COLUMN amount_decided"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_business_records_reporting_month ON business_records (reporting_month)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_business_records_project_id ON business_records (project_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_business_records_department_code ON business_records (department_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_business_records_project_manager_user_id ON business_records (project_manager_user_id)"))
