-- Nakshatech V8.1 - Multi-department operational workflow (additive, idempotent).
-- Generalizes the proven Ortho BD -> Finance -> PM -> Team Lead -> Production/QC/QA ->
-- Delivery -> Billing workflow to LiDAR, Mobile Mapping, Laser Scanning and Civil via a
-- single Performing Department column on the existing authoritative project workflow.
-- No DROP / TRUNCATE / DELETE. Safe to run more than once. The backend also applies the
-- same change automatically at startup (ensure_schema_compatibility); this file is the
-- manual / audit copy.

BEGIN;

ALTER TABLE ops_v800_project_workflows ADD COLUMN IF NOT EXISTS performing_department_code VARCHAR(30);

-- Historical rows default to Ortho, the proven template department. Never overwrite a
-- row that already carries a non-null department.
UPDATE ops_v800_project_workflows SET performing_department_code = 'ortho' WHERE performing_department_code IS NULL;

CREATE INDEX IF NOT EXISTS ix_ops_v800_project_workflows_performing_department_code
    ON ops_v800_project_workflows (performing_department_code);

COMMIT;
