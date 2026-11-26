-- V8.5 Bad Debt DUAL management approval (ADDITIVE, IDEMPOTENT, BACKWARD COMPATIBLE).
--
-- No DROP / TRUNCATE / DELETE / RENAME. Safe to run more than once. The table is also
-- created by Base.metadata.create_all at startup (project convention for new tables);
-- this file is the documented manual/migration artifact.
--
-- Why: NakshaTech requires BOTH management approvers (Vinod Sir AND Chethan) to approve
-- a Bad Debt write-off before it becomes financially effective. Each decision is its own
-- append-only row, so approval history is never overwritten, a repeated/concurrent click
-- cannot duplicate the financial effect, and a re-proposal starts a fresh approval cycle
-- (approval rows are scoped to the current cycle by decided_at >= the case proposed_at).
--
-- Historical-data impact: none. The existing project_invoice_bad_debts table and its
-- rows are untouched; the previous single-decision columns (reviewed_by_id/reviewed_at/
-- decision_reason) now record the FINAL approval only. Rollback: drop the new table only
-- if the feature is withdrawn — no existing data is affected.

CREATE TABLE IF NOT EXISTS project_invoice_bad_debt_approvals (
    id                SERIAL PRIMARY KEY,
    bad_debt_id       INTEGER NOT NULL REFERENCES project_invoice_bad_debts(id) ON DELETE CASCADE,
    invoice_id        INTEGER NOT NULL REFERENCES project_invoices(id) ON DELETE CASCADE,
    project_id        INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    approver_key      VARCHAR(20) NOT NULL,
    approver_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    approver_email    VARCHAR(255) NOT NULL,
    decision          VARCHAR(20) NOT NULL,
    comment           TEXT,
    decided_at        TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at        TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_bad_debt_id
    ON project_invoice_bad_debt_approvals (bad_debt_id);
CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_invoice_id
    ON project_invoice_bad_debt_approvals (invoice_id);
CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_project_id
    ON project_invoice_bad_debt_approvals (project_id);
CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_approver_key
    ON project_invoice_bad_debt_approvals (approver_key);
CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_approver_user_id
    ON project_invoice_bad_debt_approvals (approver_user_id);
CREATE INDEX IF NOT EXISTS ix_project_invoice_bad_debt_approvals_decided_at
    ON project_invoice_bad_debt_approvals (decided_at);
