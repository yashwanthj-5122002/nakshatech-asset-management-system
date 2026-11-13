BEGIN;

ALTER TABLE management_additional_project_requests
    ADD COLUMN IF NOT EXISTS project_type VARCHAR(16)
    NOT NULL DEFAULT 'regular';

ALTER TABLE management_additional_project_requests
    ADD COLUMN IF NOT EXISTS pilot_payment_type VARCHAR(16);

CREATE TABLE IF NOT EXISTS management_project_classifications (
    project_id INTEGER PRIMARY KEY
        REFERENCES finance_projects(id) ON DELETE RESTRICT,
    project_type VARCHAR(16) NOT NULL DEFAULT 'regular',
    pilot_payment_type VARCHAR(16),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_mgmt_pilot_classification CHECK (
        (project_type = 'regular' AND pilot_payment_type IS NULL)
        OR
        (project_type = 'pilot' AND pilot_payment_type IN ('free','paid'))
    )
);

CREATE OR REPLACE FUNCTION block_free_management_pilot_invoice()
RETURNS TRIGGER
LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM management_project_classifications
        WHERE project_id = NEW.project_id
          AND project_type = 'pilot'
          AND pilot_payment_type = 'free'
    ) THEN
        RAISE EXCEPTION
            'Customer invoices are prohibited for Free Pilot projects';
    END IF;
    RETURN NEW;
END;
$$;

DO $$
BEGIN
    IF to_regclass('public.project_invoices') IS NULL THEN
        RAISE EXCEPTION
            'Expected project_invoices table not found. Migration stopped.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_block_free_management_pilot_invoice'
          AND tgrelid = 'public.project_invoices'::regclass
    ) THEN
        CREATE TRIGGER trg_block_free_management_pilot_invoice
        BEFORE INSERT OR UPDATE ON public.project_invoices
        FOR EACH ROW
        EXECUTE FUNCTION block_free_management_pilot_invoice();
    END IF;
END;
$$;

COMMIT;
