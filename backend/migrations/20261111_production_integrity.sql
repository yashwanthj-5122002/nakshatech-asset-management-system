-- PostgreSQL; requires the existing V8.2/V8.4 production tables.
-- Preserves session history and integer range while widening converted distances.
BEGIN;
SELECT pg_advisory_xact_lock(721941);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM work_package_item_activities WHERE ended_at IS NULL
    GROUP BY work_package_item_id, stage HAVING COUNT(*) > 1
  ) THEN
    RAISE EXCEPTION 'Duplicate open production sessions exist; review and close them before upgrading. No history was deleted.';
  END IF;
END $$;

ALTER TABLE work_package_item_activities
  ALTER COLUMN quantity_completed TYPE NUMERIC(20, 9);
CREATE UNIQUE INDEX IF NOT EXISTS uq_work_package_item_activities_open
  ON work_package_item_activities (work_package_item_id, stage)
  WHERE ended_at IS NULL;
CREATE TABLE IF NOT EXISTS ops_schema_versions (
  version VARCHAR(80) PRIMARY KEY,
  applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO ops_schema_versions (version) VALUES ('20261111_production_integrity')
  ON CONFLICT (version) DO NOTHING;
COMMIT;
