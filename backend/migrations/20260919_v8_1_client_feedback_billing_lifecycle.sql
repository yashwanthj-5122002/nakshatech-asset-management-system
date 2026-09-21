-- Nakshatech V8.1 client feedback, rework and billing lifecycle.
-- Additive and repeat-safe: no existing table/column/data is dropped or reset.

BEGIN;

CREATE TABLE IF NOT EXISTS project_feedback_requests (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    request_code VARCHAR(80) NOT NULL UNIQUE,
    cycle_number INTEGER NOT NULL,
    recipient_email VARCHAR(255) NOT NULL,
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    message_thread_id VARCHAR(160) NOT NULL UNIQUE,
    status VARCHAR(40) NOT NULL DEFAULT 'sent',
    message TEXT,
    expires_at TIMESTAMP NOT NULL,
    sent_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    sent_at TIMESTAMP NOT NULL DEFAULT NOW(),
    reminder_count INTEGER NOT NULL DEFAULT 0,
    last_reminder_at TIMESTAMP,
    responded_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_feedback_request_cycle UNIQUE (project_id, cycle_number)
);

CREATE TABLE IF NOT EXISTS project_feedback_responses (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    feedback_request_id BIGINT NOT NULL REFERENCES project_feedback_requests(id) ON DELETE CASCADE,
    response_type VARCHAR(40) NOT NULL,
    comments TEXT,
    correction_description TEXT,
    client_name VARCHAR(255),
    client_email VARCHAR(255),
    external_message_id VARCHAR(255),
    classification_status VARCHAR(40) NOT NULL DEFAULT 'pending_bd',
    classified_as VARCHAR(40),
    classified_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    classified_at TIMESTAMP,
    responded_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_feedback_attachments (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    feedback_response_id BIGINT NOT NULL REFERENCES project_feedback_responses(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    storage_key VARCHAR(512) NOT NULL UNIQUE,
    mime_type VARCHAR(120),
    file_size INTEGER,
    content_sha256 VARCHAR(64),
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_rework_cycles (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    cycle_number INTEGER NOT NULL,
    source_feedback_response_id BIGINT NOT NULL REFERENCES project_feedback_responses(id) ON DELETE RESTRICT,
    status VARCHAR(40) NOT NULL DEFAULT 'REWORK_OPEN',
    correction_scope TEXT NOT NULL,
    project_manager_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    team_leader_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    opened_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    opened_at TIMESTAMP NOT NULL DEFAULT NOW(),
    delivered_at TIMESTAMP,
    resubmitted_at TIMESTAMP,
    closed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_rework_cycle_number UNIQUE (project_id, cycle_number),
    CONSTRAINT uq_project_rework_source_response UNIQUE (source_feedback_response_id)
);

CREATE TABLE IF NOT EXISTS project_delivery_versions (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    rework_cycle_id BIGINT REFERENCES project_rework_cycles(id) ON DELETE SET NULL,
    version_number INTEGER NOT NULL,
    delivery_reference VARCHAR(255) NOT NULL,
    notes TEXT,
    delivered_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    delivered_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_delivery_version_number UNIQUE (project_id, version_number)
);

CREATE TABLE IF NOT EXISTS project_change_requests (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    request_code VARCHAR(80) NOT NULL UNIQUE,
    source_feedback_response_id BIGINT NOT NULL REFERENCES project_feedback_responses(id) ON DELETE RESTRICT,
    description TEXT NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'pending',
    commercial_impact NUMERIC(16,2),
    currency VARCHAR(12) NOT NULL DEFAULT 'INR',
    created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decided_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    decision_comments TEXT,
    decided_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_change_request_source_response UNIQUE (source_feedback_response_id)
);

-- Additive: distinguish rework execution driven by a client CORRECTION_REWORK from
-- execution driven by an APPROVED_CHANGE_REQUEST (paid additional scope). Added here
-- (rather than a new migration file) so a single run of this migration produces the
-- final schema whether the tables above are being created for the first time or
-- already existed from an earlier run of this same file.
ALTER TABLE project_rework_cycles
    ADD COLUMN IF NOT EXISTS cycle_type VARCHAR(30) NOT NULL DEFAULT 'CORRECTION_REWORK',
    ADD COLUMN IF NOT EXISTS source_change_request_id BIGINT;

ALTER TABLE project_rework_cycles
    DROP CONSTRAINT IF EXISTS project_rework_cycles_source_change_request_id_fkey;
ALTER TABLE project_rework_cycles
    ADD CONSTRAINT project_rework_cycles_source_change_request_id_fkey
    FOREIGN KEY (source_change_request_id) REFERENCES project_change_requests(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_project_rework_cycles_cycle_type ON project_rework_cycles(cycle_type);
CREATE INDEX IF NOT EXISTS ix_project_rework_cycles_source_change_request_id ON project_rework_cycles(source_change_request_id);

CREATE TABLE IF NOT EXISTS project_invoices (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    invoice_number VARCHAR(100) NOT NULL UNIQUE,
    status VARCHAR(40) NOT NULL DEFAULT 'INVOICE_DRAFT',
    invoice_date DATE NOT NULL,
    due_date DATE NOT NULL,
    amount NUMERIC(16,2) NOT NULL CHECK (amount > 0),
    tax_amount NUMERIC(16,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
    currency VARCHAR(12) NOT NULL DEFAULT 'INR',
    notes TEXT,
    created_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    raised_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    raised_at TIMESTAMP,
    closed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    closed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_project_invoice_due_date CHECK (due_date >= invoice_date)
);

CREATE TABLE IF NOT EXISTS project_invoice_payments (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    invoice_id BIGINT NOT NULL REFERENCES project_invoices(id) ON DELETE CASCADE,
    payment_reference VARCHAR(180) NOT NULL,
    payment_date DATE NOT NULL,
    amount NUMERIC(16,2) NOT NULL CHECK (amount > 0),
    payment_mode VARCHAR(40) NOT NULL DEFAULT 'bank_transfer',
    comments TEXT,
    recorded_by_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_invoice_payment_reference UNIQUE (invoice_id, payment_reference)
);

CREATE TABLE IF NOT EXISTS project_messages (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    sender_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    recipient_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    message TEXT NOT NULL,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_timeline_events (
    id BIGSERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    event_key VARCHAR(180) NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    title VARCHAR(255) NOT NULL,
    details TEXT,
    status VARCHAR(50),
    actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_project_timeline_event_key UNIQUE (project_id, event_key)
);

CREATE INDEX IF NOT EXISTS ix_project_feedback_requests_project_id ON project_feedback_requests(project_id);
CREATE INDEX IF NOT EXISTS ix_project_feedback_requests_status ON project_feedback_requests(status);
CREATE INDEX IF NOT EXISTS ix_project_feedback_requests_expires_at ON project_feedback_requests(expires_at);
CREATE INDEX IF NOT EXISTS ix_project_feedback_responses_project_id ON project_feedback_responses(project_id);
CREATE INDEX IF NOT EXISTS ix_project_feedback_responses_request_id ON project_feedback_responses(feedback_request_id);
CREATE INDEX IF NOT EXISTS ix_project_feedback_responses_classification ON project_feedback_responses(classification_status, classified_as);
CREATE INDEX IF NOT EXISTS ix_project_feedback_attachments_project_id ON project_feedback_attachments(project_id);
CREATE INDEX IF NOT EXISTS ix_project_rework_cycles_project_id ON project_rework_cycles(project_id);
CREATE INDEX IF NOT EXISTS ix_project_rework_cycles_status ON project_rework_cycles(status);
CREATE INDEX IF NOT EXISTS ix_project_delivery_versions_project_id ON project_delivery_versions(project_id);
CREATE INDEX IF NOT EXISTS ix_project_change_requests_project_id ON project_change_requests(project_id);
CREATE INDEX IF NOT EXISTS ix_project_change_requests_status ON project_change_requests(status);
CREATE INDEX IF NOT EXISTS ix_project_invoices_project_id ON project_invoices(project_id);
CREATE INDEX IF NOT EXISTS ix_project_invoices_status ON project_invoices(status);
CREATE INDEX IF NOT EXISTS ix_project_invoices_due_date ON project_invoices(due_date);
CREATE INDEX IF NOT EXISTS ix_project_invoice_payments_project_id ON project_invoice_payments(project_id);
CREATE INDEX IF NOT EXISTS ix_project_invoice_payments_invoice_id ON project_invoice_payments(invoice_id);
CREATE INDEX IF NOT EXISTS ix_project_messages_project_id_created_at ON project_messages(project_id, created_at);
CREATE INDEX IF NOT EXISTS ix_project_messages_recipient_unread ON project_messages(recipient_user_id, is_read);
CREATE INDEX IF NOT EXISTS ix_project_timeline_events_project_occurred ON project_timeline_events(project_id, occurred_at);
CREATE INDEX IF NOT EXISTS ix_project_timeline_events_type ON project_timeline_events(event_type);

COMMIT;
