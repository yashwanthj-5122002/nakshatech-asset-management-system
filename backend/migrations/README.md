# Database migrations

This directory contains reviewed SQL upgrades. `alembic.ini` is a legacy stub;
there is no Alembic revision chain. Do not run `alembic upgrade head`.

The production compatibility helper performs additive upgrades on startup under
a PostgreSQL advisory transaction lock. It validates known column types and
records successful upgrades in `ops_schema_versions`. It never deletes duplicate
sessions or rewrites activity history automatically.

For `20261111_production_integrity.sql`, first apply the earlier V8.2/V8.4
production migrations on an older installation. Take the normal database backup,
stop application workers, and apply the SQL using the normal deployment database
connection with `psql -v ON_ERROR_STOP=1 -f migrations/20261111_production_integrity.sql`.
Restart workers after success. Duplicate open sessions block the upgrade and must
be reviewed and closed through the operational correction process first.

The upgrade widens activity quantities from `NUMERIC(14,3)` to `NUMERIC(20,9)`
without reducing the integer range, and allows one open session per file/stage.
Historical quantities remain unchanged; read models attribute the planned output
once across partial sessions and rework. Do not narrow the numeric column during
a code rollback: doing so could lose newly recorded fractional precision.

Run isolated PostgreSQL upgrade and concurrency checks from the repository root:

```powershell
docker compose -f docker-compose.qa.yml up -d --wait
$env:TEST_POSTGRES_URL = 'postgresql+psycopg://qa:qa-local-tests-only@127.0.0.1:38112/qa'
backend/.venv/Scripts/python.exe -m pytest backend/tests/test_production_schema_upgrade.py -q
docker compose -f docker-compose.qa.yml down
```

The QA container uses a temporary filesystem and a separate localhost port. Each
PostgreSQL test creates and removes its own schema. It never uses the ERP's normal
database URL. CI sets `TEST_POSTGRES_URL` and runs these checks automatically.
