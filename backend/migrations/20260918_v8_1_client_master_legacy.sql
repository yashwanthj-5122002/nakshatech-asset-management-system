-- Nakshatech V8.1 Client Master legacy-data compatibility migration
-- Safe/additive intent: preserve existing rows and relax only fields that are blank in the authoritative legacy workbook.
BEGIN;

DO $$
BEGIN
    IF to_regclass('public.finance_clients') IS NULL THEN
        RAISE EXCEPTION 'Expected table finance_clients does not exist; refusing Client Master patch migration';
    END IF;
    IF to_regclass('public.finance_client_master_profiles') IS NULL THEN
        RAISE EXCEPTION 'Expected table finance_client_master_profiles does not exist; refusing Client Master patch migration';
    END IF;
END $$;

ALTER TABLE finance_clients
    ALTER COLUMN client_name DROP NOT NULL,
    ALTER COLUMN contact_person_name DROP NOT NULL,
    ALTER COLUMN contact_person_phone DROP NOT NULL,
    ALTER COLUMN country DROP NOT NULL,
    ALTER COLUMN source_person_name DROP NOT NULL;

ALTER TABLE finance_client_master_profiles
    ADD COLUMN IF NOT EXISTS vendor_code VARCHAR(80),
    ADD COLUMN IF NOT EXISTS client_type VARCHAR(32) DEFAULT 'client',
    ADD COLUMN IF NOT EXISTS task TEXT,
    ADD COLUMN IF NOT EXISTS bd_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS organization_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS contact_person_email VARCHAR(255),
    ADD COLUMN IF NOT EXISTS import_source VARCHAR(255),
    ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP;

UPDATE finance_client_master_profiles
SET client_type = 'client'
WHERE client_type IS NULL OR client_type = '';

ALTER TABLE finance_client_master_profiles
    ALTER COLUMN client_type SET DEFAULT 'client',
    ALTER COLUMN client_type SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_vendor_code
    ON finance_client_master_profiles (vendor_code);
CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_client_type
    ON finance_client_master_profiles (client_type);
CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_bd_name
    ON finance_client_master_profiles (bd_name);
CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_organization_email
    ON finance_client_master_profiles (organization_email);
CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_contact_person_email
    ON finance_client_master_profiles (contact_person_email);
CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_imported_at
    ON finance_client_master_profiles (imported_at);

COMMIT;
