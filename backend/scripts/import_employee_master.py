from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database import SessionLocal  # noqa: E402
from app.modules.employee_portal.employee_master import import_workbook, inspect_workbook  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or import the NakshaTech Employee Master XLSX")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Validate only; makes zero database changes")
    mode.add_argument("--import", dest="do_import", action="store_true", help="Import transactionally and idempotently")
    parser.add_argument("--file", required=True, type=Path, help="Path to the employee-master XLSX")
    parser.add_argument("--source-batch-id", help="Optional stable source batch identifier")
    args = parser.parse_args()

    if args.dry_run:
        _records, report = inspect_workbook(args.file)
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 2 if report["duplicate_emails"] or report["duplicate_employee_numbers"] or report["duplicate_access_cards"] or report["missing_mandatory"] or report["unknown_departments"] or report["invalid_email_rows"] or report["invalid_phones"] else 0

    with SessionLocal() as db:
        try:
            result = import_workbook(db, args.file, source_batch_id=args.source_batch_id)
            db.commit()
        except Exception:
            db.rollback()
            raise
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
