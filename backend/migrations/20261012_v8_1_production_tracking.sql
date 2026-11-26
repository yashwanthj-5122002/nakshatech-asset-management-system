-- NakshaTech V8.1 - Shared Project Production Tracking (additive, idempotent, backward compatible).
-- Revision adds LiDAR-style stage tracking to the EXISTING authoritative work-package engine.
-- No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once. The backend also applies the
-- same changes automatically at startup (ensure_production_tracking_schema_compatibility);
-- this file is the manual / audit copy.
--
-- Forward: adds NULLABLE columns only; historical Ortho/LiDAR/Mobile Mapping/Laser Scanning/Civil
--          rows keep loading unchanged (NULL = stage not tracked yet).
-- Backward: prior releases ignore the new columns; nothing needs to be back-filled.
-- Rollback: no destructive action required; leave columns in place (project convention) or drop
--           them individually during a planned maintenance window if ever desired.

BEGIN;

ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS lot_batch VARCHAR(120);
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS supply_date DATE;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS remarks TEXT;

-- Import stage (IMP_DATE / IMPORTING)
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS import_status VARCHAR(30);
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP;

-- DXF stage (DXF assignee / date / status)
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS dxf_status VARCHAR(30);
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS dxf_at TIMESTAMP;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS dxf_user_id INTEGER;

-- Inspection stage (INSPECTED DATE and INSPECTED remain SEPARATE fields by requirement)
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS inspection_status VARCHAR(30);
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS inspected_at TIMESTAMP;

-- Upload stage (UPLOAD STATUS)
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS upload_status VARCHAR(30);
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS uploaded_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_dxf_user_id ON ops_v701_ortho_work_packages (dxf_user_id);
CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_current_stage ON ops_v701_ortho_work_packages (current_stage);

-- Append-only stage event history for the optional additional stages
CREATE TABLE IF NOT EXISTS ops_v81_ortho_stage_events (
    id SERIAL PRIMARY KEY,
    work_package_id INTEGER NOT NULL REFERENCES ops_v701_ortho_work_packages(id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL,
    stage_code VARCHAR(30) NOT NULL,
    from_status VARCHAR(30),
    to_status VARCHAR(30) NOT NULL,
    actor_user_id INTEGER REFERENCES users(id) ON DELETE RESTRICT,
    actor_role VARCHAR(40),
    quantity NUMERIC(14, 3),
    unit VARCHAR(30),
    remarks TEXT,
    event_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_package_stage ON ops_v81_ortho_stage_events (work_package_id, stage_code);
CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_project ON ops_v81_ortho_stage_events (project_id);
CREATE INDEX IF NOT EXISTS ix_ops_v81_ortho_stage_events_event_at ON ops_v81_ortho_stage_events (event_at);

COMMIT;
