-- User profile fields: joining date and date of birth.
-- Idempotent so it is safe to run against an existing local database.

ALTER TABLE users ADD COLUMN IF NOT EXISTS joining_date DATE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth DATE;
