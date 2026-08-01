import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.api.router import router
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.drone.router import router as drone_router
from app.modules.backup import models as backup_models  # noqa: F401
from app.modules.backup.router import router as backup_router
from app.modules.local_backup.router import router as local_backup_router
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.services.seed import seed_database
from app.services.monthly_snapshot_service import ensure_previous_month_snapshot

logger = logging.getLogger(__name__)


def ensure_schema_compatibility() -> None:
    """Add non-destructive columns required by newer releases to existing databases."""
    inspector = inspect(engine)
    if "component_replacements" not in inspector.get_table_names():
        return
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
    if "drones" in inspector.get_table_names():
        drone_columns = {column["name"] for column in inspector.get_columns("drones")}
        if "survey_asset_id" not in drone_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE drones ADD COLUMN survey_asset_id INTEGER"))


async def monthly_snapshot_watcher() -> None:
    """Close the previous month automatically within one hour of a month boundary."""
    while True:
        await asyncio.sleep(3600)
        with SessionLocal() as db:
            ensure_previous_month_snapshot(db)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine.dialect.name == "postgresql":
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        except SQLAlchemyError as exc:
            logger.warning("PostGIS extension could not be enabled: %s", exc)
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    with SessionLocal() as db:
        seed_database(db)
        ensure_previous_month_snapshot(db)
    watcher = asyncio.create_task(monthly_snapshot_watcher())
    try:
        yield
    finally:
        watcher.cancel()
        with suppress(asyncio.CancelledError):
            await watcher


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(drone_router, prefix=f"{settings.api_prefix}/drone")
app.include_router(backup_router, prefix=f"{settings.api_prefix}/backups")
app.include_router(local_backup_router, prefix=settings.api_prefix)


@app.middleware("http")
async def disable_api_caching(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(settings.api_prefix):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.get("/")
def root() -> dict:
    return {"message": settings.app_name, "docs": "/docs"}
