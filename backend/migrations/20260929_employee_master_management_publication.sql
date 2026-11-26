-- Management controls whether Excel-imported Employee Master records can be shared.
-- Existing imported records start private. Management-approved onboarding records are separate.
CREATE TABLE IF NOT EXISTS employee_master_publication (
    id INTEGER PRIMARY KEY,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
