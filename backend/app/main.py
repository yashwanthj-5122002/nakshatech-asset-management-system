import asyncio
import logging
from pathlib import Path
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
from app.modules.business import models as business_models  # noqa: F401
from app.modules.business.router import router as business_router
from app.modules.business.schema_compat import ensure_business_schema_compatibility
from app.modules.drone import models as drone_models  # noqa: F401
from app.modules.drone.router import router as drone_router
from app.modules.local_backup.router import router as local_backup_router
from app.modules.it_activity import models as it_activity_models  # noqa: F401
from app.modules.it_activity.router import router as it_activity_router
from app.modules.it_activity.import_service import ensure_bundled_it_activity_reference_data
from app.modules.employee_portal import models as employee_portal_models  # noqa: F401
from app.modules.employee_portal.router import router as employee_portal_router
from app.modules.data_quality.router import router as data_quality_router
from app.modules.naksha_copilot.router import router as naksha_copilot_router
from app.modules.agent_monitor.router import router as agent_monitor_router
from app.modules.notifications import models as notification_models  # noqa: F401
from app.modules.notifications.router import router as notification_router
from app.modules.finance import models as finance_models  # noqa: F401
from app.modules.finance.router import router as finance_router
from app.modules.finance.service import ensure_finance_seed_data
from app.modules.finance.schema_compat import ensure_finance_v2_schema_compatibility
from app.modules.commercial import models as commercial_models  # noqa: F401
from app.modules.commercial.router import router as commercial_router
from app.modules.commercial.schema_compat import ensure_commercial_schema_compatibility
from app.modules.travel_km import models as travel_km_models  # noqa: F401
from app.modules.travel_km.router import router as travel_km_router
from app.modules.operations import models as operations_models  # noqa: F401
from app.modules.operations.router import router as operations_router
from app.modules.employee_portal.service import ensure_default_branch
from app.modules.employee_portal.models import UserBranchAccess
from app.models.entities import User
from sqlalchemy import select
from app.services.monthly_snapshot_service import ensure_previous_month_snapshot
from app.services.seed import ensure_management_accounts, ensure_operations_test_accounts, ensure_v81_test_employee_accounts, seed_database

logger = logging.getLogger(__name__)
_initialization_lock = threading.Lock()
_initialized = False
_IT_ACTIVITY_IMPORT_LOCK = 620260805
_IT_ACTIVITY_DATA_DIR = Path(__file__).resolve().parent / "data" / "it_activity_imports"


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
            "must_change_password": "BOOLEAN DEFAULT FALSE",
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
            connection.execute(text("UPDATE users SET must_change_password = FALSE WHERE must_change_password IS NULL"))
            connection.execute(text("UPDATE users SET email_verified = TRUE WHERE email_verified IS NULL OR email_verified = FALSE"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_employee_id ON users (employee_id)"))

    inspector = inspect(engine)
    if "support_tickets" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("support_tickets")}
        additions = {
            "asset_id": "INTEGER",
            "asset_snapshot": "TEXT",
            "component": "VARCHAR(80)",
            "component_asset_tag": "VARCHAR(160)",
            "problem_code": "VARCHAR(120)",
            "problem_label": "VARCHAR(255)",
            "impact_assessment": "TEXT",
            "priority_reason": "TEXT",
            "sla_target_minutes": "INTEGER",
            "reporting_manager_email": "VARCHAR(255)",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE support_tickets ADD COLUMN {name} {sql_type}"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_asset_id ON support_tickets (asset_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_component ON support_tickets (component)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_problem_code ON support_tickets (problem_code)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_support_tickets_reporting_manager_email ON support_tickets (reporting_manager_email)"))

    inspector = inspect(engine)
    if "it_purchase_records" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("it_purchase_records")}
        with engine.begin() as connection:
            if "purchase_request_id" not in existing:
                connection.execute(text("ALTER TABLE it_purchase_records ADD COLUMN purchase_request_id INTEGER"))
            connection.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_it_purchase_records_purchase_request_id "
                "ON it_purchase_records (purchase_request_id)"
            ))

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
        asset_additions = {
            "original_asset_date": "DATE",
            "brand": "VARCHAR(160)",
            "model": "VARCHAR(180)",
            "serial_number": "VARCHAR(255)",
            "connection_type": "VARCHAR(100)",
            "capacity": "VARCHAR(80)",
            "ownership": "VARCHAR(80)",
            "client_name": "VARCHAR(255)",
            "project_id": "VARCHAR(120)",
            "current_holder": "VARCHAR(255)",
        }
        with engine.begin() as connection:
            for name, sql_type in asset_additions.items():
                if name not in asset_columns:
                    connection.execute(text(f"ALTER TABLE assets ADD COLUMN {name} {sql_type}"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_serial_number ON assets (serial_number)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_ownership ON assets (ownership)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_client_name ON assets (client_name)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_project_id ON assets (project_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_assets_current_holder ON assets (current_holder)"))
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
    if "work_records" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("work_records")}
        additions = {
            "submitted_by_user_id": "INTEGER",
            "submitted_by_name": "VARCHAR(255)",
            "submitted_by_email": "VARCHAR(255)",
            "submitted_by_role": "VARCHAR(30)",
            "submitted_at": "TIMESTAMP",
            "approved_by_user_id": "INTEGER",
            "approved_by_name": "VARCHAR(255)",
            "approved_by_email": "VARCHAR(255)",
            "approved_by_role": "VARCHAR(30)",
            "approved_at": "TIMESTAMP",
            "approval_comments": "TEXT",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE work_records ADD COLUMN {name} {sql_type}"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_work_records_submitted_by_user_id ON work_records (submitted_by_user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_work_records_approved_by_user_id ON work_records (approved_by_user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_work_records_submitted_at ON work_records (submitted_at)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_work_records_approved_at ON work_records (approved_at)"))

    inspector = inspect(engine)
    if "replacement_records" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("replacement_records")}
        additions = {
            "requested_by_user_id": "INTEGER",
            "requested_by_email": "VARCHAR(255)",
            "requested_by_role": "VARCHAR(30)",
            "approved_by_user_id": "INTEGER",
            "approved_by_email": "VARCHAR(255)",
            "approved_by_role": "VARCHAR(30)",
            "decision_remarks": "TEXT",
            "updated_at": "TIMESTAMP",
        }
        with engine.begin() as connection:
            for name, sql_type in additions.items():
                if name not in existing:
                    connection.execute(text(f"ALTER TABLE replacement_records ADD COLUMN {name} {sql_type}"))
            connection.execute(text("UPDATE replacement_records SET updated_at = created_at WHERE updated_at IS NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_replacement_records_requested_by_user_id ON replacement_records (requested_by_user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_replacement_records_approved_by_user_id ON replacement_records (approved_by_user_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_replacement_records_updated_at ON replacement_records (updated_at)"))

    # Reporting month is an effective reporting period. It is separate from
    # created_at, which remains the immutable system audit timestamp.
    reporting_month_tables = (
        "asset_history",
        "work_records",
        "component_replacements",
        "replacement_records",
        "it_handover_records",
        "it_purchase_records",
        "it_purchase_requests",
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

    # V8 project-workflow additive compatibility. Existing installations already
    # have the Ortho work-package/daily-update tables, so create_all cannot add
    # these mapped columns automatically. Keep the upgrade non-destructive.
    inspector = inspect(engine)
    if "finance_client_master_profiles" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("finance_client_master_profiles")}
        with engine.begin() as connection:
            if "organization_email" not in existing:
                connection.execute(text("ALTER TABLE finance_client_master_profiles ADD COLUMN organization_email VARCHAR(255)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_finance_client_master_profiles_organization_email ON finance_client_master_profiles (organization_email)"))

    inspector = inspect(engine)
    if "ops_v701_ortho_work_packages" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("ops_v701_ortho_work_packages")}
        with engine.begin() as connection:
            if "target_date" not in existing:
                connection.execute(text("ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN target_date DATE"))
            if "instructions" not in existing:
                connection.execute(text("ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN instructions TEXT"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_target_date ON ops_v701_ortho_work_packages (target_date)"))

    inspector = inspect(engine)
    if "ops_v709_ortho_daily_updates" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("ops_v709_ortho_daily_updates")}
        with engine.begin() as connection:
            if "files_completed" not in existing:
                connection.execute(text("ALTER TABLE ops_v709_ortho_daily_updates ADD COLUMN files_completed INTEGER DEFAULT 0"))
            if "work_type" not in existing:
                connection.execute(text("ALTER TABLE ops_v709_ortho_daily_updates ADD COLUMN work_type VARCHAR(255)"))
            connection.execute(text("UPDATE ops_v709_ortho_daily_updates SET files_completed = 0 WHERE files_completed IS NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v709_ortho_daily_updates_work_type ON ops_v709_ortho_daily_updates (work_type)"))

    inspector = inspect(engine)
    if "ops_v800_project_workflows" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("ops_v800_project_workflows")}
        with engine.begin() as connection:
            if "attachment_references" not in existing:
                connection.execute(text("ALTER TABLE ops_v800_project_workflows ADD COLUMN attachment_references TEXT"))
            if "submission_count" not in existing:
                connection.execute(text("ALTER TABLE ops_v800_project_workflows ADD COLUMN submission_count INTEGER DEFAULT 0"))
            if "finance_reviewer_id" not in existing:
                connection.execute(text("ALTER TABLE ops_v800_project_workflows ADD COLUMN finance_reviewer_id INTEGER"))
            if "finance_reviewed_at" not in existing:
                connection.execute(text("ALTER TABLE ops_v800_project_workflows ADD COLUMN finance_reviewed_at TIMESTAMP"))
            connection.execute(text("UPDATE ops_v800_project_workflows SET submission_count = 0 WHERE submission_count IS NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v800_project_workflows_finance_reviewer_id ON ops_v800_project_workflows (finance_reviewer_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v800_project_workflows_finance_reviewed_at ON ops_v800_project_workflows (finance_reviewed_at)"))

    # V8.1 rework: distinct rework work packages link back to their rework cycle / original package.
    inspector = inspect(engine)
    if "ops_v701_ortho_work_packages" in inspector.get_table_names() and "project_rework_cycles" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("ops_v701_ortho_work_packages")}
        with engine.begin() as connection:
            if "rework_cycle_id" not in existing:
                connection.execute(text("ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN rework_cycle_id INTEGER REFERENCES project_rework_cycles(id) ON DELETE SET NULL"))
            if "rework_of_package_id" not in existing:
                connection.execute(text("ALTER TABLE ops_v701_ortho_work_packages ADD COLUMN rework_of_package_id INTEGER REFERENCES ops_v701_ortho_work_packages(id) ON DELETE SET NULL"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_rework_cycle_id ON ops_v701_ortho_work_packages (rework_cycle_id)"))
            connection.execute(text("CREATE INDEX IF NOT EXISTS ix_ops_v701_ortho_work_packages_rework_of_package_id ON ops_v701_ortho_work_packages (rework_of_package_id)"))

    # V8.1 rework: remember reuse/adjust per cycle, and let a rework package carry its source Code forward as a NEW record.
    inspector = inspect(engine)
    if "project_rework_cycles" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("project_rework_cycles")}
        if "team_mode" not in existing:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE project_rework_cycles ADD COLUMN team_mode VARCHAR(20)"))
    if engine.dialect.name == "postgresql" and "ops_v701_ortho_work_packages" in inspector.get_table_names():
        with engine.begin() as connection:
            # Create the replacement indexes first so uniqueness is never unprotected, then drop the old blanket constraint.
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_ops_v701_project_package_code_orig ON ops_v701_ortho_work_packages (project_id, package_code) WHERE rework_cycle_id IS NULL"))
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_ops_v701_project_package_code_rework ON ops_v701_ortho_work_packages (project_id, package_code, rework_cycle_id) WHERE rework_cycle_id IS NOT NULL"))
            connection.execute(text("ALTER TABLE ops_v701_ortho_work_packages DROP CONSTRAINT IF EXISTS uq_ops_v701_project_package_code"))


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
        ensure_finance_v2_schema_compatibility()
        ensure_business_schema_compatibility()
        ensure_commercial_schema_compatibility()
        with SessionLocal() as db:
            if settings.seed_default_users:
                seed_database(db)
            ensure_management_accounts(db)
            ensure_operations_test_accounts(db)
            ensure_v81_test_employee_accounts(db)
            default_branch = ensure_default_branch(db)
            ensure_finance_seed_data(db)
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

            # Historical handover/return and purchase workbooks ship with the
            # application. Load them once so the six-month activity chart uses
            # real source dates instead of presenting empty historical periods.
            # SQLite is used by the isolated test suite, where this production
            # data import must remain disabled.
            if engine.dialect.name != "sqlite":
                import_lock_acquired = True
                if engine.dialect.name == "postgresql":
                    import_lock_acquired = bool(db.scalar(text(
                        f"SELECT pg_try_advisory_lock({_IT_ACTIVITY_IMPORT_LOCK})"
                    )))
                try:
                    if import_lock_acquired:
                        audit_user = db.scalar(
                            select(User)
                            .where(User.role.in_(["it", "admin", "software_team"]))
                            .order_by(User.id)
                            .limit(1)
                        )
                        if audit_user is not None:
                            import_result = ensure_bundled_it_activity_reference_data(
                                db,
                                _IT_ACTIVITY_DATA_DIR,
                                audit_user,
                            )
                            imported_files = [
                                name
                                for name, result in import_result["files"].items()
                                if result.get("status") == "imported"
                            ]
                            if imported_files:
                                logger.info(
                                    "Loaded bundled IT activity history: %s",
                                    ", ".join(imported_files),
                                )
                except Exception as exc:  # Keep unrelated application modules available.
                    db.rollback()
                    logger.warning("Bundled IT activity history could not be loaded: %s", exc)
                finally:
                    if engine.dialect.name == "postgresql" and import_lock_acquired:
                        try:
                            db.execute(text(
                                f"SELECT pg_advisory_unlock({_IT_ACTIVITY_IMPORT_LOCK})"
                            ))
                            db.commit()
                        except SQLAlchemyError as exc:
                            db.rollback()
                            logger.warning("IT activity import lock could not be released cleanly: %s", exc)

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
app.include_router(data_quality_router, prefix=settings.api_prefix)
app.include_router(naksha_copilot_router, prefix=settings.api_prefix)
app.include_router(agent_monitor_router, prefix=settings.api_prefix)
app.include_router(notification_router, prefix=settings.api_prefix)
app.include_router(business_router, prefix=settings.api_prefix)
app.include_router(finance_router, prefix=settings.api_prefix)
app.include_router(commercial_router, prefix=settings.api_prefix)
app.include_router(travel_km_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)


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
