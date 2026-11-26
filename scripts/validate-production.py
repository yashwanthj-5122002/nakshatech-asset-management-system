"""Offline validation of the native cPanel production deployment.

Checks configuration, workflow structure, deployment safety and the native
Python runtime. Never connects to a server and never requires Docker.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1]
problems: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        problems.append(message)


def read(relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


# --- Workflow and cPanel YAML must parse -------------------------------------
workflows = sorted((root / ".github/workflows").glob("*.yml"))
check(bool(workflows), "No GitHub workflows found")
parsed: dict[str, dict] = {}
for path in [*workflows, root / ".cpanel.yml"]:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - defensive
        problems.append(f"Invalid YAML in {path.name}: {exc}")
        continue
    check(isinstance(document, dict), f"{path.name} must contain a mapping")
    if "workflows" in str(path):
        parsed[path.name] = document

deploy = parsed.get("deploy-production.yml", {})
deploy_text = read(".github/workflows/deploy-production.yml")

# --- Deployment must not depend on Docker on the production server -----------
for name, document in parsed.items():
    jobs = document.get("jobs") or {}
    check(bool(jobs), f"{name} must define jobs")
    for job_name, job in jobs.items():
        check("runs-on" in job, f"{name}:{job_name} must declare runs-on")

for relative in ("scripts/deploy-production.sh", "scripts/backup-production.sh",
                 "scripts/verify-production.sh", "scripts/rollback-production.sh",
                 "scripts/restart-production.sh", "scripts/production-common.sh"):
    text = read(relative)
    for token in ("docker compose", "docker run", "docker build", "docker volume",
                  "docker inspect", "docker exec", "docker ps"):
        check(token not in text, f"{relative} must not use '{token}' on the production server")

for token in ("docker build", "docker compose", "docker volume"):
    check(token not in deploy_text, f"deploy-production.yml must not use '{token}' for production")

# --- Workflow safety properties ---------------------------------------------
check("environment: PRODUCTION" in deploy_text, "deploy job must use the PRODUCTION environment")
check("PRODUCTION_DEPLOY_ENABLED" in deploy_text, "PRODUCTION_DEPLOY_ENABLED gate is required")
check("vars.PRODUCTION_DEPLOY_ENABLED != 'true'" in deploy_text,
      "deployment must be skipped when the gate is disabled")
check("concurrency:" in deploy_text and "cancel-in-progress: false" in deploy_text,
      "deployments must be serialised without cancelling an in-flight release")
check("workflow_run:" in deploy_text, "deployments must follow a successful quality run")
check("conclusion == 'success'" in deploy_text, "only successful quality runs may deploy")
check("head_sha !== sha" in deploy_text, "stale quality runs must be rejected")
for secret in ("CPANEL_HOST", "CPANEL_USERNAME", "CPANEL_SSH_PORT", "CPANEL_SSH_KEY",
               "CPANEL_KNOWN_HOSTS", "CPANEL_DEPLOY_PATH"):
    check(secret in deploy_text, f"deploy workflow must use {secret}")
check("secrets." in deploy_text, "workflow must read deployment credentials from secrets")

# --- cPanel account paths ----------------------------------------------------
for relative in (".env.production.example", "scripts/production-common.sh",
                 "backend/CPANEL_BACKEND_README.txt", "frontend/CPANEL_FRONTEND_README.txt",
                 "cpanel/preflight_check.sh", "cpanel/backend.env.example",
                 "docs/PRODUCTION_DEPLOYMENT_GUIDE.md"):
    text = read(relative)
    check("/home/nakshatechws" not in text, f"{relative} still references the wrong cPanel account")
    for stale in ("/home/crmnakshatech/erp-production",):
        check(stale not in text, f"{relative} still references the retired Docker root {stale}")

common = read("scripts/production-common.sh")
check('HOME_ROOT="/home/crmnakshatech"' in common, "production home directory must be /home/crmnakshatech")
check('BACKEND_DIR="$HOME_ROOT/crm_backend"' in common, "backend must live in /home/crmnakshatech/crm_backend")
check('FRONTEND_DIR="$HOME_ROOT/public_html"' in common, "frontend must live in /home/crmnakshatech/public_html")

# --- GNU/Linux line endings --------------------------------------------------
for relative in ("scripts/deploy-production.sh", "scripts/backup-production.sh",
                 "scripts/verify-production.sh", "scripts/rollback-production.sh",
                 "scripts/restart-production.sh", "scripts/production-common.sh",
                 "scripts/validate-production.sh", "cpanel/preflight_check.sh"):
    check(b"\r" not in (root / relative).read_bytes(), f"CRLF line endings in {relative}")
for path in (root / "deploy").rglob("*"):
    if path.is_file():
        check(b"\r" not in path.read_bytes(), f"CRLF line endings in {path.relative_to(root)}")

# --- Environment template ----------------------------------------------------
template = read(".env.production.example")
template_keys = {
    line.split("=", 1)[0].strip()
    for line in template.splitlines()
    if "=" in line and not line.strip().startswith("#")
}
for key in ("PRODUCTION_DEPLOY_ENABLED", "PRODUCTION_PUBLIC_URL", "ENVIRONMENT", "API_PREFIX",
            "ROOT_PATH", "BACKEND_RUNTIME", "BACKEND_PORT", "DATABASE_URL", "JWT_SECRET",
            "TOTP_ENCRYPTION_KEY", "CORS_ORIGINS", "REDIS_URL", "MINIO_ENDPOINT",
            "MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD", "MINIO_BUCKET", "SMTP_HOST",
            "SMTP_FROM_EMAIL", "BACKUP_ROOT", "BACKUP_DATABASE_ENABLED", "SEED_DEFAULT_USERS",
            "SEED_OPERATIONS_TEST_USERS_ENABLED", "ENABLE_TEST_EMPLOYEE_SEED",
            "ENABLE_UAT_2026_CONTROLS", "LOCAL_TEST_AUTH_BYPASS"):
    check(key in template_keys, f".env.production.example is missing {key}")
for key in ("POSTGRES_PASSWORD", "PRODUCTION_HTTP_PORT"):
    check(key not in template_keys, f".env.production.example must not define container-only {key}")
for unsafe in ("SEED_DEFAULT_USERS=true", "SEED_OPERATIONS_TEST_USERS_ENABLED=true",
               "ENABLE_TEST_EMPLOYEE_SEED=true", "ENABLE_UAT_2026_CONTROLS=true",
               "LOCAL_TEST_AUTH_BYPASS=true"):
    check(unsafe not in template, f".env.production.example must not enable {unsafe.split('=')[0]}")
check("API_PREFIX=/api" in template, "native ASGI configuration must set API_PREFIX=/api")

# --- systemd unit, sudoers rule and proxy snippets ---------------------------
unit = read("deploy/systemd/nakshatech-crm.service")
check("WorkingDirectory=/home/crmnakshatech/crm_backend" in unit, "systemd unit working directory is wrong")
check("/home/crmnakshatech/crm_venv/bin/uvicorn" in unit, "systemd unit must use the dedicated virtual environment")
check("--host 127.0.0.1" in unit, "systemd unit must bind to loopback only")
check("app.batch4_main:app" in unit, "systemd unit must start the authoritative application entry point")
check("User=crmnakshatech" in unit, "systemd unit must run as the cPanel account")

sudoers = read("deploy/sudoers/nakshatech-crm-deploy")
check("NOPASSWD" in sudoers, "sudoers rule must be passwordless")
check("/usr/bin/systemctl restart nakshatech-crm.service" in sudoers, "sudoers rule must allow the restart command")
check("/usr/bin/systemctl status nakshatech-crm.service" in sudoers, "sudoers rule must allow the status command")
check("ALL=(ALL)" not in sudoers and not re.search(r"^\s*crmnakshatech\s+ALL=\(ALL", sudoers, re.M),
      "sudoers rule must not grant unrestricted sudo")
for line in sudoers.splitlines():
    if line.strip() and not line.strip().startswith("#"):
        check("systemctl" in line, f"unexpected sudoers privilege line: {line}")

apache = read("deploy/apache/crm-api-proxy.conf")
check("ProxyPass" in apache and "127.0.0.1:8010" in apache, "Apache API proxy must target the loopback backend")
nginx = read("deploy/nginx/crm-api-proxy.conf")
check("proxy_pass http://127.0.0.1:8010" in nginx, "Nginx API proxy snippet must target the loopback backend")

# --- Frontend hosting rules --------------------------------------------------
htaccess = read("frontend/public/.htaccess")
check("/api" in htaccess, "frontend .htaccess must exclude /api from the SPA fallback")
check("RewriteRule ^ index.html" in htaccess, "frontend .htaccess must keep the SPA history fallback")
check("-Indexes" in htaccess, "frontend .htaccess must disable directory listings")

# --- Python startup configuration -------------------------------------------
for relative in ("backend/app/main.py", "backend/passenger_wsgi.py",
                 "backend/cpanel_wsgi_adapter.py", "backend/scripts/cpanel_initialize.py",
                 "backend/scripts/cpanel_route_check.py", "scripts/validate-production.py"):
    try:
        compile(read(relative), relative, "exec")
    except SyntaxError as exc:
        problems.append(f"Python syntax error in {relative}: {exc}")

main = read("backend/app/main.py")
check("if not settings.is_production:" in main,
      "production startup must skip development seeders to preserve credentials")
check("initialize_application()" in main, "startup initialisation entry point is missing")

passenger = read("backend/passenger_wsgi.py")
check('os.environ["API_PREFIX"] = ""' in passenger,
      "Passenger entry point must force API_PREFIX= for the /api mount")
check('os.environ["ROOT_PATH"] = "/api"' in passenger,
      "Passenger entry point must force ROOT_PATH=/api")

# --- GitHub quality checks are preserved ------------------------------------
quality = read(".github/workflows/quality.yml")
package = json.loads(read("frontend/package.json"))
for name in re.findall(r"npm run ([\w:-]+)", quality):
    check(name in package["scripts"], f"quality workflow references unknown npm script {name}")
check("continue-on-error" not in quality, "quality checks must not be allowed to fail silently")

if problems:
    print("Production deployment validation failed:", file=sys.stderr)
    for problem in problems:
        print(f"  - {problem}", file=sys.stderr)
    raise SystemExit(1)

print("Native cPanel production validation passed")
print(f"  workflows: {', '.join(sorted(parsed))}")
print("  checks: no Docker on production, gate, concurrency, stale-SHA guard, paths,")
print("          `.env` template, LF endings, systemd, sudoers, proxies, .htaccess, Python syntax")
