-- NakshaTech Project Operations V8.1 additive PostgreSQL migration.
-- Repeat-safe: no existing table or row is dropped, truncated, or rewritten.

ALTER TABLE IF EXISTS finance_client_master_profiles
    ADD COLUMN IF NOT EXISTS organization_email VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_organization_email
    ON finance_client_master_profiles (organization_email);

ALTER TABLE IF EXISTS ops_v701_ortho_work_packages
    ADD COLUMN IF NOT EXISTS instructions TEXT;

ALTER TABLE IF EXISTS ops_v709_ortho_daily_updates
    ADD COLUMN IF NOT EXISTS work_type VARCHAR(255);

CREATE INDEX IF NOT EXISTS ix_ops_v709_ortho_daily_updates_work_type
    ON ops_v709_ortho_daily_updates (work_type);

ALTER TABLE IF EXISTS ops_v800_project_workflows
    ADD COLUMN IF NOT EXISTS attachment_references TEXT,
    ADD COLUMN IF NOT EXISTS submission_count INTEGER DEFAULT 0,
    ADD COLUMN IF NOT EXISTS finance_reviewer_id INTEGER,
    ADD COLUMN IF NOT EXISTS finance_reviewed_at TIMESTAMP;

UPDATE ops_v800_project_workflows
SET submission_count = 0
WHERE submission_count IS NULL;

DO $$
BEGIN
    IF to_regclass('public.ops_v800_project_workflows') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'fk_ops_v800_project_workflows_finance_reviewer'
       ) THEN
        ALTER TABLE ops_v800_project_workflows
            ADD CONSTRAINT fk_ops_v800_project_workflows_finance_reviewer
            FOREIGN KEY (finance_reviewer_id) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ix_ops_v800_project_workflows_finance_reviewer_id
    ON ops_v800_project_workflows (finance_reviewer_id);

CREATE INDEX IF NOT EXISTS ix_ops_v800_project_workflows_finance_reviewed_at
    ON ops_v800_project_workflows (finance_reviewed_at);
