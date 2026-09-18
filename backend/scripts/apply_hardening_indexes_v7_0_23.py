from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sqlalchemy import inspect, text

from app.core.database import SessionLocal

STATE_FILE = Path(__file__).resolve().parents[1] / ".phase9_v723_indexes.json"


def main() -> None:
    created: list[dict] = []
    with SessionLocal() as db:
        bind = db.get_bind()
        inspector = inspect(bind)
        prep = bind.dialect.identifier_preparer
        tables = inspector.get_table_names()

        def create_index(table: str, columns: tuple[str, ...]) -> None:
            available = {col["name"] for col in inspector.get_columns(table)}
            if not all(column in available for column in columns):
                return
            suffix = "_".join(columns)
            raw_name = f"idx_v723_{table}_{suffix}"
            digest = hashlib.sha1(raw_name.encode("utf-8")).hexdigest()[:8]
            name = f"{raw_name[:50]}_{digest}"
            quoted_table = prep.quote(table)
            quoted_cols = ", ".join(prep.quote(column) for column in columns)
            quoted_name = prep.quote(name)
            db.execute(text(f"CREATE INDEX IF NOT EXISTS {quoted_name} ON {quoted_table} ({quoted_cols})"))
            created.append({"table": table, "name": name, "columns": list(columns)})

        for table in tables:
            lower = table.lower()
            if lower in {"audit_events", "audit_logs"}:
                for columns in (("created_at",), ("user_id", "created_at"), ("actor_user_id", "created_at"), ("event_type", "created_at"), ("action", "created_at")):
                    create_index(table, columns)
            if "notification" in lower:
                for columns in (("created_at",), ("recipient_user_id", "created_at"), ("user_id", "created_at"), ("event_type", "created_at"), ("read_at", "created_at"), ("is_read", "created_at")):
                    create_index(table, columns)
            if lower.startswith("ops_v7"):
                for columns in (("project_id",), ("project_id", "status"), ("department_code", "status"), ("status",), ("created_at",)):
                    create_index(table, columns)
        db.commit()

    unique = {(item["table"], item["name"]): item for item in created}
    rows = sorted(unique.values(), key=lambda item: (item["table"], item["name"]))
    STATE_FILE.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"V723_OPTIMIZATION_INDEXES_APPLIED_OK: {len(rows)}")
    for item in rows:
        print(f"V723_INDEX_OK: {item['name']} -> {item['table']}({','.join(item['columns'])})")


if __name__ == "__main__":
    main()
