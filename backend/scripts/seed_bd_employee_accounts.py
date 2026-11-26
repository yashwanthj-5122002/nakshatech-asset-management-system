"""One-time script to create/reset BD01-BD05 employee test accounts.

Usage (from backend/ directory, with virtualenv activated):
    python scripts/seed_bd_employee_accounts.py

This creates bd01-bd05@nakshatech.com with password Naksha@Test2026
and role=bd_employee, matching the LiDAR/Civil demo employee convention.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.entities import User
from sqlalchemy import func, select

PASSWORD = "Naksha@Test2026"
EMAILS = [
    "bd01@nakshatech.com",
    "bd02@nakshatech.com",
    "bd03@nakshatech.com",
    "bd04@nakshatech.com",
    "bd05@nakshatech.com",
]


def main() -> None:
    # Sanity: refuse production
    if any(
        (value or "").strip().lower() in {"production", "prod", "live"}
        for value in (settings.environment, settings.app_env)
    ):
        raise SystemExit("Refusing to create test accounts in a production environment.")

    with SessionLocal() as db:
        created = 0
        updated = 0
        for email in EMAILS:
            employee_id = email.split("@", 1)[0].upper()
            user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
            if user is None:
                user = User(
                    email=email,
                    full_name=f"BD Employee {employee_id[2:]}",
                    employee_id=employee_id,
                    password_hash=hash_password(PASSWORD),
                    role="bd_employee",
                    branch="Head Office",
                    department="Business Development",
                    designation="BD Employee",
                    email_verified=True,
                    account_status="active",
                    mfa_required=False,
                    must_change_password=False,
                    is_active=True,
                    token_version=0,
                )
                db.add(user)
                created += 1
                print(f"CREATED: {email} (employee_id={employee_id})")
            else:
                user.password_hash = hash_password(PASSWORD)
                user.role = "bd_employee"
                user.employee_id = employee_id
                user.department = "Business Development"
                user.designation = "BD Employee"
                user.account_status = "active"
                user.is_active = True
                user.mfa_required = False
                user.must_change_password = False
                user.token_version = (user.token_version or 0) + 1
                updated += 1
                print(f"UPDATED: {email} (employee_id={employee_id})")
        db.commit()
        print(f"\nDone: {created} created, {updated} updated.")
        print("All BD accounts use password: Naksha@Test2026")


if __name__ == "__main__":
    main()
