#!/usr/bin/env python3
"""Manual PostgreSQL restore helper with explicit confirmation.

Run only during maintenance. This script never runs automatically.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy.engine import make_url  # noqa: E402
from app.core.config import settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore NakshaTech PostgreSQL custom-format dump")
    parser.add_argument("dump", type=Path)
    parser.add_argument("--confirm", required=True, help="Must be exactly RESTORE-NAKSHATECH")
    parser.add_argument("--pg-restore-bin", default="pg_restore")
    args = parser.parse_args()
    if args.confirm != "RESTORE-NAKSHATECH":
        print("Confirmation phrase is incorrect.", file=sys.stderr)
        return 2
    if not args.dump.exists():
        print(f"Dump not found: {args.dump}", file=sys.stderr)
        return 2
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        print("Restore helper currently supports PostgreSQL only.", file=sys.stderr)
        return 2
    binary = shutil.which(args.pg_restore_bin) or (args.pg_restore_bin if Path(args.pg_restore_bin).exists() else None)
    if not binary:
        print("pg_restore not found.", file=sys.stderr)
        return 2
    database_url = url.set(drivername="postgresql").render_as_string(hide_password=False)
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = str(url.password)
    command = [str(binary), "--clean", "--if-exists", "--no-owner", "--no-privileges", "--dbname", database_url, str(args.dump)]
    result = subprocess.run(command, env=environment)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
