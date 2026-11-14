BEGIN;
ALTER TABLE management_additional_project_requests ALTER COLUMN project_name DROP NOT NULL;
ALTER TABLE management_additional_project_requests ALTER COLUMN scope_text DROP NOT NULL;
COMMIT;
