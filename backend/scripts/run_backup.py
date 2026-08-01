#!/usr/bin/env python3
"""Create NakshaTech Excel/database backups without requiring the web UI.

Designed for cPanel Cron Jobs, Linux cron, Windows Task Scheduler, or manual use.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.modules.backup import models as backup_models  # noqa: F401,E402
from app.modules.backup.service import create_backup, run_scheduled_backups  # noqa: E402
from app.modules.drone import models as drone_models  # noqa: F401,E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NakshaTech backup runner")
    parser.add_argument("--scheduled", action="store_true", help="Run the daily schedule and month/year boundary backups")
    parser.add_argument("--type", choices=["daily", "monthly", "current_month", "yearly", "financial_year", "full"], default="daily")
    parser.add_argument("--period", help="YYYY-MM-DD, YYYY-MM, YYYY, or YYYY-YY depending on backup type")
    parser.add_argument("--scope", choices=["all", "it", "drone"], default="all")
    parser.add_argument("--without-database", action="store_true")
    parser.add_argument("--include-minio", action="store_true")
    parser.add_argument("--created-by", default="Server scheduled backup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            if args.scheduled:
                runs = run_scheduled_backups(db, args.created_by)
            else:
                runs = [
                    create_backup(
                        db,
                        args.type,
                        args.scope,
                        args.period,
                        args.created_by,
                        include_database=not args.without_database,
                        include_minio=args.include_minio,
                        include_admin_data=args.scope == "all",
                    )
                ]
            # SQLAlchemy expires ORM attributes after commit. Capture printable values
            # before the session closes so cron jobs never report a false failure.
            results = [
                {
                    "backup_code": run.backup_code,
                    "status": run.status,
                    "excel_filename": run.excel_filename,
                    "message": run.message,
                }
                for run in runs
            ]
        for result in results:
            print(f"{result['backup_code']}: {result['status']}: {result['excel_filename'] or '-'}")
            if result["message"]:
                print(result["message"])
        return 0 if all(result["status"] != "failed" for result in results) else 1
    except Exception as exc:
        print(f"BACKUP FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
