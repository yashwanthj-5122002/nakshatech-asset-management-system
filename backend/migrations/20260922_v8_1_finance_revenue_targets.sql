-- V8.1 Finance monthly department revenue targets
-- Additive table only. Existing Sales/Revenue/invoice/payment data remains untouched.

CREATE TABLE IF NOT EXISTS finance_revenue_targets (
    id SERIAL PRIMARY KEY,
    month_start DATE NOT NULL,
    department_code VARCHAR(30) NOT NULL,
    target_amount_inr NUMERIC(18, 2) NOT NULL DEFAULT 0,
    created_by_id INTEGER NOT NULL REFERENCES users(id),
    updated_by_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_finance_revenue_target_month_department UNIQUE (month_start, department_code)
);

CREATE INDEX IF NOT EXISTS ix_finance_revenue_targets_month_start
    ON finance_revenue_targets (month_start);

CREATE INDEX IF NOT EXISTS ix_finance_revenue_targets_department_code
    ON finance_revenue_targets (department_code);

CREATE INDEX IF NOT EXISTS ix_finance_revenue_targets_created_by_id
    ON finance_revenue_targets (created_by_id);

CREATE INDEX IF NOT EXISTS ix_finance_revenue_targets_updated_by_id
    ON finance_revenue_targets (updated_by_id);
