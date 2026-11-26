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
for variable in ("PRODUCTION_FRONTEND_PATH", "PRODUCTION_BACKEND_PATH", "PRODUCTION_REPOSITORY_PATH"):
    check(variable in deploy_text, f"deploy workflow must support {variable}")
check("/home/crmnakshatech/crm_backend" in deploy_text,
      "deploy workflow must target the running backend directory /home/crmnakshatech/crm_backend")
check("/home/crmnakshatech/public_html" in deploy_text,
      "deploy workflow must target the running frontend directory /home/crmnakshatech/public_html")

# --- Transfer must be SSH + rsync only ---------------------------------------
check("rsync " in deploy_text and "-e \"$rsync_rsh\"" in deploy_text,
      "deploy workflow must upload the release with rsync over SSH")
check("scp " not in deploy_text, "deploy workflow must not use scp for the release transfer")
for token in ("ftp://", "ftps://", "sftp", "lftp", "curl -T"):
    check(token not in deploy_text.lower(), f"deploy workflow must not use FTP/FTPS ({token})")
check("release-version.json" in deploy_text,
      "deploy workflow must publish and verify the public release marker")
check("PRODUCTION_PUBLIC_URL" in deploy_text,
      "deploy workflow must verify the live release over HTTPS")
check("The latest push quality run for the exact main SHA must succeed." in deploy_text,
      "deploy workflow must keep the exact-SHA quality gate")
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
check('BACKEND_DIR="${PRODUCTION_BACKEND_PATH:-$HOME_ROOT/crm_backend}"' in common,
      "backend path must honour PRODUCTION_BACKEND_PATH with the crm_backend default")
check('REPOSITORY_DIR="${PRODUCTION_REPOSITORY_PATH:-$HOME_ROOT/repositories/nakshatech-asset-management-system}"' in common,
      "repository path must honour PRODUCTION_REPOSITORY_PATH")
check('FRONTEND_DIR="${PRODUCTION_FRONTEND_PATH:-$HOME_ROOT/public_html}"' in common,
      "frontend path must honour PRODUCTION_FRONTEND_PATH with the public_html default")
check("release-version.json" in common and '{\\"commit\\":\\"$sha\\"}' in common,
      "frontend publish must write the public release marker atomically")
check("schema_fingerprint()" in common,
      "schema changes must be detected from migrations and schema compatibility code")
check('printf \'%s\\n\' "$sha" > "$BACKEND_DIR/RELEASE_SHA"' in common,
      "the running backend must be marked with the deployed SHA")
check('printf \'%s\\n\' "$sha" > "$SHARED/frontend-sha"' in common,
      "the published frontend must be marked with the deployed SHA")
check('rsync -a --delete "$stage/assets/" "$FRONTEND_DIR/assets/"' in common,
      "only public_html/assets may be replaced with --delete")
check('"$release/frontend/" "$stage/"' in common, "frontend must be staged before publishing")
check('mv -f "$temp" "$FRONTEND_DIR/index.html"' in common, "index.html must be swapped atomically")
check(".deployment" in common, "repository checkout must record deployment metadata")

verify = read("scripts/verify-production.sh")
check("Backend directory $BACKEND_DIR is not running release" in verify,
      "verification must prove the backend directory matches the release")
check("was not published from release" in verify,
      "verification must prove the frontend directory matches the release")
check("Published $name does not match release" in verify,
      "verification must compare published frontend files with the release")

deploy = read("scripts/deploy-production.sh")
check("AUTO_ROLLBACK_ON_FAILURE" in deploy, "failed activation must support automatic rollback")
check("sync_backend \"$release\" \"$sha\"" in deploy and "sync_frontend \"$release\" \"$sha\"" in deploy,
      "both running directories must be deployed from the same release")
check("schema_fingerprint" in deploy and "APPROVED_SCHEMA_SHA is not required" in deploy,
      "schema approval must only be required when schema-sensitive files change")
check("release $previous is missing" in deploy,
      "the deploy script must refuse to guess schema changes without the previous release")

layout = read("scripts/validate-release-layout.sh")
for required in ("release-version.json", "assets", "data", "RELEASE_SHA"):
    check(required in layout, f"release layout validation must check {required}")
check("release-version.json" in verify,
      "verification must check the published release marker over HTTPS")

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
