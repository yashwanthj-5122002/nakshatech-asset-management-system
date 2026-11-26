-- ============================================================================
-- SETUP (probe fixtures only) for the live invoice/payment lifecycle validation.
-- Creates two throwaway finance projects whose workflows are parked at
-- READY_FOR_BILLING so the invoice endpoints can be exercised through the API.
-- Touches NO existing UAT row.
-- ============================================================================
\set ON_ERROR_STOP on

INSERT INTO finance_clients (client_name, created_by_id, created_at, updated_at)
SELECT 'ZZ PROBE CLIENT LIFECYCLE', u.id, now(), now()
FROM users u WHERE u.email = 'finance@nakshatech.com'
  AND NOT EXISTS (SELECT 1 FROM finance_clients c WHERE c.client_name = 'ZZ PROBE CLIENT LIFECYCLE');

INSERT INTO finance_projects (client_id, project_number, project_name, status, created_by_id, created_at, updated_at)
SELECT c.id, 'ZZPROBE-A', 'ZZ PROBE FULL PAYMENT', 'active', c.created_by_id, now(), now()
FROM finance_clients c WHERE c.client_name = 'ZZ PROBE CLIENT LIFECYCLE'
  AND NOT EXISTS (SELECT 1 FROM finance_projects p WHERE p.project_number = 'ZZPROBE-A');

INSERT INTO finance_projects (client_id, project_number, project_name, status, created_by_id, created_at, updated_at)
SELECT c.id, 'ZZPROBE-B', 'ZZ PROBE PARTIAL PAYMENT', 'active', c.created_by_id, now(), now()
FROM finance_clients c WHERE c.client_name = 'ZZ PROBE CLIENT LIFECYCLE'
  AND NOT EXISTS (SELECT 1 FROM finance_projects p WHERE p.project_number = 'ZZPROBE-B');

INSERT INTO ops_v800_project_workflows (
    project_id, bd_owner_user_id, status, quantity_unit, priority, currency,
    commercial_value, created_by_id, updated_by_id, created_at, updated_at)
SELECT p.id, u.id, 'READY_FOR_BILLING', 'nos', 'normal', 'INR',
       10000.00, u.id, u.id, now(), now()
FROM finance_projects p, users u
WHERE p.project_number IN ('ZZPROBE-A','ZZPROBE-B')
  AND u.email = 'bd@nakshatech.com'
  AND NOT EXISTS (SELECT 1 FROM ops_v800_project_workflows w WHERE w.project_id = p.id);

SELECT p.id AS probe_project_id, p.project_number, w.status
FROM finance_projects p JOIN ops_v800_project_workflows w ON w.project_id = p.id
WHERE p.project_number IN ('ZZPROBE-A','ZZPROBE-B') ORDER BY p.project_number;