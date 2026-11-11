import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from app.main import app as _app  # noqa: F401 - register the complete ORM schema for isolated fixtures

from app.modules.operations.production_schema_compat import SCHEMA_VERSION, ensure_production_tracking_schema_compatibility


def legacy_schema(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE ops_v701_ortho_work_packages (id INTEGER PRIMARY KEY, current_stage VARCHAR(30))"))
        connection.execute(text("CREATE TABLE work_package_items (id INTEGER PRIMARY KEY, work_package_id INTEGER, project_id INTEGER, item_number VARCHAR(120), status VARCHAR(40), is_active BOOLEAN, created_at TIMESTAMP, production_user_id INTEGER, qc_user_id INTEGER, qa_user_id INTEGER)"))
        connection.execute(text("CREATE TABLE work_package_item_activities (id INTEGER PRIMARY KEY, project_id INTEGER, work_package_id INTEGER, work_package_item_id INTEGER, stage VARCHAR(20), employee_user_id INTEGER, status VARCHAR(40), started_at TIMESTAMP, ended_at TIMESTAMP, created_at TIMESTAMP)"))
        connection.execute(text("INSERT INTO work_package_items (id, item_number, status) VALUES (1, 'HISTORICAL', 'not_started')"))


@pytest.fixture(params=["sqlite", "postgresql"])
def migration_database(request):
    if request.param == "sqlite":
        engine = create_engine("sqlite://")
        try:
            yield engine
        finally:
            engine.dispose()
        return
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is required for PostgreSQL upgrade verification")
    schema = f"production_test_{uuid.uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_old_schema_upgrades_idempotently_and_preserves_records(migration_database):
    engine = migration_database
    legacy_schema(engine)
    ensure_production_tracking_schema_compatibility(engine)
    ensure_production_tracking_schema_compatibility(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT item_number FROM work_package_items WHERE id=1")).scalar_one() == "HISTORICAL"
        assert connection.execute(text("SELECT COUNT(*) FROM ops_schema_versions WHERE version=:version"), {"version": SCHEMA_VERSION}).scalar_one() == 1
    columns = {row["name"] for row in inspect(engine).get_columns("work_package_items")}
    assert {"planned_quantity", "planned_unit", "production_target_date"} <= columns
    assert any(index["name"] == "uq_work_package_item_activities_open" and index["unique"]
               for index in inspect(engine).get_indexes("work_package_item_activities"))


def test_upgrade_refuses_conflicting_open_sessions_without_deleting_history(migration_database):
    engine = migration_database
    legacy_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO work_package_item_activities (id, work_package_item_id, stage) VALUES (1, 1, 'production'), (2, 1, 'production')"))
    with pytest.raises(RuntimeError, match="duplicate open activity"):
        ensure_production_tracking_schema_compatibility(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM work_package_item_activities")).scalar_one() == 2


def test_upgrade_detects_wrong_existing_column_type(migration_database):
    engine = migration_database
    legacy_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE work_package_items ADD COLUMN planned_quantity VARCHAR(40)"))
    with pytest.raises(RuntimeError, match="Incompatible production schema"):
        ensure_production_tracking_schema_compatibility(engine)


def test_upgrade_widens_distance_precision_without_changing_old_quantities(migration_database):
    engine = migration_database
    legacy_schema(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE work_package_item_activities ADD COLUMN quantity_completed NUMERIC(14, 3)"))
        connection.execute(text("INSERT INTO work_package_item_activities (id, work_package_item_id, stage, quantity_completed, ended_at) VALUES (1, 1, 'production', 1.234, CURRENT_TIMESTAMP)"))
    ensure_production_tracking_schema_compatibility(engine)
    with engine.connect() as connection:
        assert float(connection.execute(text("SELECT quantity_completed FROM work_package_item_activities WHERE id=1")).scalar_one()) == 1.234
    if engine.dialect.name == "postgresql":
        column = next(column for column in inspect(engine).get_columns("work_package_item_activities")
                      if column["name"] == "quantity_completed")
        assert column["type"].precision == 20 and column["type"].scale == 9


@pytest.mark.parametrize("operation", ["start", "stop"])
def test_concurrent_session_requests_have_one_winner(migration_database, operation):
    if migration_database.dialect.name != "postgresql":
        pytest.skip("Real row-lock concurrency requires PostgreSQL")
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session
    from app.core.database import Base
    from app.models.entities import User
    from app.modules.operations import production_items as items
    from app.modules.operations.models import WorkPackageItemActivity
    from test_production_master_excel_allocation_v8_3 import (
        MASTER_HEADERS, assign_all, import_master, items_of, packages_of, setup_project, xlsx_bytes,
    )
    engine = migration_database
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        ctx = setup_project(db, "CONCURRENT")
        import_master(db, ctx, xlsx_bytes(MASTER_HEADERS, [["LOT", "CODE", "AREA", "F1", 3, "km", ""]]))
        package = packages_of(db, ctx)[0]
        item = items_of(db, ctx)[0]
        assign_all(db, ctx, package, [item.id])
        user_id, item_id = ctx["team"]["prod"].id, item.id
        activity_id = None
        if operation == "stop":
            activity_id = items.start_activity(db, actor=ctx["team"]["prod"], role="employee",
                                               work_package_item_id=item_id, stage="production").id
        db.commit()
    barrier = Barrier(2)

    def request():
        with Session(engine) as db:
            actor = db.get(User, user_id)
            barrier.wait(timeout=10)
            try:
                if operation == "start":
                    items.start_activity(db, actor=actor, role="employee", work_package_item_id=item_id, stage="production")
                else:
                    items.stop_activity(db, actor=actor, activity_id=activity_id, status="completed")
                db.commit()
                return "saved"
            except ValueError as exc:
                db.rollback()
                assert "open" in str(exc) or "already completed" in str(exc)
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(request) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == ["conflict", "saved"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(WorkPackageItemActivity)) == 1
