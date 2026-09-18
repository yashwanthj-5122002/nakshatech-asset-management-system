from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text

from app.core.database import SessionLocal

STATE_FILE = Path(__file__).resolve().parents[1] / ".phase9_v723_indexes.json"


def main() -> None:
    if not STATE_FILE.exists():
        print("V723_ROLLBACK_INDEXES_NONE")
        return
    rows = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    with SessionLocal() as db:
        prep = db.get_bind().dialect.identifier_preparer
        for item in rows:
            name = str(item.get("name") or "")
            if not name.startswith("idx_v723_"):
                continue
            db.execute(text(f"DROP INDEX IF EXISTS {prep.quote(name)}"))
        db.commit()
    STATE_FILE.unlink(missing_ok=True)
    print("V723_ROLLBACK_INDEXES_OK")


if __name__ == "__main__":
    main()
