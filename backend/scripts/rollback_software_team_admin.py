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
    admin_email = os.getenv("NEW_ADMIN_EMAIL", "").strip().lower()
    if not admin_email:
        raise SystemExit("NEW_ADMIN_EMAIL is required")

    with SessionLocal() as db:
        software_user = db.scalar(select(User).where(func.lower(User.email) == software_email))
        if not software_user:
            raise SystemExit(f"Software Team account not found: {software_email}")
        software_user.role = "admin"
        software_user.is_active = True

        admin_user = db.scalar(select(User).where(func.lower(User.email) == admin_email))
        if admin_user and admin_user.id != software_user.id:
            # Preserve the row and any historical attribution; only disable its login.
            admin_user.is_active = False

        db.commit()

    print(f"Software Support restored to Admin: {software_email}")
    print(f"New Admin login disabled (not deleted): {admin_email}")


if __name__ == "__main__":
    main()
