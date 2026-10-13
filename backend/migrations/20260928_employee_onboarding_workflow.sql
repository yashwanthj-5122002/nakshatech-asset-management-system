-- Additive: future new-joiner onboarding workflow (HR -> IT -> Management).
-- Also relaxes employee_master.source_sl_no for HR-created rows (new joiners have no
-- XLSX serial number). No existing row is modified or deleted.

CREATE TABLE IF NOT EXISTS employee_onboarding_requests (
    id SERIAL PRIMARY KEY,
    employee_name VARCHAR(255) NOT NULL,
    personal_email VARCHAR(255) NOT NULL,
    personal_email_normalized VARCHAR(255) NOT NULL,
    phone VARCHAR(80) NOT NULL,
    employee_number VARCHAR(120) NOT NULL,
    employee_number_normalized VARCHAR(120) NOT NULL,
    access_card_no VARCHAR(120) NOT NULL,
    access_card_no_normalized VARCHAR(120) NOT NULL,
    department_code VARCHAR(80) NOT NULL,
    designation VARCHAR(200) NOT NULL,
    joining_date TIMESTAMP NULL,
    notes TEXT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'hr_draft',
    official_email VARCHAR(255) NULL,
    official_email_normalized VARCHAR(255) NULL,
    decided_by VARCHAR(255) NULL,
    created_by_user_id INTEGER NOT NULL REFERENCES users(id),
    submitted_to_it_at TIMESTAMP NULL,
    it_approved_by_user_id INTEGER NULL REFERENCES users(id),
    it_approved_at TIMESTAMP NULL,
    management_approved_at TIMESTAMP NULL,
    rejected_by_user_id INTEGER NULL REFERENCES users(id),
    rejected_reason TEXT NULL,
    rejected_at TIMESTAMP NULL,
    employee_master_id INTEGER NULL REFERENCES employee_master(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_personal_email ON employee_onboarding_requests (personal_email);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_personal_email_normalized ON employee_onboarding_requests (personal_email_normalized);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_employee_number_normalized ON employee_onboarding_requests (employee_number_normalized);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_access_card_no_normalized ON employee_onboarding_requests (access_card_no_normalized);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_department_code ON employee_onboarding_requests (department_code);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_status ON employee_onboarding_requests (status);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_official_email ON employee_onboarding_requests (official_email);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_official_email_normalized ON employee_onboarding_requests (official_email_normalized);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_created_by_user_id ON employee_onboarding_requests (created_by_user_id);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_it_approved_by_user_id ON employee_onboarding_requests (it_approved_by_user_id);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_rejected_by_user_id ON employee_onboarding_requests (rejected_by_user_id);
CREATE INDEX IF NOT EXISTS ix_employee_onboarding_requests_employee_master_id ON employee_onboarding_requests (employee_master_id);

ALTER TABLE employee_master ALTER COLUMN source_sl_no DROP NOT NULL;
