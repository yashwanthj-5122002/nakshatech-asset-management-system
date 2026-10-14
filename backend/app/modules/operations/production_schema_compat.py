"""Idempotent, additive-only schema upgrade for shared production tracking (V8.1).

New tables (``ops_v81_ortho_stage_events``) are created by ``Base.metadata.create_all``;
this routine only ADDS nullable columns and indexes to the EXISTING work-package
table so every historical Ortho/LiDAR/Mobile Mapping/Laser Scanning/Civil row keeps
loading unchanged. Nothing is dropped, renamed, truncated or rewritten.

Forward: safe to run any number of times on PostgreSQL and SQLite.
Backward: old code ignores the new nullable columns; new code treats NULL as
"stage not tracked yet" (``not_started``/``pending`` semantics are derived, not stored).
Rollback: no action required — columns are nullable and unread by prior releases;
they may be left in place permanently (project convention: additive columns are kept).
"""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine

WORK_PACKAGE_COLUMNS = {
    # General (LiDAR Daily Activity: MARCHE LOTTO 3, SUPPLY DATE, REMARKS)
    "lot_batch": "VARCHAR(120)",
    "supply_date": "DATE",
    "remarks": "TEXT",
    # Import stage (IMP_DATE / IMPORTING)
    "import_status": "VARCHAR(30)",
    "imported_at": "TIMESTAMP",
    # DXF stage (DXF_ALLOTMENT assignee + DXF STATUS + date)
    "dxf_status": "VARCHAR(30)",
    "dxf_at": "TIMESTAMP",
    "dxf_user_id": "INTEGER",
    # Inspection stage (INSPECTED DATE and INSPECTED kept as SEPARATE fields)
    "inspection_status": "VARCHAR(30)",
    "inspected_at": "TIMESTAMP",
    # Upload stage (UPLOAD STATUS)
    "upload_status": "VARCHAR(30)",
    "uploaded_at": "TIMESTAMP",
    # V8.2 production buffer (additive; original target_date is never modified)
    "production_target_date": "DATE",
    "production_buffer_days": "INTEGER",
    # V8.3 stage targets + delivery readiness (additive, nullable)
    "qc_target_date": "DATE",
    "qa_target_date": "DATE",
    "ready_for_delivery_by_id": "INTEGER",
    "ready_for_delivery_at": "TIMESTAMP",
    # V8.4 declared physical-file count (additive, nullable)
    "total_files": "INTEGER",
}

# V8.3 per-file columns added to the existing (V8.2) work_package_items table.
WORK_PACKAGE_ITEM_COLUMNS = {
    "production_target_date": "DATE",
    "qc_target_date": "DATE",
    "qa_target_date": "DATE",
    "import_source": "VARCHAR(255)",
}

# V8.4 attempt metadata added to the existing activity table (additive, nullable).
WORK_PACKAGE_ITEM_ACTIVITY_COLUMNS = {
    "attempt_type": "VARCHAR(20)",
    "attempt_number": "INTEGER",
}


def _add_missing(connection, table: str, existing: set[str], columns: dict[str, str]) -> None:
    for name, ddl in columns.items():
        if name not in existing:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def ensure_production_tracking_schema_compatibility() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "ops_v701_ortho_work_packages" in tables:
            existing = {c["name"] for c in inspector.get_columns("ops_v701_ortho_work_packages")}
            _add_missing(connection, "ops_v701_ortho_work_packages", existing, WORK_PACKAGE_COLUMNS)
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_dxf_user_id "
                "ON ops_v701_ortho_work_packages (dxf_user_id)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_current_stage "
                "ON ops_v701_ortho_work_packages (current_stage)"
            ))
        if "ops_v81_ortho_stage_events" in tables:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_package_stage "
                "ON ops_v81_ortho_stage_events (work_package_id, stage_code)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_project "
                "ON ops_v81_ortho_stage_events (project_id)"
            ))
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_event_at "
                "ON ops_v81_ortho_stage_events (event_at)"
            ))
        if "work_package_items" in tables:
            item_existing = {c["name"] for c in inspector.get_columns("work_package_items")}
            _add_missing(connection, "work_package_items", item_existing, WORK_PACKAGE_ITEM_COLUMNS)
            for ddl in (
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_work_package_id ON work_package_items (work_package_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_project_id ON work_package_items (project_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_item_number ON work_package_items (item_number)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_status ON work_package_items (status)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_is_active ON work_package_items (is_active)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_created_at ON work_package_items (created_at)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_production_user_id ON work_package_items (production_user_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_qc_user_id ON work_package_items (qc_user_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_items_qa_user_id ON work_package_items (qa_user_id)",
            ):
                connection.execute(text(ddl))
        if "work_package_item_activities" in tables:
            activity_existing = {c["name"] for c in inspector.get_columns("work_package_item_activities")}
            _add_missing(connection, "work_package_item_activities", activity_existing,
                         WORK_PACKAGE_ITEM_ACTIVITY_COLUMNS)
            for ddl in (
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_project_id ON work_package_item_activities (project_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_work_package_id ON work_package_item_activities (work_package_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_work_package_item_id ON work_package_item_activities (work_package_item_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_stage ON work_package_item_activities (stage)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_employee_user_id ON work_package_item_activities (employee_user_id)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_status ON work_package_item_activities (status)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_item_stage ON work_package_item_activities (work_package_item_id, stage)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_employee_stage ON work_package_item_activities (employee_user_id, stage)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_stage_status ON work_package_item_activities (stage, status)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_started_at ON work_package_item_activities (started_at)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_ended_at ON work_package_item_activities (ended_at)",
                "CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_created_at ON work_package_item_activities (created_at)",
            ):
                connection.execute(text(ddl))
