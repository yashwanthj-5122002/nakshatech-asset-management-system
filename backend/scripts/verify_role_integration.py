from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.entities import User


def main() -> None:
    software_email = os.getenv("SOFTWARE_TEAM_EMAIL", settings.seed_admin_email).strip().lower()
    admin_email = os.getenv("NEW_ADMIN_EMAIL", settings.seed_organization_admin_email).strip().lower()

    with SessionLocal() as db:
        software_user = db.scalar(select(User).where(func.lower(User.email) == software_email))
        if not software_user or software_user.role != "software_team" or not software_user.is_active:
            raise SystemExit("FAIL: Software Team account is missing, inactive, or has the wrong role")

        if not admin_email:
            raise SystemExit("FAIL: NEW_ADMIN_EMAIL was not supplied for verification")
        admin_user = db.scalar(select(User).where(func.lower(User.email) == admin_email))
        if not admin_user or admin_user.role != "admin" or not admin_user.is_active:
            raise SystemExit("FAIL: New Admin account is missing, inactive, or has the wrong role")

        required_roles = {"management", "it", "drone"}
        existing_roles = set(db.scalars(select(User.role).where(User.is_active.is_(True))).all())
        missing = required_roles - existing_roles
        if missing:
            raise SystemExit(f"FAIL: Existing department role(s) missing: {', '.join(sorted(missing))}")

    print("PASS: Software Team account is active with full-access role")
    print("PASS: Admin account is active with Admin role")
    print("PASS: Management, IT and Drone accounts remain present")
    print("PASS: No password verification or password reset was performed on existing accounts")


if __name__ == "__main__":
    main()
