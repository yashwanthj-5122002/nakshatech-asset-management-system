\set ON_ERROR_STOP on
BEGIN;

CREATE TEMP TABLE patch_v81_target_clients ON COMMIT DROP AS
SELECT c.id, c.client_code, c.client_name
FROM finance_clients c
JOIN (VALUES
    ('123TEST123'::text, '123TEST123'::text),
    ('65465465'::text, 'gfsbhfh'::text),
    ('789TEST'::text, 'test789'::text),
    ('NAKSHATEST12345'::text, 'testravi'::text)
) AS target(client_code, client_name)
  ON c.client_code = target.client_code
 AND c.client_name = target.client_name;

-- If one of the requested exact test names exists under a different Client Code, stop for manual review rather than guessing.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM finance_clients c
        WHERE c.client_name IN ('123TEST123', 'gfsbhfh', 'test789', 'testravi')
          AND NOT EXISTS (
              SELECT 1
              FROM (VALUES
                  ('123TEST123'::text, '123TEST123'::text),
                  ('65465465'::text, 'gfsbhfh'::text),
                  ('789TEST'::text, 'test789'::text),
                  ('NAKSHATEST12345'::text, 'testravi'::text)
              ) AS expected(client_code, client_name)
              WHERE expected.client_code = c.client_code
                AND expected.client_name = c.client_name
          )
    ) THEN
        RAISE EXCEPTION 'Cleanup aborted: an exact requested test client name exists with an unexpected Client Code. No guessed cleanup was attempted.';
    END IF;
END $$;

-- Safety guard: none of the exact test rows may be one of the imported legacy Client Master records.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM patch_v81_target_clients t
        JOIN finance_client_master_profiles p ON p.client_id = t.id
        WHERE COALESCE(p.import_source, '') LIKE 'LEGACY_EXCEL%'
    ) THEN
        RAISE EXCEPTION 'Cleanup aborted: an exact test target is marked as a LEGACY_EXCEL Client Master record.';
    END IF;
END $$;

CREATE TEMP TABLE patch_v81_target_projects ON COMMIT DROP AS
SELECT p.id, p.project_code, p.project_name, p.client_id
FROM finance_projects p
JOIN patch_v81_target_clients c ON c.id = p.client_id;

-- Snapshot every exact target before any hard delete or safe archive/hide action.
INSERT INTO patch_v81_cleanup_audit (patch_id, entity_type, entity_id, entity_key, payload)
SELECT
    'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918',
    'finance_client',
    c.id,
    c.client_code,
    to_jsonb(c)
FROM finance_clients c
JOIN patch_v81_target_clients t ON t.id = c.id
ON CONFLICT (patch_id, entity_type, entity_id) DO NOTHING;

INSERT INTO patch_v81_cleanup_audit (patch_id, entity_type, entity_id, entity_key, payload)
SELECT
    'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918',
    'finance_project',
    p.id,
    p.project_code,
    to_jsonb(p)
FROM finance_projects p
JOIN patch_v81_target_projects t ON t.id = p.id
ON CONFLICT (patch_id, entity_type, entity_id) DO NOTHING;

-- Projects with Expense/Travel history must not be hard-deleted. Keep the historical
-- rows and foreign keys intact, but hide only those exact test entities from all
-- operational Client/Project registers through the additive hidden-entity ledger.
CREATE TEMP TABLE patch_v81_protected_projects ON COMMIT DROP AS
SELECT
    p.id,
    p.project_code,
    p.project_name,
    p.client_id,
    (SELECT COUNT(*) FROM expense_claims e WHERE e.project_id = p.id) AS expense_claim_count,
    (SELECT COUNT(*) FROM travel_km_claims t WHERE t.project_id = p.id) AS travel_claim_count,
    (SELECT COUNT(*) FROM travel_km_verification_snapshots v WHERE v.project_id = p.id) AS travel_snapshot_count
FROM patch_v81_target_projects p
WHERE EXISTS (SELECT 1 FROM expense_claims e WHERE e.project_id = p.id)
   OR EXISTS (SELECT 1 FROM travel_km_claims t WHERE t.project_id = p.id)
   OR EXISTS (SELECT 1 FROM travel_km_verification_snapshots v WHERE v.project_id = p.id);

INSERT INTO patch_v81_hidden_entities (patch_id, entity_type, entity_id, entity_key, reason)
SELECT
    'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918',
    'finance_project',
    p.id,
    p.project_code,
    format(
        'Exact approved test project retained only for protected history: expense_claims=%s; travel_km_claims=%s; travel_verification_snapshots=%s',
        p.expense_claim_count,
        p.travel_claim_count,
        p.travel_snapshot_count
    )
FROM patch_v81_protected_projects p
ON CONFLICT (patch_id, entity_type, entity_id)
DO UPDATE SET entity_key = EXCLUDED.entity_key, reason = EXCLUDED.reason, hidden_at = NOW();

INSERT INTO patch_v81_hidden_entities (patch_id, entity_type, entity_id, entity_key, reason)
SELECT DISTINCT
    'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918',
    'finance_client',
    c.id,
    c.client_code,
    'Exact approved test client retained only because a linked test project has protected Expense/Travel history.'
FROM patch_v81_target_clients c
JOIN patch_v81_protected_projects p ON p.client_id = c.id
ON CONFLICT (patch_id, entity_type, entity_id)
DO UPDATE SET entity_key = EXCLUDED.entity_key, reason = EXCLUDED.reason, hidden_at = NOW();

-- Print the exact scope and protected-history decision before mutation.
SELECT 'TARGET_CLIENT' AS record_type, id, client_code AS record_code, client_name AS record_name
FROM patch_v81_target_clients
ORDER BY id;

SELECT
    'TARGET_PROJECT' AS record_type,
    p.id,
    p.project_code AS record_code,
    p.project_name AS record_name,
    CASE WHEN x.id IS NULL THEN 'HARD_DELETE' ELSE 'SAFE_HIDE_PRESERVE_HISTORY' END AS cleanup_action
FROM patch_v81_target_projects p
LEFT JOIN patch_v81_protected_projects x ON x.id = p.id
ORDER BY p.id;

SELECT
    'PROTECTED_HISTORY' AS record_type,
    id,
    project_code,
    project_name,
    expense_claim_count,
    travel_claim_count,
    travel_snapshot_count
FROM patch_v81_protected_projects
ORDER BY id;

-- Hard-delete only exact test projects that have no protected Expense/Travel history.
DELETE FROM finance_projects p
WHERE p.id IN (SELECT id FROM patch_v81_target_projects)
  AND p.id NOT IN (SELECT id FROM patch_v81_protected_projects);

-- Hard-delete only exact test clients for which no linked project remains. Clients that
-- must remain solely to preserve protected-history foreign keys are hidden instead.
DELETE FROM finance_clients c
WHERE c.id IN (SELECT id FROM patch_v81_target_clients)
  AND NOT EXISTS (SELECT 1 FROM finance_projects p WHERE p.client_id = c.id);

-- Final guard: any surviving exact target must be explicitly hidden and may survive only
-- because one of its projects carries protected Expense/Travel history.
DO $$
DECLARE
    visible_clients INTEGER;
    visible_projects INTEGER;
    unsafe_surviving_clients INTEGER;
    unsafe_surviving_projects INTEGER;
    hidden_clients INTEGER;
    hidden_projects INTEGER;
BEGIN
    SELECT COUNT(*) INTO visible_clients
    FROM finance_clients c
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code AND c.client_name = target.client_name
    WHERE NOT EXISTS (
        SELECT 1 FROM patch_v81_hidden_entities h
        WHERE h.patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
          AND h.entity_type = 'finance_client'
          AND h.entity_id = c.id
    );

    SELECT COUNT(*) INTO visible_projects
    FROM finance_projects p
    JOIN patch_v81_target_projects t ON t.id = p.id
    WHERE NOT EXISTS (
        SELECT 1 FROM patch_v81_hidden_entities h
        WHERE h.patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
          AND h.entity_type = 'finance_project'
          AND h.entity_id = p.id
    );

    SELECT COUNT(*) INTO unsafe_surviving_projects
    FROM finance_projects p
    JOIN patch_v81_target_projects t ON t.id = p.id
    WHERE NOT EXISTS (SELECT 1 FROM patch_v81_protected_projects x WHERE x.id = p.id);

    SELECT COUNT(*) INTO unsafe_surviving_clients
    FROM finance_clients c
    JOIN patch_v81_target_clients t ON t.id = c.id
    WHERE NOT EXISTS (
        SELECT 1 FROM patch_v81_protected_projects p WHERE p.client_id = c.id
    );

    SELECT COUNT(*) INTO hidden_clients
    FROM patch_v81_hidden_entities
    WHERE patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
      AND entity_type = 'finance_client'
      AND entity_id IN (SELECT id FROM patch_v81_target_clients);

    SELECT COUNT(*) INTO hidden_projects
    FROM patch_v81_hidden_entities
    WHERE patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
      AND entity_type = 'finance_project'
      AND entity_id IN (SELECT id FROM patch_v81_target_projects);

    IF visible_clients <> 0 OR visible_projects <> 0 THEN
        RAISE EXCEPTION 'Cleanup verification failed: visible_clients=% visible_projects=%', visible_clients, visible_projects;
    END IF;
    IF unsafe_surviving_clients <> 0 OR unsafe_surviving_projects <> 0 THEN
        RAISE EXCEPTION 'Cleanup verification failed: a target survived without protected history. clients=% projects=%', unsafe_surviving_clients, unsafe_surviving_projects;
    END IF;

    RAISE NOTICE 'TARGETED_TEST_CLEANUP_R2|visible_clients=%|visible_projects=%|hidden_clients=%|hidden_projects=%',
        visible_clients, visible_projects, hidden_clients, hidden_projects;
END $$;

COMMIT;
