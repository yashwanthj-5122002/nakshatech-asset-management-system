# NakshaTech ERP production deployment

Prepared for crm.nakshatech.com. Production activation awaits hosting administrator approval. Native cPanel deployment is an optional echo-only placeholder. GitHub Actions is the primary release mechanism.

## Architecture and hosting prerequisites

The cPanel HTTPS virtual host proxies only crm.nakshatech.com to 127.0.0.1:18090. Container Nginx routes /api/ to FastAPI and other requests to the built React SPA. PostgreSQL/PostGIS, Redis and MinIO have no published ports. The private Docker network isolates storage. Backend has outbound access for SMTP and external integrations. All six services have health checks, restart policies and rotating logs.

Administrator responsibilities include enabling approved shell access, Docker Engine and Compose v2 with --wait support, Docker permissions, disk capacity, DNS/AutoSSL, SMTP, backups and a domain-specific reverse proxy. Docker group membership grants powerful host access and requires administrator approval. The observed shell-disabled account cannot deploy. Python 3.12, PostgreSQL, Redis and MinIO run inside containers. Do not install host-wide proxy replacements or change NMaps.

## First server setup

The administrator creates /home/crmnakshatech/erp-production with private shared, incoming, releases and backups directories owned by crmnakshatech. Keep this path outside public_html and free of symlinks. Use mode 700 on private directories.

Copy .env.production.example to shared/production.env and set mode 600. Replace every REPLACE_ME with private values. Use URL-encoded database credentials in DATABASE_URL, consistent with POSTGRES_USER, POSTGRES_PASSWORD and POSTGRES_DB. Configure SMTP and a separate JWT and TOTP encryption secret. Set ISOLATION_CHECK_URL to an existing unrelated website whose availability will be checked. Review every application setting in backend/app/core/config.py. Optional invoice and AI configuration remains server-owned. Uploaded objects use MinIO. The uploads volume additionally preserves /app/uploads. Confirm any additional storage used by enabled integrations before activation.

Keep production.env outside Git, artifacts and public_html. Deployment never overwrites it. The supplied configuration disables demo seeds, UAT and password-reset provisioning in production. Initial privileged accounts must be provisioned through an administrator-reviewed account import or one-time controlled onboarding procedure. Existing startup schema compatibility routines still run. This is why each release requires APPROVED_SCHEMA_SHA. There is no runnable Alembic environment in this repository, so do not blindly execute alembic upgrade head.

## GitHub configuration and release approval

Retain the PRODUCTION environment restricted to main. Require reviewers and the regression status in branch protection. Existing environment secrets are CPANEL_HOST, CPANEL_USERNAME, CPANEL_SSH_PORT, CPANEL_SSH_KEY, CPANEL_KNOWN_HOSTS and CPANEL_DEPLOY_PATH. Set the last to /home/crmnakshatech/erp-production. Obtain known_hosts fingerprints through a trusted administrator channel, including the port-specific host entry where needed.

PRODUCTION environment variables start with PRODUCTION_DEPLOY_ENABLED=false and APPROVE_EMPTY_INSTALL=false. For each release, review schema compatibility and set APPROVED_SCHEMA_SHA to the exact main commit. Existing automatic startup migrations prevent safe unattended schema approval. Successful quality runs on main trigger build/configuration validation. Manual dispatch also requires the latest successful push quality run on the exact current main SHA. Deployments are serialized, current main is rechecked before transfer, and SSH is skipped entirely while the gate is disabled.

The release archive contains tracked backend, frontend, nginx, scripts and the production Compose file at the approved SHA. Private production configuration is excluded. Builds install locked frontend dependencies. Backend dependencies follow the existing requirements.txt. Infrastructure image upgrades and digest pinning should be reviewed by the administrator against their approved registry policy before activation.

## Reverse proxy integration

Ask the administrator to configure only the crm.nakshatech.com HTTPS virtual host to proxy to http://127.0.0.1:18090, preserving Host and forwarded client headers, handling WebSocket upgrades, allowing 100 MiB uploads and 300-second API timeouts. Preserve cPanel AutoSSL and HTTPS redirection. Container proxy configuration is nginx/production.conf. SPA fallback and immutable hashed assets are served by frontend/nginx.production.conf. API responses carry no-store. Documents remain behind existing authenticated API routes. Do not expose the MinIO console or a raw upload directory. Verify the configured isolation URL and inspect the administrator's domain configuration diff.

## Initial deployment and later releases

1. Complete infrastructure approval, configure production.env and verify shell and Docker access.
2. Verify an empty-install plan or an explicit data migration/adoption plan. The script refuses to treat existing production volumes as an empty install.
3. Review startup schema changes at the approved SHA, retain a tested backup and approve that SHA.
4. Enable PRODUCTION_DEPLOY_ENABLED=true in both the PRODUCTION environment variables and shared/production.env.
5. For an empty installation only, set APPROVE_EMPTY_INSTALL=true temporarily. Existing databases require controlled administrator adoption with a verified baseline release.
6. Merge the reviewed PR manually into main and wait for ERP quality checks to pass. Set APPROVED_SCHEMA_SHA to that main SHA and dispatch Production deployment manually if the earlier automatic run stopped for approval.
7. Reset APPROVE_EMPTY_INSTALL=false after the first successful release.
8. Review logs and run PRODUCTION_DEPLOY_ENABLED=true bash releases/SHA/scripts/verify-production.sh SHA from the production root.

Use only docker compose --project-name nakshatech_crm_production --env-file shared/production.env -f releases/SHA/docker-compose.production.yml. Export RELEASE_SHA and an absolute PRODUCTION_ENV_FILE first. Never allow the development override to load. Never delete volumes. Database, Redis AOF, MinIO objects, uploads and application backups persist in dedicated project volumes. Record the previous release and retain its images and source for rollback.

## Backups, restoration and rollback

Before each upgrade the backup script pauses backend, Redis and MinIO and snapshots the database plus object, upload and Redis volumes. It stores configuration and release metadata outside public_html in unique private backup directories. It checks pg_restore's archive inventory, gzip integrity and SHA256 manifests, then writes VERIFIED. These checks establish archive readability. Administrators must also perform a full restoration drill in isolated infrastructure before activation. Account for upgrade downtime.

Run PRODUCTION_DEPLOY_ENABLED=true bash releases/SHA/scripts/backup-production.sh SHA for a manual snapshot. Schedule this under the approved account at an agreed frequency. Retain daily backups for 30 days and monthly backups for 12 months, copy encrypted backups off-host, and prune only through a separately reviewed retention process. Scripts never delete backups automatically. Configuration backups contain secrets and require encryption and restricted access.

For restoration, disable deployments, verify SHA256SUMS, stop writers and create an isolated recovery stack. Restore database.dump using pg_restore into a new empty database, restore each tar archive into its corresponding empty recovery volume, and supply the captured private environment securely. Validate counts, logins and document downloads before an administrator-approved cutover. Never overwrite live storage during a trial restore.

Application rollback requires administrator confirmation that the current schema is compatible with the previous application. Set ROLLBACK_SCHEMA_COMPATIBLE_SHA to the previous SHA and run PRODUCTION_DEPLOY_ENABLED=true bash releases/CURRENT/scripts/rollback-production.sh. It uses retained images, preserves volumes and verifies health before recording current. A failed update can leave partly migrated schema. Stop and arrange controlled recovery when compatibility is uncertain. Database restoration is always a separate explicit operation.

## Verification and troubleshooting

Run bash scripts/validate-production.sh locally or in CI with Bash, Docker Compose, Python and PyYAML. The production workflow builds both images while disabled. Quality checks retain PostgreSQL tests, backend regression, TypeScript, frontend checks, production build, Playwright, reports and dependency audits.

Shell-disabled responses require administrator shell enablement. Docker permission errors require approved access. Missing environment files, placeholders, unsafe modes, disabled gates, insufficient disk space, unapproved schema changes and failed health checks stop deployment. Inspect docker compose logs without publishing secrets. A failed release retains data and previous release metadata. Resolve the fault and use a fresh validated main commit or a reviewed rollback.

Temporarily disable deployments by setting PRODUCTION_DEPLOY_ENABLED=false in GitHub and production.env. This does not stop the running application. To retry an unchanged failed transfer, review and quarantine the incomplete release directory manually before dispatch, since release directories are immutable.

## Local validation record

See the implementation completion report for actual commands and results. Full GitHub quality eligibility remains mandatory even when local dependencies are unavailable. Application regression corrections are owned by a separate task and must be merged and pass before production activation. No server connection, server configuration or deployment is performed by this implementation task.


## Implementation validation on 26 November 2026

The deployment worktree base was a745e1d599654085a6e72d25a0283d3f2773fce8, equal to origin/main. No separate regression corrections were present on this base. The original development worktree retained its existing three modified notification/production files.

Executed successfully

- docker compose --env-file .env.production.example -f docker-compose.production.yml config --quiet with dummy RELEASE_SHA and PRODUCTION_ENV_FILE.
- scripts/validate-production.py inside a read-only, network-disabled regression container.
- bash -n for all six production shell scripts.
- rhysd/actionlint:1.7.7 against both GitHub workflows.
- nginx -t using production.conf with local upstream host aliases.
- Backend Docker image build using the existing Dockerfile.
- Isolated pytest for test_production_startup_safety.py and test_management_authentication.py, four passed. A dependency deprecation warning was reported.
- Negative deployment preflight, which refused missing private infrastructure before any server action.
- Pinned pgsty/minio manifest lookup and curl health tooling verification. The earlier official MinIO tag lookup was denied, so the configuration reuses the pinned image already running in the local ERP.
- git diff --check and secret-file ignore checks.

Full backend regression, PostgreSQL migration/concurrency cases, Playwright, backend vulnerability audit, live deployment, backup restoration and server health have not been verified by this local task. Full GitHub quality remains mandatory. Production infrastructure approval is pending. GitHub CLI is unavailable, so the completion report supplies a PR creation link.

Frontend production image build also passed, including npm ci, TypeScript compilation and Vite production build. npm reported zero vulnerabilities. Vite reported existing large-chunk warnings.

All 17 frontend verification scripts passed in an isolated container. A host attempt lacked TypeScript dependencies and was superseded by that successful container run.
