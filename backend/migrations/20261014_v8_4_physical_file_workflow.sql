-- V8.4 physical-file workflow (ADDITIVE, IDEMPOTENT, BACKWARD COMPATIBLE).
--
-- No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once. The backend also
-- applies the same changes idempotently at startup via
-- app.modules.operations.production_schema_compat (single source for runtime safety).
--
-- What changed and why:
--   1. ops_v701_ortho_work_packages.total_files  -> declared physical-file count for a
--      Lot/Code/Area (source metadata). NULL keeps the legacy "one file per master row"
--      behaviour. Never used to fabricate per-file length.
--   2. work_package_item_activities.attempt_type / attempt_number -> mark each stage
--      attempt as INITIAL or REWORK so rework is a NEW attempt and never inflates the
--      physical-file count. Historical rows keep NULL and are read as the first attempt.
--
-- Historical-data impact: none. Columns are nullable; existing rows keep working and are
-- never rewritten. Rollback: no action required (nullable columns unread by older code);
-- columns may be left in place permanently (project convention).

ALTER TABLE ops_v701_ortho_work_packages
    ADD COLUMN IF NOT EXISTS total_files INTEGER;

ALTER TABLE work_package_item_activities
    ADD COLUMN IF NOT EXISTS attempt_type VARCHAR(20);

ALTER TABLE work_package_item_activities
    ADD COLUMN IF NOT EXISTS attempt_number INTEGER;
