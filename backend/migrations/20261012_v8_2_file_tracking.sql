-- NakshaTech V8.2 - Optional FILE / TILE / ITEM tracking on the EXISTING work packages
-- (additive, idempotent, backward compatible).
-- No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once. The backend also applies
-- the column additions automatically at startup
-- (ensure_production_tracking_schema_compatibility); this file is the manual / audit copy.
--
-- Forward: two new nullable columns on the work-package table plus two brand-new child tables.
--          A work package with NO items keeps working exactly as before (area-level tracking).
-- Backward: prior releases ignore the new tables/columns; existing rows keep loading unchanged.
-- Rollback: no destructive action required; leave everything in place (project convention).

BEGIN;

-- One-day production buffer: original target_date is never modified.
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS production_target_date DATE;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS production_buffer_days INTEGER;

-- Optional per-area file / tile / item master (0..N per work package).
CREATE TABLE IF NOT EXISTS work_package_items (
    id SERIAL PRIMARY KEY,
    work_package_id INTEGER NOT NULL REFERENCES ops_v701_ortho_work_packages(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    item_number VARCHAR(120) NOT NULL,
    item_name VARCHAR(255),
    sequence_no INTEGER,
    planned_quantity NUMERIC(14, 3),
    planned_unit VARCHAR(30),
    production_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    qc_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    qa_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'not_started',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_work_package_items_number UNIQUE (work_package_id, item_number)
);
CREATE INDEX IF NOT EXISTS ix_work_package_items_work_package_id ON work_package_items (work_package_id);
CREATE INDEX IF NOT EXISTS ix_work_package_items_project_id ON work_package_items (project_id);
CREATE INDEX IF NOT EXISTS ix_work_package_items_item_number ON work_package_items (item_number);
CREATE INDEX IF NOT EXISTS ix_work_package_items_status ON work_package_items (status);
CREATE INDEX IF NOT EXISTS ix_work_package_items_is_active ON work_package_items (is_active);
CREATE INDEX IF NOT EXISTS ix_work_package_items_created_at ON work_package_items (created_at);
CREATE INDEX IF NOT EXISTS ix_work_package_items_production_user_id ON work_package_items (production_user_id);
CREATE INDEX IF NOT EXISTS ix_work_package_items_qc_user_id ON work_package_items (qc_user_id);
CREATE INDEX IF NOT EXISTS ix_work_package_items_qa_user_id ON work_package_items (qa_user_id);

-- Append-only per-file stage activity: timings, output, delay reasons.
CREATE TABLE IF NOT EXISTS work_package_item_activities (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    work_package_id INTEGER NOT NULL REFERENCES ops_v701_ortho_work_packages(id) ON DELETE CASCADE,
    work_package_item_id INTEGER NOT NULL REFERENCES work_package_items(id) ON DELETE CASCADE,
    stage VARCHAR(20) NOT NULL,
    employee_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    performed_role VARCHAR(40),
    from_status VARCHAR(40),
    started_at TIMESTAMP,
    ended_at TIMESTAMP,
    duration_seconds INTEGER,
    quantity_completed NUMERIC(14, 3),
    unit VARCHAR(30),
    files_completed INTEGER NOT NULL DEFAULT 0,
    status VARCHAR(40) NOT NULL DEFAULT 'in_progress',
    remarks TEXT,
    delay_category VARCHAR(80),
    affected_item_id INTEGER REFERENCES work_package_items(id) ON DELETE SET NULL,
    delay_reason VARCHAR(255),
    system_malfunction BOOLEAN NOT NULL DEFAULT FALSE,
    delay_remarks TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_project_id ON work_package_item_activities (project_id);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_work_package_id ON work_package_item_activities (work_package_id);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_work_package_item_id ON work_package_item_activities (work_package_item_id);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_stage ON work_package_item_activities (stage);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_employee_user_id ON work_package_item_activities (employee_user_id);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_status ON work_package_item_activities (status);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_started_at ON work_package_item_activities (started_at);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_ended_at ON work_package_item_activities (ended_at);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_created_at ON work_package_item_activities (created_at);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_item_stage ON work_package_item_activities (work_package_item_id, stage);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_employee_stage ON work_package_item_activities (employee_user_id, stage);
CREATE INDEX IF NOT EXISTS ix_work_package_item_activities_stage_status ON work_package_item_activities (stage, status);

COMMIT;
