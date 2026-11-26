"""Idempotent, additive-only schema upgrade for the client-billing invoice document (V8.7).

Adds the invoice presentation THEME and the authorised signatory fields to the existing
``project_invoices`` table so historical invoices keep loading unchanged (NULL theme renders
as the classic design, signed defaults to false). Nothing is dropped, renamed or rewritten.

Forward: safe to run any number of times. Backward: older code ignores the nullable columns.
Rollback: no action required — the columns are additive and may be kept permanently
(project convention).
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine

INVOICE_COLUMNS: dict[str, str] = {
    # 'blue_classic' | 'blue_topographic' | 'green_gold_premium' (NULL = classic/legacy)
    "theme": "VARCHAR(40)",
    # Visual authorised-signatory workflow (NOT a statutory DSC signature).
    "signed": "BOOLEAN DEFAULT false",
    "signed_by_id": "INTEGER REFERENCES users(id) ON DELETE SET NULL",
    "signed_at": "TIMESTAMP",
    "signature_invalidated_at": "TIMESTAMP",
}


def ensure_lifecycle_billing_schema_compatibility() -> None:
    inspector = inspect(engine)
    if "project_invoices" not in set(inspector.get_table_names()):
        return
    existing = {column["name"] for column in inspector.get_columns("project_invoices")}
    with engine.begin() as connection:
        for column, ddl in INVOICE_COLUMNS.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE project_invoices ADD COLUMN {column} {ddl}"))
        for ddl in (
            "CREATE INDEX IF NOT EXISTS ix_project_invoices_theme ON project_invoices (theme)",
            "CREATE INDEX IF NOT EXISTS ix_project_invoices_signed_by_id ON project_invoices (signed_by_id)",
            "CREATE INDEX IF NOT EXISTS ix_project_invoices_signed_at ON project_invoices (signed_at)",
        ):
            connection.execute(text(ddl))
