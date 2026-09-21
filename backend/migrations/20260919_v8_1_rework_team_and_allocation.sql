-- V8.1 rework: PM rework-team confirmation + Team Lead rework allocation (with work-context carry-forward).
--
-- Rework work is allocated as a DISTINCT (NEW) work package linked back to its rework cycle and to the original
-- (source) package it relates to. Original work packages are never modified by a rework cycle.
--
-- Idempotent. The backend applies the same statements at startup (app/main.py ensure_schema_compatibility), so
-- running this file by hand is optional.

ALTER TABLE IF EXISTS ops_v701_ortho_work_packages
    ADD COLUMN IF NOT EXISTS rework_cycle_id INTEGER REFERENCES project_rework_cycles(id) ON DELETE SET NULL;

ALTER TABLE IF EXISTS ops_v701_ortho_work_packages
    ADD COLUMN IF NOT EXISTS rework_of_package_id INTEGER REFERENCES ops_v701_ortho_work_packages(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_rework_cycle_id
    ON ops_v701_ortho_work_packages (rework_cycle_id);

CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_rework_of_package_id
    ON ops_v701_ortho_work_packages (rework_of_package_id);

-- How the PM confirmed the rework team for the cycle: 'reuse' (carry the original work context forward) or 'adjust'.
ALTER TABLE IF EXISTS project_rework_cycles
    ADD COLUMN IF NOT EXISTS team_mode VARCHAR(20);

-- A rework package carries its source package's Code forward as a NEW record, so a Code is unique per project for
-- ORIGINAL packages (unchanged rule) and unique per rework cycle for rework packages. Replacement indexes are created
-- before the old blanket constraint is dropped.
CREATE UNIQUE INDEX IF NOT EXISTS uq_ops_v701_project_package_code_orig
    ON ops_v701_ortho_work_packages (project_id, package_code) WHERE rework_cycle_id IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ops_v701_project_package_code_rework
    ON ops_v701_ortho_work_packages (project_id, package_code, rework_cycle_id) WHERE rework_cycle_id IS NOT NULL;

ALTER TABLE IF EXISTS ops_v701_ortho_work_packages
    DROP CONSTRAINT IF EXISTS uq_ops_v701_project_package_code;
