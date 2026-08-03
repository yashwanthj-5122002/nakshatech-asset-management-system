from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Change a NakshaTech application user password")
    parser.add_argument("email")
    args = parser.parse_args()
    password = getpass.getpass("New password: ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords do not match")
    if len(password) < 10:
        raise SystemExit("Use at least 10 characters")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(func.lower(User.email) == args.email.strip().lower()))
        if not user:
            raise SystemExit(f"User not found: {args.email}")
        user.password_hash = hash_password(password)
        db.commit()
    print(f"Password updated for {args.email}")


if __name__ == "__main__":
    main()
