-- Additive Employee Master identity source for CRM self-registration.
-- This migration never modifies or deletes an existing user or workflow row.

CREATE TABLE IF NOT EXISTS employee_master (
    id SERIAL PRIMARY KEY,
    source_sl_no VARCHAR(40) NOT NULL,
    access_card_no VARCHAR(120) NOT NULL,
    access_card_no_normalized VARCHAR(120) NOT NULL,
    employee_number VARCHAR(120) NOT NULL,
    employee_number_normalized VARCHAR(120) NOT NULL,
    employee_name VARCHAR(255) NOT NULL,
    phone VARCHAR(80) NOT NULL,
    phone_normalized VARCHAR(40) NOT NULL,
    department_raw VARCHAR(160) NOT NULL,
    department_code VARCHAR(80) NOT NULL,
    designation_raw VARCHAR(200) NOT NULL,
    email VARCHAR(255) NOT NULL,
    email_normalized VARCHAR(255) NOT NULL,
    employment_status VARCHAR(40) NOT NULL DEFAULT 'active',
    crm_account_status VARCHAR(40) NOT NULL DEFAULT 'not_registered',
    linked_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    source_batch_id VARCHAR(80) NOT NULL,
    review_reason TEXT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_employee_master_access_card_normalized UNIQUE (access_card_no_normalized),
    CONSTRAINT uq_employee_master_employee_number_normalized UNIQUE (employee_number_normalized),
    CONSTRAINT uq_employee_master_email_normalized UNIQUE (email_normalized),
    CONSTRAINT uq_employee_master_linked_user UNIQUE (linked_user_id)
);

CREATE INDEX IF NOT EXISTS ix_employee_master_source_sl_no ON employee_master (source_sl_no);
CREATE INDEX IF NOT EXISTS ix_employee_master_employee_name ON employee_master (employee_name);
CREATE INDEX IF NOT EXISTS ix_employee_master_department_raw ON employee_master (department_raw);
CREATE INDEX IF NOT EXISTS ix_employee_master_department_code ON employee_master (department_code);
CREATE INDEX IF NOT EXISTS ix_employee_master_employment_status ON employee_master (employment_status);
CREATE INDEX IF NOT EXISTS ix_employee_master_crm_account_status ON employee_master (crm_account_status);
CREATE INDEX IF NOT EXISTS ix_employee_master_source_batch_id ON employee_master (source_batch_id);
CREATE INDEX IF NOT EXISTS ix_employee_master_imported_at ON employee_master (imported_at);
