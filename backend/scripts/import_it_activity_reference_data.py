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
from app.modules.it_activity.import_service import import_handover_workbook, import_purchase_workbook


DATA_DIR = ROOT / "app" / "data" / "it_activity_imports"


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.role.in_(["software_team", "admin", "it"])).order_by(User.id))
        if user is None:
            raise RuntimeError("No Software Team, Admin or IT user exists for the historical import audit identity")
        jobs = [
            ("laptop", DATA_DIR / "Laptop_Handover_and_Returned.xlsx"),
            ("desktop", DATA_DIR / "Desktop_Handover_and_Returned.xlsx"),
        ]
        for category, path in jobs:
            if not path.exists():
                print(f"SKIP: {path.name} was not found")
                continue
            result = import_handover_workbook(db, path.read_bytes(), path.name, category, user)
            print(f"{path.name}: created={result['created']} skipped={result['skipped']} invalid={result['invalid']}")
        purchase = DATA_DIR / "Purchase_Details.xlsx"
        if purchase.exists():
            result = import_purchase_workbook(db, purchase.read_bytes(), purchase.name, user)
            print(f"{purchase.name}: created={result['created']} skipped={result['skipped']} invalid={result['invalid']}")
        else:
            print(f"SKIP: {purchase.name} was not found")


if __name__ == "__main__":
    main()
