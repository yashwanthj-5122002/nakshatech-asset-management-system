-- Nakshatech V8.1 - Commercial workflow alignment (additive, idempotent, backward compatible).
-- Revision 1 is entered with the project; PM billing basis; unit-rate / milestone billing structure.
-- No DROP / TRUNCATE / DELETE. Safe to run more than once. The backend also applies the same changes
-- automatically at startup (ensure_commercial_schema_compatibility); this file is the manual / audit copy.

BEGIN;

-- 1. Existing commercial estimate revisions: unit-rate billing basis
ALTER TABLE project_commercial_estimate_revisions ADD COLUMN IF NOT EXISTS unit_rate NUMERIC(18, 4);
ALTER TABLE project_commercial_estimate_revisions ADD COLUMN IF NOT EXISTS estimated_quantity NUMERIC(14, 3);
ALTER TABLE project_commercial_estimate_revisions ADD COLUMN IF NOT EXISTS quantity_unit VARCHAR(30);

-- 2. Existing client invoices: traceability to the approved commercial basis / PM billing basis
ALTER TABLE project_invoices ADD COLUMN IF NOT EXISTS estimate_revision_id INTEGER;
ALTER TABLE project_invoices ADD COLUMN IF NOT EXISTS billing_basis_id INTEGER;
ALTER TABLE project_invoices ADD COLUMN IF NOT EXISTS billed_quantity NUMERIC(14, 3);
ALTER TABLE project_invoices ADD COLUMN IF NOT EXISTS billed_milestone_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_project_invoices_estimate_revision_id ON project_invoices (estimate_revision_id);
CREATE INDEX IF NOT EXISTS ix_project_invoices_billed_milestone_id ON project_invoices (billed_milestone_id);

-- 3. New table project_commercial_milestones
CREATE TABLE IF NOT EXISTS project_commercial_milestones (
	id SERIAL NOT NULL,
	revision_id INTEGER NOT NULL,
	project_id INTEGER NOT NULL,
	sequence INTEGER NOT NULL,
	milestone_name VARCHAR(255) NOT NULL,
	percent NUMERIC(6, 2),
	amount NUMERIC(18, 2),
	PRIMARY KEY (id),
	CONSTRAINT uq_project_commercial_milestone_sequence UNIQUE (revision_id, sequence),
	FOREIGN KEY(revision_id) REFERENCES project_commercial_estimate_revisions (id) ON DELETE CASCADE,
	FOREIGN KEY(project_id) REFERENCES finance_projects (id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_project_commercial_milestones_project_id ON project_commercial_milestones (project_id);
CREATE INDEX IF NOT EXISTS ix_project_commercial_milestones_revision_id ON project_commercial_milestones (revision_id);

-- 4. New table project_billing_basis_entries
CREATE TABLE IF NOT EXISTS project_billing_basis_entries (
	id SERIAL NOT NULL,
	project_id INTEGER NOT NULL,
	entry_no INTEGER NOT NULL,
	estimate_revision_id INTEGER,
	billing_type VARCHAR(30) NOT NULL,
	cumulative_billable_quantity NUMERIC(14, 3),
	quantity_unit VARCHAR(30),
	milestone_id INTEGER,
	milestone_name VARCHAR(255),
	completion_percent NUMERIC(5, 2),
	delivery_accepted BOOLEAN NOT NULL,
	acceptance_reference VARCHAR(255),
	pm_remarks TEXT,
	billing_readiness_date DATE,
	confirmed_by_id INTEGER NOT NULL,
	confirmed_at TIMESTAMP WITHOUT TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_project_billing_basis_entry UNIQUE (project_id, entry_no),
	FOREIGN KEY(project_id) REFERENCES finance_projects (id) ON DELETE CASCADE,
	FOREIGN KEY(estimate_revision_id) REFERENCES project_commercial_estimate_revisions (id) ON DELETE SET NULL,
	FOREIGN KEY(milestone_id) REFERENCES project_commercial_milestones (id) ON DELETE SET NULL,
	FOREIGN KEY(confirmed_by_id) REFERENCES users (id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS ix_project_billing_basis_entries_confirmed_at ON project_billing_basis_entries (confirmed_at);
CREATE INDEX IF NOT EXISTS ix_project_billing_basis_entries_confirmed_by_id ON project_billing_basis_entries (confirmed_by_id);
CREATE INDEX IF NOT EXISTS ix_project_billing_basis_entries_estimate_revision_id ON project_billing_basis_entries (estimate_revision_id);
CREATE INDEX IF NOT EXISTS ix_project_billing_basis_entries_milestone_id ON project_billing_basis_entries (milestone_id);
CREATE INDEX IF NOT EXISTS ix_project_billing_basis_entries_project_id ON project_billing_basis_entries (project_id);

COMMIT;
