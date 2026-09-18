from __future__ import annotations

import os
import smtplib
import socket
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import MetaData, Table, func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.entities import User
from app.modules.operations.service import normalize_role
from app.modules.operations.technical_routing_service import routing_status_payload

HARDENING_ROLES = {"admin", "management", "software_team"}
HARDENING_WRITE_DIAGNOSTIC_ROLES = {"admin", "software_team"}

AUDIT_TABLE_CANDIDATES = ("audit_events", "audit_logs")
NOTIFICATION_TABLE_CANDIDATES = ("global_notifications", "notifications")


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def _setting(name: str, env_name: str, default: Any = None) -> Any:
    value = getattr(settings, name, None)
    if value not in (None, ""):
        return value
    return os.getenv(env_name, default)


def _find_table(db: Session, candidates: tuple[str, ...], contains: str | None = None) -> str | None:
    inspector = inspect(db.get_bind())
    names = set(inspector.get_table_names())
    for name in candidates:
        if name in names:
            return name
    if contains:
        matches = sorted(name for name in names if contains in name.lower())
        if matches:
            return matches[0]
    return None


def _reflect(db: Session, table_name: str) -> Table:
    return Table(table_name, MetaData(), autoload_with=db.get_bind())


def _order_column(table: Table):
    for name in ("created_at", "occurred_at", "timestamp", "updated_at", "id"):
        if name in table.c:
            return table.c[name]
    return next(iter(table.c), None)


def _user_name_map(db: Session, ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.full_name, User.email).where(User.id.in_(sorted(ids)))).all()
    return {
        int(row.id): (row.full_name or row.email or f"User #{row.id}")
        for row in rows
    }


def audit_snapshot(db: Session, limit: int = 30) -> dict[str, Any]:
    table_name = _find_table(db, AUDIT_TABLE_CANDIDATES, "audit")
    if not table_name:
        return {"available": False, "table": None, "total": 0, "recent": [], "by_event": {}}
    table = _reflect(db, table_name)
    total = int(db.scalar(select(func.count()).select_from(table)) or 0)

    user_col = next((name for name in ("user_id", "actor_user_id") if name in table.c), None)
    event_col = next((name for name in ("event_type", "action", "event", "type") if name in table.c), None)
    module_col = next((name for name in ("module", "resource_type", "target_type") if name in table.c), None)
    target_type_col = next((name for name in ("target_type", "resource_type", "entity_type") if name in table.c), None)
    target_id_col = next((name for name in ("target_id", "resource_id", "entity_id") if name in table.c), None)
    created_col = next((name for name in ("created_at", "occurred_at", "timestamp") if name in table.c), None)

    safe_names = [name for name in ("id", event_col, module_col, target_type_col, target_id_col, user_col, created_col) if name]
    safe_names = list(dict.fromkeys(safe_names))
    safe_columns = [table.c[name] for name in safe_names]
    stmt = select(*safe_columns) if safe_columns else select(table.c[next(iter(table.c.keys()))])
    order = table.c[created_col] if created_col else _order_column(table)
    if order is not None:
        stmt = stmt.order_by(order.desc())
    rows = list(db.execute(stmt.limit(max(1, min(int(limit), 100)))).mappings().all())

    user_ids: set[int] = set()
    if user_col:
        for row in rows:
            value = row.get(user_col)
            if value is not None:
                try:
                    user_ids.add(int(value))
                except (TypeError, ValueError):
                    pass
    names = _user_name_map(db, user_ids)

    recent: list[dict[str, Any]] = []
    for row in rows:
        uid = row.get(user_col) if user_col else None
        actor_name = None
        if uid is not None:
            try:
                actor_name = names.get(int(uid))
            except (TypeError, ValueError):
                actor_name = None
        recent.append({
            "id": _json_value(row.get("id")),
            "event_type": _json_value(row.get(event_col)) if event_col else None,
            "module": _json_value(row.get(module_col)) if module_col else None,
            "target_type": _json_value(row.get(target_type_col)) if target_type_col else None,
            "target_id": _json_value(row.get(target_id_col)) if target_id_col else None,
            "user_id": _json_value(uid),
            "actor_name": actor_name,
            "created_at": _json_value(row.get(created_col)) if created_col else None,
        })

    by_event: dict[str, int] = {}
    if event_col:
        grouped = db.execute(
            select(table.c[event_col], func.count()).group_by(table.c[event_col]).order_by(func.count().desc()).limit(12)
        ).all()
        by_event = {str(row[0] or "unknown"): int(row[1]) for row in grouped}

    return {
        "available": True,
        "table": table_name,
        "total": total,
        "recent": recent,
        "by_event": by_event,
        "sensitive_payloads_exposed": False,
    }

def notification_snapshot(db: Session, limit: int = 30) -> dict[str, Any]:
    table_name = _find_table(db, NOTIFICATION_TABLE_CANDIDATES, "notification")
    if not table_name:
        return {"available": False, "table": None, "total": 0, "unread": 0, "recent": [], "by_event": {}}
    table = _reflect(db, table_name)
    total = int(db.scalar(select(func.count()).select_from(table)) or 0)

    recipient_col = next((name for name in ("recipient_user_id", "user_id") if name in table.c), None)
    event_col = next((name for name in ("event_type", "category", "type") if name in table.c), None)
    created_col = next((name for name in ("created_at", "sent_at", "timestamp") if name in table.c), None)
    title_col = next((name for name in ("title", "subject") if name in table.c), None)
    read_col = "read_at" if "read_at" in table.c else ("is_read" if "is_read" in table.c else None)
    target_col = "target_url" if "target_url" in table.c else None

    safe_names = [name for name in ("id", event_col, title_col, recipient_col, read_col, target_col, created_col) if name]
    safe_names = list(dict.fromkeys(safe_names))
    safe_columns = [table.c[name] for name in safe_names]
    stmt = select(*safe_columns) if safe_columns else select(table.c[next(iter(table.c.keys()))])
    order = table.c[created_col] if created_col else _order_column(table)
    if order is not None:
        stmt = stmt.order_by(order.desc())
    rows = list(db.execute(stmt.limit(max(1, min(int(limit), 100)))).mappings().all())

    user_ids: set[int] = set()
    if recipient_col:
        for row in rows:
            value = row.get(recipient_col)
            if value is not None:
                try:
                    user_ids.add(int(value))
                except (TypeError, ValueError):
                    pass
    names = _user_name_map(db, user_ids)

    unread = 0
    if "read_at" in table.c:
        unread = int(db.scalar(select(func.count()).select_from(table).where(table.c.read_at.is_(None))) or 0)
    elif "is_read" in table.c:
        unread = int(db.scalar(select(func.count()).select_from(table).where(table.c.is_read.is_(False))) or 0)

    recent: list[dict[str, Any]] = []
    for row in rows:
        uid = row.get(recipient_col) if recipient_col else None
        recipient_name = None
        if uid is not None:
            try:
                recipient_name = names.get(int(uid))
            except (TypeError, ValueError):
                recipient_name = None
        is_read = None
        if "read_at" in table.c:
            is_read = row.get("read_at") is not None
        elif "is_read" in table.c:
            is_read = bool(row.get("is_read"))
        recent.append({
            "id": _json_value(row.get("id")),
            "event_type": _json_value(row.get(event_col)) if event_col else None,
            "title": _json_value(row.get(title_col)) if title_col else None,
            "recipient_user_id": _json_value(uid),
            "recipient_name": recipient_name,
            "is_read": is_read,
            "target_url": _json_value(row.get("target_url")) if "target_url" in row else None,
            "created_at": _json_value(row.get(created_col)) if created_col else None,
        })

    by_event: dict[str, int] = {}
    if event_col:
        grouped = db.execute(
            select(table.c[event_col], func.count()).group_by(table.c[event_col]).order_by(func.count().desc()).limit(12)
        ).all()
        by_event = {str(row[0] or "unknown"): int(row[1]) for row in grouped}

    return {
        "available": True,
        "table": table_name,
        "total": total,
        "unread": unread,
        "recent": recent,
        "by_event": by_event,
        "message_bodies_exposed": False,
    }


def database_health(db: Session) -> dict[str, Any]:
    try:
        value = db.execute(text("SELECT 1")).scalar_one()
        dialect = db.get_bind().dialect.name
        return {"ok": value == 1, "dialect": dialect, "detail": "Database query succeeded"}
    except Exception as exc:
        return {"ok": False, "dialect": None, "detail": f"Database health check failed: {type(exc).__name__}"}


def redis_health() -> dict[str, Any]:
    url = _setting("redis_url", "REDIS_URL")
    if not url:
        return {"configured": False, "ok": False, "detail": "Redis URL is not configured"}
    try:
        import redis
        client = redis.Redis.from_url(str(url), socket_connect_timeout=2, socket_timeout=2)
        ok = bool(client.ping())
        return {"configured": True, "ok": ok, "detail": "Redis PING succeeded" if ok else "Redis PING failed"}
    except Exception as exc:
        return {"configured": True, "ok": False, "detail": f"Redis check failed: {type(exc).__name__}"}


def _endpoint_host_port(value: str, default_port: int) -> tuple[str, int]:
    raw = value.strip()
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or raw.split(":", 1)[0]
    port = parsed.port or default_port
    return host, int(port)


def minio_health() -> dict[str, Any]:
    endpoint = str(_setting("minio_endpoint", "MINIO_ENDPOINT", "") or "").strip()
    if not endpoint:
        return {"configured": False, "ok": False, "detail": "MinIO endpoint is not configured"}
    try:
        host, port = _endpoint_host_port(endpoint, 9000)
        with socket.create_connection((host, port), timeout=2):
            pass
        return {"configured": True, "ok": True, "detail": f"MinIO endpoint reachable on {host}:{port}"}
    except Exception as exc:
        return {"configured": True, "ok": False, "detail": f"MinIO endpoint check failed: {type(exc).__name__}"}


def smtp_configuration() -> dict[str, Any]:
    host = str(_setting("smtp_host", "SMTP_HOST", "") or "").strip()
    port_raw = _setting("smtp_port", "SMTP_PORT", 587)
    username = str(_setting("smtp_username", "SMTP_USERNAME", "") or "").strip()
    password = str(_setting("smtp_password", "SMTP_PASSWORD", "") or "")
    try:
        port = int(port_raw or 587)
    except (TypeError, ValueError):
        port = 587
    return {
        "configured": bool(host and username and password),
        "host": host or None,
        "port": port,
        "username": username or None,
        "password_present": bool(password),
    }


def smtp_auth_probe() -> dict[str, Any]:
    cfg = smtp_configuration()
    if not cfg["configured"]:
        return {**cfg, "ok": False, "detail": "SMTP is not fully configured"}
    password = str(_setting("smtp_password", "SMTP_PASSWORD", "") or "")
    smtp = None
    try:
        if int(cfg["port"]) == 465:
            smtp = smtplib.SMTP_SSL(str(cfg["host"]), int(cfg["port"]), timeout=15)
        else:
            smtp = smtplib.SMTP(str(cfg["host"]), int(cfg["port"]), timeout=15)
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
        smtp.login(str(cfg["username"]), password)
        return {**cfg, "ok": True, "detail": "SMTP authentication succeeded; no email was sent"}
    except smtplib.SMTPAuthenticationError as exc:
        return {**cfg, "ok": False, "detail": f"SMTP authentication rejected ({exc.smtp_code})"}
    except Exception as exc:
        return {**cfg, "ok": False, "detail": f"SMTP probe failed: {type(exc).__name__}"}
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass


def _security_secret_state() -> dict[str, Any]:
    candidates = [
        ("jwt_secret", "JWT_SECRET"),
        ("jwt_secret_key", "JWT_SECRET_KEY"),
        ("secret_key", "SECRET_KEY"),
        ("app_secret_key", "APP_SECRET_KEY"),
    ]
    value = ""
    source = None
    for setting_name, env_name in candidates:
        item = _setting(setting_name, env_name, "")
        if item:
            value = str(item)
            source = env_name
            break
    lowered = value.strip().lower()
    known_defaults = {"secret", "changeme", "change-me", "development", "dev-secret", "your-secret-key"}
    weak = bool(value) and (len(value) < 24 or lowered in known_defaults)
    return {
        "configured": bool(value),
        "source": source,
        "length": len(value) if value else 0,
        "weak_default_or_short": weak,
    }


def optimization_index_snapshot(db: Session) -> dict[str, Any]:
    inspector = inspect(db.get_bind())
    rows: list[dict[str, Any]] = []
    for table in inspector.get_table_names():
        for idx in inspector.get_indexes(table):
            name = str(idx.get("name") or "")
            if name.startswith("idx_v723_"):
                rows.append({"table": table, "name": name, "columns": idx.get("column_names") or []})
    rows.sort(key=lambda item: (item["table"], item["name"]))
    return {"count": len(rows), "indexes": rows}


def _backup_capability() -> dict[str, Any]:
    script_root = Path("/app/scripts")
    candidates = sorted(path.name for path in script_root.glob("*backup*") if path.is_file()) if script_root.exists() else []
    return {
        "scripts_detected": len(candidates),
        "script_names": candidates[:12],
        "detail": "Backup-related backend scripts detected" if candidates else "No backup-named backend script detected inside /app/scripts",
    }


def hardening_overview_payload(db: Session, *, actor: User, effective_role: str) -> dict[str, Any]:
    role = normalize_role(effective_role)
    database = database_health(db)
    redis = redis_health()
    minio = minio_health()
    smtp = smtp_configuration()
    audit = audit_snapshot(db, 12)
    notifications = notification_snapshot(db, 12)
    routing = routing_status_payload(db)
    security = _security_secret_state()
    indexes = optimization_index_snapshot(db)
    backup = _backup_capability()
    reporting_source_present = Path("/app/app/modules/operations/reporting_service.py").exists()

    checks: list[dict[str, Any]] = []

    def add(key: str, label: str, passed: bool, detail: str, *, critical: bool = False, warn_only: bool = False) -> None:
        status = "pass" if passed else ("warn" if warn_only else "fail")
        checks.append({"key": key, "label": label, "status": status, "critical": critical, "detail": detail})

    add("database", "Database connectivity", bool(database["ok"]), str(database["detail"]), critical=True)
    add("audit", "Audit trail available", bool(audit["available"]), f"{audit['total']} audit events visible" if audit["available"] else "Audit table not detected", critical=True)
    add("notifications", "Notification store available", bool(notifications["available"]), f"{notifications['total']} notifications visible" if notifications["available"] else "Notification table not detected", critical=True)
    add("reporting", "Phase 8 reporting source", reporting_source_present, "Phase 8 reporting module present" if reporting_source_present else "Phase 8 reporting module missing", critical=True)
    add("secret", "Application/JWT secret strength", bool(security["configured"]) and not bool(security["weak_default_or_short"]), "Secret is configured with acceptable length" if security["configured"] and not security["weak_default_or_short"] else "Secret is missing, short or looks like a development default", critical=True)
    add("smtp", "SMTP configuration", bool(smtp["configured"]), "SMTP credentials configured; use the explicit auth probe to verify" if smtp["configured"] else "SMTP configuration is incomplete", warn_only=True)
    add("redis", "Redis runtime", bool(redis["ok"]), str(redis["detail"]), warn_only=True)
    add("minio", "MinIO runtime", bool(minio["ok"]), str(minio["detail"]), warn_only=True)
    add("routing", "Phase 7 routing control", routing.get("routing_mode") in {"uat_demo_locked", "production_live"}, f"Routing mode: {routing.get('routing_mode')}", critical=True)
    add("optimization", "Phase 9 reporting/audit indexes", indexes["count"] > 0, f"{indexes['count']} Phase 9 indexes active", warn_only=True)
    add("backup", "Backup tooling visibility", backup["scripts_detected"] > 0, str(backup["detail"]), warn_only=True)

    pass_count = sum(1 for item in checks if item["status"] == "pass")
    fail_count = sum(1 for item in checks if item["status"] == "fail")
    warn_count = sum(1 for item in checks if item["status"] == "warn")
    critical_failures = [item for item in checks if item["critical"] and item["status"] == "fail"]
    score = round((pass_count / len(checks)) * 100) if checks else 0

    return {
        "viewer_role": role,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "phase": "V7.0.23 Phase 9",
        "read_only": True,
        "production_review_ready": len(critical_failures) == 0,
        "readiness_score": score,
        "summary": {
            "checks": len(checks),
            "passed": pass_count,
            "warnings": warn_count,
            "failed": fail_count,
            "critical_failures": len(critical_failures),
            "audit_events": int(audit["total"]),
            "notifications": int(notifications["total"]),
            "unread_notifications": int(notifications.get("unread", 0)),
            "optimization_indexes": int(indexes["count"]),
        },
        "checks": checks,
        "services": {"database": database, "redis": redis, "minio": minio, "smtp": smtp},
        "security": security,
        "routing": routing,
        "audit": audit,
        "notifications": notifications,
        "optimization": indexes,
        "backup": backup,
        "go_live_note": "Phase 9 does not activate Phase 7 production routing. Routing cutover remains a separate explicit Admin action.",
    }
