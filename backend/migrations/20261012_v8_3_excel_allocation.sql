-- NakshaTech V8.3 - Team Lead Excel-driven daily activity allocation (additive, idempotent).
-- Adds stage targets (Production / QC / QA), the Ready-for-Delivery confirmation and
-- the per-file import trace. No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once.
-- The backend also applies the same additions automatically at startup
-- (ensure_production_tracking_schema_compatibility); this file is the manual / audit copy.
--
-- Source-of-truth note: the AUTHORITATIVE per-stage deadlines live on work_package_items
-- (selected files inherit the Team Lead targets). The work-package columns hold the area-level
-- rollup used by the area table / AREA MASTER export.
--
-- Forward: NULLABLE columns only; existing rows keep loading (NULL = not set).
-- Backward: prior releases ignore the new columns.
-- Rollback: no destructive action required; columns may be left in place.

BEGIN;

-- Area-level stage targets + delivery readiness confirmation
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS qc_target_date DATE;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS qa_target_date DATE;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS ready_for_delivery_by_id INTEGER;
ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN IF NOT EXISTS ready_for_delivery_at TIMESTAMP;

-- Per-file stage targets (authoritative deadlines) + Excel import trace
ALTER TABLE work_package_items ADD COLUMN IF NOT EXISTS production_target_date DATE;
ALTER TABLE work_package_items ADD COLUMN IF NOT EXISTS qc_target_date DATE;
ALTER TABLE work_package_items ADD COLUMN IF NOT EXISTS qa_target_date DATE;
ALTER TABLE work_package_items ADD COLUMN IF NOT EXISTS import_source VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_ready_for_delivery_at
    ON ops_v701_ortho_work_packages (ready_for_delivery_at);

COMMIT;
