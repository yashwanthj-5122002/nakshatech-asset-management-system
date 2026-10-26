-- V8.7 Invoice themes + authorised signatory (ADDITIVE, IDEMPOTENT, BACKWARD COMPATIBLE).
--
-- No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once. The same columns are
-- also ensured at startup by app.modules.operations.lifecycle_schema_compat.
--
-- What changed and why:
--   theme                    -> selects one of the three A4 designs rendered from the SAME
--                               normalized invoice payload:
--                                 blue_classic | blue_topographic | green_gold_premium
--                               NULL keeps the historical (classic) design for legacy rows.
--   signed / signed_by_id / signed_at
--                            -> the application's authorised-signatory workflow (visual
--                               signature + company stamp). This is NOT a statutory
--                               cryptographic DSC signature.
--   signature_invalidated_at -> set when a material edit invalidates a previous signature so
--                               the old sign-off is never represented as approval of changed
--                               financial content. Old signed_at/signed_by are retained for audit.
--
-- Historical-data impact: none. Existing invoices render exactly as before (NULL theme,
-- signed=false). Rollback: no action required (additive nullable columns).

ALTER TABLE project_invoices
    ADD COLUMN IF NOT EXISTS theme VARCHAR(40);

ALTER TABLE project_invoices
    ADD COLUMN IF NOT EXISTS signed BOOLEAN DEFAULT false;

ALTER TABLE project_invoices
    ADD COLUMN IF NOT EXISTS signed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE project_invoices
    ADD COLUMN IF NOT EXISTS signed_at TIMESTAMP;

ALTER TABLE project_invoices
    ADD COLUMN IF NOT EXISTS signature_invalidated_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS ix_project_invoices_theme ON project_invoices (theme);
CREATE INDEX IF NOT EXISTS ix_project_invoices_signed_by_id ON project_invoices (signed_by_id);
CREATE INDEX IF NOT EXISTS ix_project_invoices_signed_at ON project_invoices (signed_at);
