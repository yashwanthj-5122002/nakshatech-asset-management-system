"""Run explicitly with: python -m app.modules.operations.pilot_migrate

Add only pilot registry and conditional non-billable financial-write guards.
No resets, deletes or changes to existing business rows.
"""
from __future__ import annotations
from sqlalchemy import text
from app.core.database import engine

DDL_TABLE = """
CREATE TABLE IF NOT EXISTS ops_pilot_projects (
    project_id BIGINT PRIMARY KEY,
    bd_owner_user_id BIGINT NOT NULL,
    client_data_percentage NUMERIC(5,2) NOT NULL DEFAULT 2.00,
    client_data_reference VARCHAR(500) NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP NULL,
    delivery_reference VARCHAR(500) NULL,
    satisfaction VARCHAR(32) NULL,
    feedback_note TEXT NULL,
    feedback_at TIMESTAMP NULL,
    paid_project_id BIGINT UNIQUE NULL,
    conversion_deferred BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT ck_ops_pilot_pct CHECK (client_data_percentage > 0 AND client_data_percentage <= 100),
    CONSTRAINT ck_ops_pilot_satisfaction CHECK (satisfaction IS NULL OR satisfaction IN ('satisfied','not_satisfied'))
)
"""

TRIGGER_FN = """
CREATE OR REPLACE FUNCTION ops_pilot_reject_financial_write() RETURNS trigger AS $body$
DECLARE pid BIGINT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        pid := OLD.project_id;
    ELSE
        pid := NEW.project_id;
    END IF;
    IF pid IS NOT NULL AND EXISTS (
        SELECT 1 FROM ops_pilot_projects p WHERE p.project_id = pid
    ) THEN
       RAISE EXCEPTION 'Pilot project % is non-billable: monetary records cannot be created or modified in %', pid, TG_TABLE_NAME
         USING ERRCODE='23514';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END;
$body$ LANGUAGE plpgsql
"""

# Intentionally fail closed if financial tables lack project_id: do not claim
# comprehensive protection in that case; administrator must review report.
FINANCIAL_PATTERN = "(invoice|payment|expense|advance|receipt|settlement|revenue|cost|billing|vendor)"


def migrate() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Pilot non-billing database guards require PostgreSQL")
    with engine.begin() as connection:
        connection.execute(text(DDL_TABLE))
        connection.execute(text(TRIGGER_FN))
        candidates = connection.execute(text("""
            SELECT c.table_schema, c.table_name
              FROM information_schema.columns c
             WHERE c.column_name = 'project_id'
               AND c.table_schema = current_schema()
               AND c.table_name ~* :pattern
               AND c.table_name <> 'ops_pilot_projects'
             ORDER BY c.table_name
        """), {"pattern": FINANCIAL_PATTERN}).all()
        if not candidates:
            raise RuntimeError("No financial project_id tables found; refusing to install unguarded pilots")
        # Explicit safe identifier quoting via DB dialect; table names are fetched from DB metadata.
        prep = connection.dialect.identifier_preparer
        for schema, table in candidates:
            qtable = f"{prep.quote_schema(schema)}.{prep.quote(table)}"
            trigger = f"ops_pilot_protect_{table}"
            if len(trigger) > 63:
                raise RuntimeError(f"Trigger identifier too long for {table}")
            qtrigger = prep.quote(trigger)
            connection.execute(text(f"DROP TRIGGER IF EXISTS {qtrigger} ON {qtable}"))
            connection.execute(text(
                f"CREATE TRIGGER {qtrigger} BEFORE INSERT OR UPDATE OR DELETE ON {qtable} "
                "FOR EACH ROW EXECUTE FUNCTION ops_pilot_reject_financial_write()"
            ))
        print("PILOT TABLE READY: ops_pilot_projects")
        print(f"MONETARY TABLE GUARDS INSTALLED: {len(candidates)}")
        for _, table in candidates:
            print(f" - {table}")
        # Visibility: warn when financial-looking tables have no direct project_id.
        missing = connection.execute(text("""
            SELECT t.table_name
              FROM information_schema.tables t
             WHERE t.table_schema=current_schema() AND t.table_type='BASE TABLE'
               AND t.table_name ~* :pattern
               AND NOT EXISTS (
                 SELECT 1 FROM information_schema.columns c
                  WHERE c.table_schema=t.table_schema AND c.table_name=t.table_name AND c.column_name='project_id'
               ) ORDER BY t.table_name
        """), {"pattern":FINANCIAL_PATTERN}).all()
        if missing:
            print("FINANCIAL TABLES WITHOUT DIRECT project_id - check indirect write paths:")
            for (table,) in missing:
                print(f" - {table}")
    print("MIGRATION COMPLETE: existing project data remains unchanged")


if __name__ == "__main__":
    migrate()
