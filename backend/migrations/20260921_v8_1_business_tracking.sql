-- Business / Total-Sell tracking: monthly business done per project, entered by Finance.
-- Idempotent so it is safe to run against an existing local database.

BEGIN;

CREATE TABLE IF NOT EXISTS business_records (
    id                        SERIAL PRIMARY KEY,
    reporting_month           VARCHAR(7)  NOT NULL,
    project_id                INTEGER     NOT NULL REFERENCES finance_projects(id) ON DELETE CASCADE,
    client_id                 INTEGER     REFERENCES finance_clients(id) ON DELETE SET NULL,
    project_manager_user_id   INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    project_manager_name      VARCHAR(255),
    department_code           VARCHAR(40) NOT NULL DEFAULT 'ortho',
    amount_total              NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    amount_released           NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    amount_pending            NUMERIC(16, 2) NOT NULL DEFAULT 0.00,
    currency                  VARCHAR(12) NOT NULL DEFAULT 'INR',
    notes                     TEXT,
    status                    VARCHAR(20) NOT NULL DEFAULT 'submitted',
    verified_by_id            INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    verified_at               TIMESTAMP,
    entered_by_id             INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    created_at                TIMESTAMP   NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMP   NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_business_record_project_month UNIQUE (project_id, reporting_month)
);

CREATE INDEX IF NOT EXISTS ix_business_records_reporting_month ON business_records (reporting_month);
CREATE INDEX IF NOT EXISTS ix_business_records_project_id ON business_records (project_id);
CREATE INDEX IF NOT EXISTS ix_business_records_client_id ON business_records (client_id);
CREATE INDEX IF NOT EXISTS ix_business_records_project_manager_user_id ON business_records (project_manager_user_id);
CREATE INDEX IF NOT EXISTS ix_business_records_department_code ON business_records (department_code);
CREATE INDEX IF NOT EXISTS ix_business_records_status ON business_records (status);

-- The figures are now derived from Billing & Invoices; Decided had no source.
ALTER TABLE business_records DROP COLUMN IF EXISTS amount_decided;

CREATE TABLE IF NOT EXISTS business_record_history (
    id                      SERIAL PRIMARY KEY,
    record_id               INTEGER REFERENCES business_records(id) ON DELETE CASCADE,
    reporting_month         VARCHAR(7) NOT NULL,
    project_id              INTEGER,
    client_id               INTEGER,
    project_manager_user_id INTEGER,
    action                  VARCHAR(40) NOT NULL,
    actor_user_id           INTEGER,
    actor_name              VARCHAR(255),
    actor_role              VARCHAR(40),
    changes                 TEXT,
    created_at              TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_business_record_history_record_id ON business_record_history (record_id);
CREATE INDEX IF NOT EXISTS ix_business_record_history_reporting_month ON business_record_history (reporting_month);
CREATE INDEX IF NOT EXISTS ix_business_record_history_project_id ON business_record_history (project_id);

COMMIT;
