\set ON_ERROR_STOP on

DO $$
DECLARE
    imported_count INTEGER;
    special_code_count INTEGER;
    visible_test_client_count INTEGER;
    visible_test_project_count INTEGER;
    surviving_test_client_count INTEGER;
    surviving_test_project_count INTEGER;
    unsafe_surviving_project_count INTEGER;
    hidden_client_count INTEGER;
    hidden_project_count INTEGER;
    test_employee_count INTEGER;
    management_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO imported_count
    FROM finance_clients c
    JOIN finance_client_master_profiles p ON p.client_id = c.id
    WHERE COALESCE(p.import_source, '') LIKE 'LEGACY_EXCEL%';

    IF imported_count <> 1009 THEN
        RAISE EXCEPTION 'Client Master regression: expected 1009 imported records, found %', imported_count;
    END IF;

    SELECT COUNT(*) INTO special_code_count
    FROM finance_clients
    WHERE client_code IN ('NT100', 'NT104', 'NT105', 'NT 220', 'NT-568');

    IF special_code_count <> 5 THEN
        RAISE EXCEPTION 'Client Code regression: one or more representative exact codes are missing.';
    END IF;

    SELECT COUNT(*) INTO surviving_test_client_count
    FROM finance_clients c
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code
     AND c.client_name = target.client_name;

    SELECT COUNT(*) INTO visible_test_client_count
    FROM finance_clients c
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code
     AND c.client_name = target.client_name
    WHERE NOT EXISTS (
        SELECT 1
        FROM patch_v81_hidden_entities h
        WHERE h.patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
          AND h.entity_type = 'finance_client'
          AND h.entity_id = c.id
    );

    IF visible_test_client_count <> 0 THEN
        RAISE EXCEPTION 'Targeted cleanup regression: % exact test client(s) remain visible.', visible_test_client_count;
    END IF;

    SELECT COUNT(*) INTO surviving_test_project_count
    FROM finance_projects p
    JOIN finance_clients c ON c.id = p.client_id
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code
     AND c.client_name = target.client_name;

    SELECT COUNT(*) INTO visible_test_project_count
    FROM finance_projects p
    JOIN finance_clients c ON c.id = p.client_id
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code
     AND c.client_name = target.client_name
    WHERE NOT EXISTS (
        SELECT 1
        FROM patch_v81_hidden_entities h
        WHERE h.patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
          AND h.entity_type = 'finance_project'
          AND h.entity_id = p.id
    );

    IF visible_test_project_count <> 0 THEN
        RAISE EXCEPTION 'Targeted cleanup regression: % exact test project(s) remain visible.', visible_test_project_count;
    END IF;

    SELECT COUNT(*) INTO unsafe_surviving_project_count
    FROM finance_projects p
    JOIN finance_clients c ON c.id = p.client_id
    JOIN (VALUES
        ('123TEST123'::text, '123TEST123'::text),
        ('65465465'::text, 'gfsbhfh'::text),
        ('789TEST'::text, 'test789'::text),
        ('NAKSHATEST12345'::text, 'testravi'::text)
    ) AS target(client_code, client_name)
      ON c.client_code = target.client_code
     AND c.client_name = target.client_name
    WHERE NOT EXISTS (SELECT 1 FROM expense_claims e WHERE e.project_id = p.id)
      AND NOT EXISTS (SELECT 1 FROM travel_km_claims t WHERE t.project_id = p.id)
      AND NOT EXISTS (SELECT 1 FROM travel_km_verification_snapshots v WHERE v.project_id = p.id);

    IF unsafe_surviving_project_count <> 0 THEN
        RAISE EXCEPTION 'Targeted cleanup regression: % surviving test project(s) have no protected history and should have been hard-deleted.', unsafe_surviving_project_count;
    END IF;

    SELECT COUNT(*) INTO hidden_client_count
    FROM patch_v81_hidden_entities
    WHERE patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
      AND entity_type = 'finance_client';

    SELECT COUNT(*) INTO hidden_project_count
    FROM patch_v81_hidden_entities
    WHERE patch_id = 'V8_1_MANAGEMENT_FINANCE_VISIBILITY_20260918'
      AND entity_type = 'finance_project';

    IF hidden_project_count <> surviving_test_project_count THEN
        RAISE EXCEPTION 'Protected-history hide ledger mismatch: surviving_projects=% hidden_projects=%', surviving_test_project_count, hidden_project_count;
    END IF;

    IF hidden_client_count <> surviving_test_client_count THEN
        RAISE EXCEPTION 'Protected-history hide ledger mismatch: surviving_clients=% hidden_clients=%', surviving_test_client_count, hidden_client_count;
    END IF;

    SELECT COUNT(*) INTO test_employee_count
    FROM users
    WHERE email IN (
        'employee1.test@nakshatech.com', 'employee2.test@nakshatech.com', 'employee3.test@nakshatech.com',
        'employee4.test@nakshatech.com', 'employee5.test@nakshatech.com', 'employee6.test@nakshatech.com',
        'employee7.test@nakshatech.com', 'employee8.test@nakshatech.com', 'employee9.test@nakshatech.com',
        'employee10.test@nakshatech.com', 'employee11.test@nakshatech.com', 'employee12.test@nakshatech.com',
        'employee13.test@nakshatech.com', 'employee14.test@nakshatech.com', 'employee15.test@nakshatech.com'
    );

    IF test_employee_count <> 15 THEN
        RAISE EXCEPTION 'Employee test-login regression: expected 15 test employee accounts, found %', test_employee_count;
    END IF;

    SELECT COUNT(*) INTO management_count
    FROM users
    WHERE email IN ('vinod@nakshatech.com', 'chethan@nakshatech.com')
      AND role = 'management';

    IF management_count <> 2 THEN
        RAISE EXCEPTION 'Management account regression: Vinod and Chethan management accounts were not both found.';
    END IF;

    RAISE NOTICE 'MANAGEMENT_FINANCE_VALIDATION_R2|imported_clients=%|representative_codes=%|visible_test_clients=%|visible_test_projects=%|protected_clients=%|protected_projects=%|test_employees=%|management_accounts=%',
        imported_count, special_code_count, visible_test_client_count, visible_test_project_count,
        surviving_test_client_count, surviving_test_project_count, test_employee_count, management_count;
END $$;
