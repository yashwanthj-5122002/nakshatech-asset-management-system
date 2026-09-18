BEGIN;

-- Additive audit ledger used only for the exact, user-approved test-data cleanup.
CREATE TABLE IF NOT EXISTS patch_v81_cleanup_audit (
    patch_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    entity_key TEXT NOT NULL,
    payload JSONB NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (patch_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS ix_patch_v81_cleanup_audit_captured_at
    ON patch_v81_cleanup_audit (captured_at DESC);

-- Protected historical records cannot always be hard-deleted because Expense/Travel
-- history must remain intact. Such exact test entities are hidden from operational
-- registers through this additive ledger while all historical foreign keys remain valid.
CREATE TABLE IF NOT EXISTS patch_v81_hidden_entities (
    patch_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT NOT NULL,
    entity_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (patch_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS ix_patch_v81_hidden_entities_type_id
    ON patch_v81_hidden_entities (entity_type, entity_id);

COMMIT;
