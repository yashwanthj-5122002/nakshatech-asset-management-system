"""Verify the live database has the additive reporting-month schema.

This script is read-only. Run inside the backend container after startup:
    python scripts/verify_reporting_month_schema.py
"""
from __future__ import annotations

from pathlib import Path
import sys

# Allow this file to be run both as `python scripts/<name>.py` and
# as `python -m scripts.<name>` from the backend container.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import inspect

from app.core.database import engine

TABLES = (
    "asset_history",
    "work_records",
    "component_replacements",
    "replacement_records",
    "it_handover_records",
    "it_purchase_records",
)


def main() -> None:
    inspector = inspect(engine)
    available = set(inspector.get_table_names())
    missing_tables = [table for table in TABLES if table not in available]
    if missing_tables:
        raise SystemExit(f"Missing required tables: {', '.join(missing_tables)}")

    missing_columns: list[str] = []
    for table in TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "reporting_month" not in columns:
            missing_columns.append(f"{table}.reporting_month")
    if missing_columns:
        raise SystemExit(f"Missing reporting-month columns: {', '.join(missing_columns)}")

    print("LIVE REPORTING MONTH SCHEMA VERIFIED")
    for table in TABLES:
        print(f"- {table}.reporting_month")


if __name__ == "__main__":
    main()
