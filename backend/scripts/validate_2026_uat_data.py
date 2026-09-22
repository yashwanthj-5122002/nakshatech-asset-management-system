from __future__ import annotations

from pathlib import Path
import sys

# Running "python scripts/<name>.py" sets sys.path[0] to /app/scripts inside Docker.
# Add the backend project root explicitly so imports such as "app.core.database" work
# consistently both as a direct script and from local development environments.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import json

from app.core.database import SessionLocal
from app.uat_2026 import TAG, validate_year_2026


def main() -> int:
    with SessionLocal() as db:
        result = validate_year_2026(db)
    print(json.dumps(result, indent=2))
    if result["projects"] == 0:
        print(f"{TAG}: no UAT project dataset is currently loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
