import asyncio
import logging
import threading
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.modules.backup import models as backup_models  # noqa: F401
from app.modules.backup.router import router as backup_router
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.drone.router import router as drone_router
from app.modules.local_backup.router import router as local_backup_router
from app.modules.it_activity import models as it_activity_models  # noqa: F401
from app.modules.it_activity.router import router as it_activity_router
from app.modules.employee_portal import models as employee_portal_models  # noqa: F401
from app.modules.employee_portal.router import router as employee_portal_router
from app.modules.employee_portal.service import ensure_default_branch
from app.modules.employee_portal.models import UserBranchAccess
from app.models.entities import User
from sqlalchemy import select
from app.services.monthly_snapshot_service import ensure_previous_month_snapshot
from app.services.seed import seed_database

logger = logging.getLogger(__name__)
_initialization_lock = threading.Lock()
_initialized = False


def ensure_schema_compatibility() -> None:
    """Add non-destructive columns required by newer releases to existing databases."""
    inspector = inspect(engine)
    if "users" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("users")}
        additions = {
            "employee_id": "VARCHAR(80)",
            "department": "VARCHAR(120)",
            "designation": "VARCHAR(160)",
            "phone_number": "VARCHAR(40)",
            "email_verified": "BOOLEAN DEFAULT FALSE",
            "account_status": "VARCHAR(40) DEFAULT 'active'",
            "mfa_required": "BOOLEAN DEFAULT FALSE",
            "token_version": "INTEGER DEFAULT 0",
            "last_login_at": "TIMESTAMP",
            "last_logout_at": "TIMESTAMP",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sql_type}"))
            connection.execute(text("UPDATE users SET account_status = 'active' WHERE account_status IS NULL"))
            connection.execute(text("UPDATE users SET token_version = 0 WHERE token_version IS NULL"))
            connection.execute(text("UPDATE users SET mfa_required = FALSE WHERE mfa_required IS NULL"))
            connection.execute(text("UPDATE users SET email_verified = TRUE WHERE email_verified IS NULL OR email_verified = FALSE"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_employee_id ON users (employee_id)"))

    inspector = inspect(engine)
    if "component_replacements" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("component_replacements")}
        additions = {
            "change_type": "VARCHAR(40) DEFAULT 'replacement'",
            "batch_code": "VARCHAR(80)",
            "sequence_no": "INTEGER DEFAULT 1",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE component_replacements ADD COLUMN {name} {sql_type}"))

    inspector = inspect(engine)
    if "assets" in inspector.get_table_names():
        asset_columns = {column["name"] for column in inspector.get_columns("assets")}
        with engine.begin() as connection:
            if "original_asset_date" not in asset_columns:
                connection.execute(text("ALTER TABLE assets ADD COLUMN original_asset_date DATE"))
            connection.execute(text("UPDATE assets SET original_asset_date = asset_date WHERE original_asset_date IS NULL"))

    inspector = inspect(engine)
    if "asset_history" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("asset_history")}
        additions = {
            "change_type": "VARCHAR(60) DEFAULT 'asset_activity'",
            "batch_code": "VARCHAR(80)",
            "reason": "TEXT",
            "changed_by_name": "VARCHAR(255)",
            "changed_by_role": "VARCHAR(30)",
            "field_count": "INTEGER DEFAULT 0",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE asset_history ADD COLUMN {name} {sql_type}"))

    inspector = inspect(engine)
    if "component_replacements" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("component_replacements")}
        additions = {
            "performed_by_email": "VARCHAR(255)",
            "performed_by_role": "VARCHAR(30)",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE component_replacements ADD COLUMN {name} {sql_type}"))

    inspector = inspect(engine)
    if "replacement_records" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("replacement_records")}
        additions = {
            "requested_by_email": "VARCHAR(255)",
            "requested_by_role": "VARCHAR(30)",
            "approved_by_email": "VARCHAR(255)",
            "approved_by_role": "VARCHAR(30)",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE replacement_records ADD COLUMN {name} {sql_type}"))

    # Reporting month is an effective reporting period. It is separate from
    # created_at, which remains the immutable system audit timestamp.
    reporting_month_tables = (
        "asset_history",
        "work_records",
        "component_replacements",
        "replacement_records",
        "it_handover_records",
        "it_purchase_records",
    )
    for table_name in reporting_month_tables:
        inspector = inspect(engine)
        if table_name not in inspector.get_table_names():
            continue
        existing = {column["name"] for column in inspector.get_columns(table_name)}
        with engine.begin() as connection:
            if "reporting_month" not in existing:
                connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN reporting_month VARCHAR(7)"))
            # Existing tables do not receive mapped_column(index=True) indexes
            # from create_all, so create the lookup index explicitly.
            connection.execute(text(
                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_reporting_month "
                f"ON {table_name} (reporting_month)"
            ))

    inspector = inspect(engine)
    if "drones" in inspector.get_table_names():
        drone_columns = {column["name"] for column in inspector.get_columns("drones")}
        if "survey_asset_id" not in drone_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE drones ADD COLUMN survey_asset_id INTEGER"))


def initialize_application() -> None:
    """Initialize the database safely for Uvicorn and cPanel Passenger workers.

    Passenger/WSGI does not reliably execute ASGI lifespan hooks, so the cPanel
    entry point calls this function before serving requests. It is idempotent
    and guarded per process.
    """
    global _initialized
    if _initialized:
        return
    with _initialization_lock:
        if _initialized:
            return
        settings.validate_production_settings()
        if engine.dialect.name == "postgresql":
            try:
                with engine.begin() as connection:
                    connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
            except SQLAlchemyError as exc:
                # Current application tables do not require geometry columns;
                # continue when shared hosting does not permit CREATE EXTENSION.
                logger.warning("PostGIS extension could not be enabled: %s", exc)
        Base.metadata.create_all(bind=engine)
        ensure_schema_compatibility()
        with SessionLocal() as db:
            if settings.seed_default_users:
                seed_database(db)
            default_branch = ensure_default_branch(db)
            for user in db.scalars(select(User)).all():
                if not user.branch:
                    user.branch = default_branch.name
                if not user.account_status:
                    user.account_status = "active"
                existing_access = db.scalar(
                    select(UserBranchAccess.id).where(
                        UserBranchAccess.user_id == user.id,
                        UserBranchAccess.branch_id == default_branch.id,
                    )
                )
                if existing_access is None:
                    db.add(UserBranchAccess(user_id=user.id, branch_id=default_branch.id, is_default=True))
            db.commit()
            ensure_previous_month_snapshot(db)
        _initialized = True


async def monthly_snapshot_watcher() -> None:
    """Close the previous month automatically within one hour of a month boundary."""
    while True:
        await asyncio.sleep(3600)
        with SessionLocal() as db:
            ensure_previous_month_snapshot(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_application()
    watcher = None
    if settings.enable_background_watcher:
        watcher = asyncio.create_task(monthly_snapshot_watcher())
    try:
        yield
    finally:
        if watcher is not None:
            watcher.cancel()
            with suppress(asyncio.CancelledError):
                await watcher


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    root_path=settings.root_path,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
        "X-Content-SHA256",
        "X-Backup-Month",
        "X-Backup-Role",
        "X-Generated-At",
        "X-Row-Counts",
        "ETag",
    ],
)
if settings.is_production and settings.trusted_host_list and "*" not in settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

app.include_router(router, prefix=settings.api_prefix)
app.include_router(drone_router, prefix=f"{settings.api_prefix}/drone")
app.include_router(backup_router, prefix=f"{settings.api_prefix}/backups")
app.include_router(local_backup_router, prefix=settings.api_prefix)
app.include_router(it_activity_router, prefix=f"{settings.api_prefix}/it-activity")
app.include_router(employee_portal_router, prefix=settings.api_prefix)


@app.middleware("http")
async def production_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    if request.url.path.startswith(settings.api_prefix or "/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
def root() -> dict:
    return {
        "message": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "docs": f"{settings.root_path}/docs" if settings.docs_enabled else None,
    }
