from __future__ import annotations

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
