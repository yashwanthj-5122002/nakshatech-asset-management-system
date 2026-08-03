from __future__ import annotations

import os
import re
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9@!._-]+$")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    software_team_email = os.getenv("SOFTWARE_TEAM_EMAIL", settings.seed_admin_email).strip().lower()
    admin_name = required_env("NEW_ADMIN_NAME")
    admin_email = required_env("NEW_ADMIN_EMAIL").lower()
    admin_password = required_env("NEW_ADMIN_PASSWORD")

    if not EMAIL_PATTERN.match(software_team_email):
        raise SystemExit("Software Team email is not valid")
    if not EMAIL_PATTERN.match(admin_email):
        raise SystemExit("New Admin email is not valid")
    if software_team_email == admin_email:
        raise SystemExit("Software Team and Admin must use different email addresses")
    if len(admin_password) < 10:
        raise SystemExit("New Admin password must contain at least 10 characters")
    if not PASSWORD_PATTERN.match(admin_password):
        raise SystemExit("New Admin password may use letters, numbers, and @ ! . _ - only")

    with SessionLocal() as db:
        software_user = db.scalar(
            select(User).where(func.lower(User.email) == software_team_email)
        )
        if not software_user:
            raise SystemExit(
                f"Existing Software Support account was not found: {software_team_email}. "
                "No database changes were made."
            )

        # Preserve the existing email and password hash. Only the role identity and display name change.
        software_user.role = "software_team"
        if software_user.full_name.strip().lower() in {
            "software support administrator",
            "software support",
            "administrator",
            "admin",
        }:
            software_user.full_name = "Software Team"
        software_user.is_active = True

        admin_user = db.scalar(select(User).where(func.lower(User.email) == admin_email))
        if admin_user and admin_user.id == software_user.id:
            raise SystemExit("The selected Admin email belongs to the Software Team account")
        if admin_user and admin_user.role not in {"admin"}:
            raise SystemExit(
                f"The email {admin_email} already belongs to role '{admin_user.role}'. "
                "No department account was overwritten."
            )

        if admin_user:
            admin_user.full_name = admin_name
            admin_user.password_hash = hash_password(admin_password)
            admin_user.role = "admin"
            admin_user.branch = admin_user.branch or "Head Office"
            admin_user.is_active = True
            admin_action = "updated"
        else:
            admin_user = User(
                email=admin_email,
                full_name=admin_name,
                password_hash=hash_password(admin_password),
                role="admin",
                branch="Head Office",
                is_active=True,
            )
            db.add(admin_user)
            admin_action = "created"

        db.commit()

        role_rows = db.execute(select(User.email, User.role, User.is_active).order_by(User.role, User.email)).all()

    print("ROLE INTEGRATION SUCCESSFUL")
    print(f"Software Team preserved: {software_team_email}")
    print("Software Team password: unchanged")
    print(f"New Admin {admin_action}: {admin_email}")
    print("Management / IT / Drone credentials: unchanged")
    print("Active login roles:")
    for email, role, is_active in role_rows:
        print(f"  - {role}: {email} ({'active' if is_active else 'inactive'})")


if __name__ == "__main__":
    main()
