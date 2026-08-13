from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
from app.models.entities import User
from app.modules.drone import models as _drone_models  # noqa: F401
from app.modules.backup import models as _backup_models  # noqa: F401
from app.modules.it_activity import models as _models  # noqa: F401
from app.modules.it_activity.import_service import ensure_bundled_it_activity_reference_data


DATA_DIR = ROOT / "app" / "data" / "it_activity_imports"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(
            select(User)
            .where(User.role.in_(["software_team", "admin", "it"]))
            .order_by(User.id)
            .limit(1)
        )
        if user is None:
            raise RuntimeError("No Software Team, Admin or IT user exists for the historical import audit identity")

        result = ensure_bundled_it_activity_reference_data(db, DATA_DIR, user)
        backfill = result["backfill"]
        print(
            "Reporting-month backfill: "
            f"handovers={backfill['handovers_updated']} "
            f"purchases={backfill['purchases_updated']}"
        )
        for filename, file_result in result["files"].items():
            status = file_result["status"]
            if status == "imported":
                print(
                    f"{filename}: created={file_result['created']} "
                    f"skipped={file_result['skipped']} invalid={file_result['invalid']}"
                )
            else:
                print(f"{filename}: {status}")


if __name__ == "__main__":
    main()
