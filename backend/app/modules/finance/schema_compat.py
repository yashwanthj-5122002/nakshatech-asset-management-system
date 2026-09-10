from __future__ import annotations

from decimal import Decimal

from sqlalchemy import inspect, select, text

from app.core.database import SessionLocal, engine
from app.models.entities import utc_now
from app.modules.finance.models import ExpenseClaim, ExpenseClaimPayment


def _add_column_if_missing(connection, table: str, existing: set[str], column: str, ddl: str) -> None:
    if column not in existing:
        connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def ensure_finance_v2_schema_compatibility() -> None:
    """Idempotent Finance-only compatibility upgrade through Finance V5.

    The wider application intentionally still uses create_all plus compatibility
    ALTERs. This routine touches Finance tables only and preserves all historic
    claims/payments/attachments.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "expense_claims" not in tables:
        return

    claim_columns = {column["name"] for column in inspector.get_columns("expense_claims")}
    with engine.begin() as connection:
        _add_column_if_missing(connection, "expense_claims", claim_columns, "finance_approved_amount", "NUMERIC(14, 2)")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "requested_work_start_date", "DATE")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "requested_work_end_date", "DATE")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "approved_work_start_date", "DATE")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "approved_work_end_date", "DATE")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "settlement_due_date", "DATE")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "parent_advance_claim_id", "INTEGER REFERENCES expense_claims(id) ON DELETE RESTRICT")
        _add_column_if_missing(connection, "expense_claims", claim_columns, "settlement_status", "VARCHAR(50) DEFAULT 'not_required'")

        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_finance_approved_amount ON expense_claims (finance_approved_amount)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_requested_work_start_date ON expense_claims (requested_work_start_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_requested_work_end_date ON expense_claims (requested_work_end_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_approved_work_start_date ON expense_claims (approved_work_start_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_approved_work_end_date ON expense_claims (approved_work_end_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_settlement_due_date ON expense_claims (settlement_due_date)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_parent_advance_claim_id ON expense_claims (parent_advance_claim_id)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claims_settlement_status ON expense_claims (settlement_status)"))

        connection.execute(text(
            "UPDATE expense_claims SET finance_approved_amount = total_amount "
            "WHERE finance_approved_amount IS NULL AND status IN ('finance_approved', 'partially_paid', 'paid')"
        ))
        connection.execute(text(
            "UPDATE expense_claims SET settlement_status = CASE "
            "WHEN claim_type = 'advance' AND COALESCE(paid_amount, 0) > 0 THEN 'open' "
            "WHEN claim_type = 'advance' THEN 'pending_release' "
            "WHEN claim_type = 'additional_advance' THEN 'covered_by_parent' "
            "ELSE 'not_required' END "
            "WHERE settlement_status IS NULL OR settlement_status = '' OR settlement_status = 'not_required'"
        ))

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "finance_clients" in tables:
        columns = {column["name"] for column in inspector.get_columns("finance_clients")}
        with engine.begin() as connection:
            _add_column_if_missing(connection, "finance_clients", columns, "client_email", "VARCHAR(255)")
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_clients_client_email ON finance_clients (client_email)"))

    if "finance_projects" in tables:
        columns = {column["name"] for column in inspector.get_columns("finance_projects")}
        with engine.begin() as connection:
            _add_column_if_missing(connection, "finance_projects", columns, "start_date", "DATE")
            _add_column_if_missing(connection, "finance_projects", columns, "end_date", "DATE")
            _add_column_if_missing(connection, "finance_projects", columns, "client_id", "INTEGER REFERENCES finance_clients(id) ON DELETE RESTRICT")
            _add_column_if_missing(connection, "finance_projects", columns, "project_number", "INTEGER")
            _add_column_if_missing(connection, "finance_projects", columns, "description", "TEXT")
            _add_column_if_missing(connection, "finance_projects", columns, "created_by_id", "INTEGER REFERENCES users(id)")
            _add_column_if_missing(connection, "finance_projects", columns, "project_source_team", "VARCHAR(80)")
            _add_column_if_missing(connection, "finance_projects", columns, "project_source_person_name", "VARCHAR(255)")
            _add_column_if_missing(connection, "finance_projects", columns, "client_awarded_by_name", "VARCHAR(255)")
            _add_column_if_missing(connection, "finance_projects", columns, "project_award_date", "DATE")
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_start_date ON finance_projects (start_date)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_end_date ON finance_projects (end_date)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_client_id ON finance_projects (client_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_project_number ON finance_projects (project_number)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_created_by_id ON finance_projects (created_by_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_project_source_team ON finance_projects (project_source_team)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_project_source_person_name ON finance_projects (project_source_person_name)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_projects_project_award_date ON finance_projects (project_award_date)"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_finance_project_client_number ON finance_projects (client_id, project_number) WHERE client_id IS NOT NULL AND project_number IS NOT NULL"))

    if "expense_claim_items" in tables:
        columns = {column["name"] for column in inspector.get_columns("expense_claim_items")}
        with engine.begin() as connection:
            _add_column_if_missing(connection, "expense_claim_items", columns, "payment_mode", "VARCHAR(40)")
            _add_column_if_missing(connection, "expense_claim_items", columns, "expense_date", "DATE")
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claim_items_payment_mode ON expense_claim_items (payment_mode)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_expense_claim_items_expense_date ON expense_claim_items (expense_date)"))

    if "expense_claim_attachments" in tables:
        attachment_columns = {column["name"] for column in inspector.get_columns("expense_claim_attachments")}
        if "content_sha256" not in attachment_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE expense_claim_attachments ADD COLUMN content_sha256 VARCHAR(64)"))

    # Base.metadata.create_all creates the V2 payment table and V3 settlement
    # tables before this function runs. Migrate legacy single-payment fields once.
    inspector = inspect(engine)
    if "expense_claim_payments" not in inspector.get_table_names():
        return

    with SessionLocal() as db:
        legacy_claims = list(db.scalars(
            select(ExpenseClaim).where(
                ExpenseClaim.paid_amount.is_not(None),
                ExpenseClaim.paid_amount > Decimal("0.00"),
            )
        ).all())
        changed = False
        for claim in legacy_claims:
            existing_payment = db.scalar(
                select(ExpenseClaimPayment.id).where(ExpenseClaimPayment.claim_id == claim.id).limit(1)
            )
            if existing_payment is None and claim.payment_reference:
                recorded_by_id = claim.finance_decision_by_id or claim.admin_decision_by_id or claim.requester_id
                db.add(ExpenseClaimPayment(
                    claim_id=claim.id,
                    payment_reference=claim.payment_reference,
                    payment_mode="bank_transfer",
                    amount=claim.paid_amount,
                    payment_date=(claim.paid_at or claim.finance_decision_at or claim.submitted_at or claim.created_at or utc_now()).date(),
                    recorded_by_id=recorded_by_id,
                    comments="Migrated from Finance V1 legacy payment fields.",
                ))
                changed = True

            approved = claim.finance_approved_amount or claim.total_amount
            if claim.status == "paid" and claim.paid_amount is not None and claim.paid_amount < approved:
                claim.status = "partially_paid"
                claim.paid_at = None
                changed = True
        if changed:
            db.commit()
