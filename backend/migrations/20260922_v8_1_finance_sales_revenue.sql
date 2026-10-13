-- V8.1 Finance Sales / Revenue analytics support
-- Additive only: preserves every existing project, commercial revision, invoice and payment row.

ALTER TABLE IF EXISTS project_commercial_estimate_revisions
    ADD COLUMN IF NOT EXISTS projected_payment_date DATE;

CREATE INDEX IF NOT EXISTS ix_project_commercial_estimate_revisions_projected_payment_date
    ON project_commercial_estimate_revisions (projected_payment_date);
