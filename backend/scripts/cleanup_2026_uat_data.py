from __future__ import annotations

from pathlib import Path
import sys

# Running "python scripts/<name>.py" sets sys.path[0] to /app/scripts inside Docker.
# Add the backend project root explicitly so imports such as "app.core.database" work
# consistently both as a direct script and from local development environments.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import argparse
import json

from app.core.database import SessionLocal
from app.uat_2026 import TAG, cleanup_year_2026, existing_counts, validate_year_2026


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Delete ONLY the tagged/prefixed 2026 ERP UAT dataset.")
    p.add_argument("--confirm", metavar="TAG", help=f"Required destructive confirmation. Must equal {TAG}.")
    p.add_argument("--dry-run", action="store_true", help="Show UAT counts without deleting anything.")
    return p


def main() -> int:
    args = parser().parse_args()
    with SessionLocal() as db:
        before = existing_counts(db)
        if args.dry_run:
            print(json.dumps({"tag": TAG, "mode": "dry-run", "existing": before}, indent=2))
            return 0
        if args.confirm != TAG:
            raise SystemExit(
                f"Refusing cleanup. Re-run with --confirm {TAG}. "
                "This guard prevents accidental data deletion."
            )

        deleted = cleanup_year_2026(db)
        after = validate_year_2026(db)
        print(json.dumps({
            "tag": TAG,
            "deleted": deleted,
            "after_cleanup": after,
        }, indent=2))
        if after["projects"] != 0 or after["clients"] != 0:
            raise SystemExit("Cleanup validation failed: UAT rows still exist.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
