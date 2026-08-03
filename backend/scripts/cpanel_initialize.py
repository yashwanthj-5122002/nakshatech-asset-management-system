from __future__ import annotations

import os
import sys
from pathlib import Path

# cPanel's "Execute python script" can start with a working directory that is
# not the application root. Add the backend root explicitly before importing
# the application package, and make .env resolution deterministic.
APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import func, select, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.main import initialize_application  # noqa: E402
from app.models.entities import Asset, User  # noqa: E402
from app.modules.drone.models import DroneSurveyAsset  # noqa: E402


def main() -> None:
    initialize_application()
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
        users = db.scalar(select(func.count(User.id))) or 0
        assets = db.scalar(select(func.count(Asset.id))) or 0
        drones = db.scalar(select(func.count(DroneSurveyAsset.id))) or 0

    print("NakshaTech cPanel initialization completed")
    print(f"Application root: {APP_ROOT}")
    print(f"Environment: {settings.environment}")
    print(f"Database users: {users}")
    print(f"IT assets: {assets}")
    print(f"Drone assets: {drones}")
    print("Required routes are available through the cPanel /api application mount.")


if __name__ == "__main__":
    main()
