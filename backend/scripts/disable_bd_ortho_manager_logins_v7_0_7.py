from __future__ import annotations

from pathlib import Path
import sys

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models.entities import User  # noqa: E402


MANAGED_IDS = {
    "TEST-BD-MGR",
    "TEST-ORTHO-PM",
    "TEST-EMPLOYEE-001",
    "TEST-BD-EMP",
    "TEST-ORTHO-TL",
    "TEST-ORTHO-PROD",
    "TEST-ORTHO-QC",
    "TEST-ORTHO-QA",
}


def main() -> None:
    with SessionLocal() as db:
        users = db.scalars(select(User).where(User.employee_id.in_(MANAGED_IDS))).all()
        for user in users:
            user.is_active = False
            user.account_status = "disabled_test_seed_rollback"
            user.mfa_required = False
            user.must_change_password = False
            user.token_version = (user.token_version or 0) + 1
        db.commit()
    print(f"V707_TEST_ACCOUNTS_DISABLED: {len(users)}")


if __name__ == "__main__":
    main()
