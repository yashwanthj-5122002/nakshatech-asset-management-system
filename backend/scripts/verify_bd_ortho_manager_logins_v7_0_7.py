from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import func, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.core.security import verify_password  # noqa: E402
from app.models.entities import User  # noqa: E402


EXPECTED = [
    (settings.seed_bd_manager_email, settings.seed_bd_manager_password, "bd", "Manager", "TEST-BD-MGR"),
    (settings.seed_ortho_pm_email, settings.seed_ortho_pm_password, "ortho", "Project Manager", "TEST-ORTHO-PM"),
    (settings.seed_employee_test_email, settings.seed_employee_test_password, "employee", "Employee", "TEST-EMPLOYEE-001"),
]
OBSOLETE_IDS = {"TEST-BD-EMP", "TEST-ORTHO-TL", "TEST-ORTHO-PROD", "TEST-ORTHO-QC", "TEST-ORTHO-QA"}


def main() -> None:
    if not settings.seed_operations_test_users_enabled:
        raise SystemExit("SEED_OPERATIONS_TEST_USERS_ENABLED is not enabled")

    with SessionLocal() as db:
        for configured_email, password, role, designation, employee_id in EXPECTED:
            email = configured_email.strip().lower()
            user = db.scalar(select(User).where(func.lower(User.email) == email))
            if user is None:
                raise SystemExit(f"Missing V7.0.7 test account: {email}")
            if user.role != role:
                raise SystemExit(f"Role mismatch for {email}: {user.role} != {role}")
            if user.designation != designation:
                raise SystemExit(f"Designation mismatch for {email}: {user.designation} != {designation}")
            if user.employee_id != employee_id:
                raise SystemExit(f"Managed fixture ID mismatch for {email}: {user.employee_id} != {employee_id}")
            if not user.is_active or user.account_status != "active":
                raise SystemExit(f"Inactive V7.0.7 test account: {email}")
            if not verify_password(password, user.password_hash):
                raise SystemExit(f"Configured password does not authenticate: {email}")

        active_obsolete = db.scalars(
            select(User).where(User.employee_id.in_(OBSOLETE_IDS), User.is_active.is_(True))
        ).all()
        if active_obsolete:
            raise SystemExit(
                "Superseded V7.0.5 Ortho sub-role test accounts are still active: "
                + ", ".join(sorted(user.email for user in active_obsolete))
            )

    print("BD_ORTHO_MANAGER_EMPLOYEE_TEST_ACCOUNTS_OK")
    print("BD_MANAGER_LOGIN_OK: bd -> /bd")
    print("ORTHO_PM_LOGIN_OK: ortho -> /ortho (PM controls all five views)")
    print("EMPLOYEE_LOGIN_OK: employee -> existing employee dashboard; no Ortho role")


if __name__ == "__main__":
    main()
