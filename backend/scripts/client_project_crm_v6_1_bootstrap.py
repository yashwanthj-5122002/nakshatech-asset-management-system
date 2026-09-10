from __future__ import annotations

import argparse
from pathlib import Path
from sqlalchemy import text

from app.core.database import Base, SessionLocal, engine
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.travel_km import models as travel_models  # noqa: F401
from app.modules.finance.client_master_io import import_client_master_workbook


def ensure_upgrade_columns() -> None:
    Base.metadata.create_all(bind=engine)
    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE finance_client_master_profiles ADD COLUMN IF NOT EXISTS vendor_code VARCHAR(80)",
        "ALTER TABLE finance_client_master_profiles ADD COLUMN IF NOT EXISTS client_type VARCHAR(32) DEFAULT 'client'",
        "ALTER TABLE finance_client_master_profiles ADD COLUMN IF NOT EXISTS import_source VARCHAR(255)",
        "ALTER TABLE finance_client_master_profiles ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_vendor_code ON finance_client_master_profiles (vendor_code)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_client_type ON finance_client_master_profiles (client_type)"))
        connection.execute(text("UPDATE finance_client_master_profiles SET client_type='client' WHERE client_type IS NULL OR client_type=''"))


def import_seed() -> dict:
    source = Path(__file__).resolve().parents[1] / "app" / "data" / "CLIENT_CODES_MASTER.xlsx"
    if not source.exists():
        raise SystemExit(f"Bundled client workbook missing: {source}")
    with SessionLocal() as db:
        result = import_client_master_workbook(
            db,
            raw=source.read_bytes(),
            actor=None,
            source_name="CLIENT CODES.xlsx / bundled V6.1 seed",
            overwrite_existing=False,
        )
        db.commit()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema-only", action="store_true")
    parser.add_argument("--import-only", action="store_true")
    args = parser.parse_args()
    if args.schema_only and args.import_only:
        raise SystemExit("Choose only one of --schema-only or --import-only")

    if not args.import_only:
        ensure_upgrade_columns()
        print("CLIENT_PROJECT_CRM_V6_1_SCHEMA_OK")

    if not args.schema_only:
        result = import_seed()
        print("CLIENT_PROJECT_CRM_V6_1_IMPORT_OK")
        for key in ("parsed_rows", "created", "updated", "skipped_existing", "skipped_incomplete", "issue_count"):
            print(f"{key}={result[key]}")


if __name__ == "__main__":
    main()
