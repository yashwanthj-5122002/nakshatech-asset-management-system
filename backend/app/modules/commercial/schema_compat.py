"""Idempotent, additive-only schema upgrade for the commercial/cost feature.

New tables are created by ``Base.metadata.create_all``; this routine only ADDS nullable columns to the two
existing lifecycle tables and back-fills INR-only history. Nothing is dropped, truncated or rewritten, and no
historical foreign-currency value is invented: INR rows resolve at rate 1 by definition, anything else stays NULL.
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine

INVOICE_COLUMNS = {
    "tax_percent": "NUMERIC(6, 2)",
    "fx_snapshot_id": "INTEGER",
    "fx_rate_to_inr": "NUMERIC(18, 8)",
    "fx_rate_date": "DATE",
    "fx_rate_source": "VARCHAR(120)",
    "fx_rate_mode": "VARCHAR(30)",
    "base_inr": "NUMERIC(18, 2)",
    "tax_inr": "NUMERIC(18, 2)",
    "total_inr": "NUMERIC(18, 2)",
    "fx_locked": "BOOLEAN DEFAULT FALSE",
    "payment_terms": "VARCHAR(255)",
    "po_wo_reference": "VARCHAR(160)",
    "estimate_revision_id": "INTEGER",
    "billing_basis_id": "INTEGER",
    "billed_quantity": "NUMERIC(14, 3)",
    "billed_milestone_id": "INTEGER",
}
ESTIMATE_COLUMNS = {
    "unit_rate": "NUMERIC(18, 4)",
    "estimated_quantity": "NUMERIC(14, 3)",
    "quantity_unit": "VARCHAR(30)",
}
PAYMENT_COLUMNS = {
    "payment_currency": "VARCHAR(3)",
    "fx_snapshot_id": "INTEGER",
    "fx_rate_to_inr": "NUMERIC(18, 8)",
    "fx_rate_date": "DATE",
    "fx_rate_source": "VARCHAR(120)",
    "fx_rate_mode": "VARCHAR(30)",
    "inr_equivalent": "NUMERIC(18, 2)",
    "invoice_inr_equivalent": "NUMERIC(18, 2)",
    "fx_gain_loss_inr": "NUMERIC(18, 2)",
}


def _add_missing(connection, table: str, existing: set[str], columns: dict[str, str]) -> None:
    for name, ddl in columns.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_commercial_schema_compatibility() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "project_invoices" in tables:
            _add_missing(connection, "project_invoices", {c["name"] for c in inspector.get_columns("project_invoices")}, INVOICE_COLUMNS)
            # INR invoices are their own accounting value at rate 1 (definitional, not an estimate).
            connection.execute(text(
                "UPDATE project_invoices SET fx_rate_to_inr = 1, fx_rate_date = invoice_date, "
                "fx_rate_source = 'BASE_CURRENCY', fx_rate_mode = 'BASE_CURRENCY', base_inr = amount, "
                "tax_inr = COALESCE(tax_amount, 0), total_inr = amount + COALESCE(tax_amount, 0), "
                "fx_locked = CASE WHEN status = 'INVOICE_DRAFT' THEN FALSE ELSE TRUE END "
                "WHERE UPPER(currency) = 'INR' AND fx_rate_to_inr IS NULL"
            ))
            connection.execute(text("UPDATE project_invoices SET fx_locked = FALSE WHERE fx_locked IS NULL"))
        if "project_commercial_estimate_revisions" in tables:
            _add_missing(connection, "project_commercial_estimate_revisions", {c["name"] for c in inspector.get_columns("project_commercial_estimate_revisions")}, ESTIMATE_COLUMNS)
        if "project_invoice_payments" in tables:
            _add_missing(connection, "project_invoice_payments", {c["name"] for c in inspector.get_columns("project_invoice_payments")}, PAYMENT_COLUMNS)
            connection.execute(text(
                "UPDATE project_invoice_payments SET payment_currency = 'INR', fx_rate_to_inr = 1, "
                "fx_rate_date = payment_date, fx_rate_source = 'BASE_CURRENCY', fx_rate_mode = 'BASE_CURRENCY', "
                "inr_equivalent = amount, invoice_inr_equivalent = amount, fx_gain_loss_inr = 0 "
                "WHERE inr_equivalent IS NULL AND invoice_id IN (SELECT id FROM project_invoices WHERE UPPER(currency) = 'INR')"
            ))
