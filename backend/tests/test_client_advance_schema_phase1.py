from sqlalchemy import create_engine, inspect, text

from app.core.database import Base, engine
from app.modules.commercial import models as commercial_models  # noqa: F401
from app.modules.commercial import schema_compat as commercial_schema_compat
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.commercial.advance import (
    ClientAdvanceFollowUp,
    ClientAdvanceStatusHistory,
    ClientAdvanceTransaction,
)


def test_client_advance_tables_are_registered_with_phase1_columns():
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    transaction_columns = {column["name"] for column in inspector.get_columns(ClientAdvanceTransaction.__tablename__)}
    assert {
        "id",
        "project_id",
        "client_id",
        "amount",
        "currency",
        "amount_inr",
        "fx_rate",
        "payment_date",
        "payment_mode",
        "reference_number",
        "bank_reference",
        "attachment",
        "verified_by",
        "created_at",
    } <= transaction_columns

    followup_columns = {column["name"] for column in inspector.get_columns(ClientAdvanceFollowUp.__tablename__)}
    assert {
        "id",
        "project_id",
        "client_id",
        "contact_person",
        "communication_type",
        "remarks",
        "followup_date",
        "next_followup_date",
        "created_by",
        "created_at",
    } <= followup_columns

    history_columns = {column["name"] for column in inspector.get_columns(ClientAdvanceStatusHistory.__tablename__)}
    assert {
        "id",
        "project_id",
        "old_status",
        "new_status",
        "remarks",
        "created_by",
        "created_at",
    } <= history_columns

    assert "expense_claims" not in {
        foreign_key.column.table.name
        for table in (ClientAdvanceTransaction.__table__, ClientAdvanceFollowUp.__table__, ClientAdvanceStatusHistory.__table__)
        for foreign_key in table.foreign_keys
    }


def test_commercial_revision_compatibility_is_additive_and_idempotent(monkeypatch):
    legacy_engine = create_engine("sqlite+pysqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE project_commercial_estimate_revisions "
            "(id INTEGER PRIMARY KEY, payment_terms VARCHAR(255))"
        ))
        connection.execute(text(
            "INSERT INTO project_commercial_estimate_revisions (id, payment_terms) "
            "VALUES (1, '30 percent after PO')"
        ))

    monkeypatch.setattr(commercial_schema_compat, "engine", legacy_engine)
    commercial_schema_compat.ensure_commercial_schema_compatibility()
    commercial_schema_compat.ensure_commercial_schema_compatibility()

    columns = {
        column["name"]: column
        for column in inspect(legacy_engine).get_columns("project_commercial_estimate_revisions")
    }
    assert {
        "advance_required",
        "advance_payment_type",
        "advance_percent",
        "advance_amount",
        "advance_currency_code",
        "expected_advance_date",
        "final_advance_date",
    } <= columns.keys()
    assert all(columns[name]["nullable"] for name in (
        "advance_required",
        "advance_payment_type",
        "advance_percent",
        "advance_amount",
        "advance_currency_code",
        "expected_advance_date",
        "final_advance_date",
    ))

    with legacy_engine.connect() as connection:
        assert connection.execute(text(
            "SELECT payment_terms FROM project_commercial_estimate_revisions WHERE id = 1"
        )).scalar_one() == "30 percent after PO"

    legacy_engine.dispose()
