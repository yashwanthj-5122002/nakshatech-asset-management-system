from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# JWT secrets that are literally published in this repository (source, example
# env files, git history). None of them may ever sign a token: whoever reads the
# repository can sign for admin@nakshatech.com. Kept lowercase for comparison.
_PUBLICLY_KNOWN_SECRETS = frozenset(
    {
        "change-this-secret-before-production",
        "change-this-secret-before-production-with-at-least-32-characters",
        "replace-with-a-long-random-production-secret",
        "<generate-secure-secret>",
        "secret",
        "password",
    }
)

# Prefixes that only ever appear in an unedited template. Accepted in
# development so a fresh checkout boots, rejected in production.
_TEMPLATE_PREFIXES = ("replace-", "<set-in-local-env>", "<change-me>", "<generate-")


def _is_unedited_template(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or lowered.startswith(_TEMPLATE_PREFIXES)


class Settings(BaseSettings):
    app_name: str = "NakshaTech Asset Management System"
    app_version: str = "1.0.0"
    environment: str = "development"
    app_env: str = ""

    # Local Docker serves the API under /api. For cPanel Passenger, the app is
    # mounted externally at /api, so API_PREFIX is intentionally set to an
    # empty string in the cPanel environment.
    api_prefix: str = "/api"
    root_path: str = ""
    # Interactive API documentation and the OpenAPI schema. Off by default: /docs and
    # /openapi.json publish the complete route map to anonymous callers. Opt in
    # explicitly for local development, and never in production.
    docs_enabled: bool = False
    enable_background_watcher: bool = True
    seed_default_users: bool = True

    # Brute-force protection for the credential surfaces (login, MFA, OTP and
    # password reset). Two independent windows are enforced: a fast one for
    # total request volume so a single host cannot flood the endpoints, and a
    # slower one for repeated failures so legitimate users on shared NAT are
    # not locked out by their own traffic. Set RATE_LIMIT_ENABLED=false only
    # where a fronting proxy already enforces its own limiter.
    rate_limit_enabled: bool = True
    rate_limit_auth_per_minute: int = 60
    rate_limit_auth_failures_per_minute: int = 10
    # Comma-separated CIDRs (or IPs) whose X-Real-IP header may be trusted when
    # resolving the client address. Defaults to the private/loopback ranges so
    # that traffic arriving through the bundled nginx or a cPanel proxy is
    # attributed to the real client instead of collapsing into one global
    # bucket. Set to a single CIDR (or empty) on hosts where the API port is
    # reachable directly from an untrusted network: only then can a caller
    # spoof X-Real-IP to work around the limiter.
    trusted_proxy_cidrs: str = "127.0.0.0/8,::1/128,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7"

    # Privileged department accounts are provisioned by NakshaTech and are not
    # available through public employee registration. Temporary first-login
    # passwords are stored only in protected environment configuration.
    #
    # These default to empty on purpose. A published default password is a
    # public credential: the previous ChangeMe* values shipped in source, in
    # docker-compose.yml and in git history, and an account created from one
    # logs in without MFA. Empty means "not configured" - seeding skips the
    # account entirely instead of creating one everyone can log into.
    seed_admin_email: str = "admin@nakshatech.com"
    seed_admin_password: str = ""
    seed_software_team_email: str = "software.team@nakshatech.com"
    seed_software_team_password: str = ""
    # Optional additional organization Admin retained for backward compatibility.
    seed_organization_admin_name: str = "NakshaTech Administrator"
    seed_organization_admin_email: str = ""
    seed_organization_admin_password: str = ""
    # Management access is restricted to the two authoritative accounts in
    # app.core.management_access. These settings contain only their temporary
    # first-login passwords; permanent passwords are stored as database hashes.
    seed_management_email: str = "vinod@nakshatech.com"
    seed_management_password: str = ""
    seed_management_secondary_email: str = "chethan@nakshatech.com"
    seed_management_secondary_password: str = ""
    seed_it_email: str = "it-support@nakshatech.com"
    seed_it_password: str = ""
    seed_finance_password: str = ""
    seed_hr_password: str = ""
    seed_drone_email: str = "drone@nakshatech.com"
    seed_drone_password: str = ""

    # Local/UAT-only V7.0.7 workflow test logins. These accounts use the
    # existing unified authentication system; clear-text credentials come
    # from protected environment configuration and are hashed in PostgreSQL.
    # Normal employees remain employee-role users and never gain /ortho access.
    seed_operations_test_users_enabled: bool = False
    seed_bd_manager_email: str = ""
    seed_bd_manager_password: str = ""
    seed_ortho_pm_email: str = ""
    seed_ortho_pm_password: str = ""
    seed_employee_test_email: str = ""
    seed_employee_test_password: str = ""

    # Multi-department generalization of the Ortho PM login above: one PM/UAT
    # account per additional technical department, same unified authentication,
    # same opt-in gate (seed_operations_test_users_enabled), password never logged.
    seed_lidar_pm_email: str = ""
    seed_lidar_pm_password: str = ""
    seed_mobile_mapping_pm_email: str = ""
    seed_mobile_mapping_pm_password: str = ""
    seed_laser_scanning_pm_email: str = ""
    seed_laser_scanning_pm_password: str = ""
    seed_civil_pm_email: str = ""
    seed_civil_pm_password: str = ""

    # V8.1 local/test-only normal Employee fixtures. The seed function also
    # refuses to run whenever APP_ENV or ENVIRONMENT identifies production.
    enable_test_employee_seed: bool = False
    test_employee_seed_password: str = ""
    # Shared password for the 60 LiDAR/Mobile Mapping/Laser Scanning/Civil test employees
    # (15 each), gated by the same enable_test_employee_seed flag as the Ortho 15.
    multi_department_test_employee_seed_password: str = ""

    # Local/UAT-only control panel for the deterministic 2026 ERP simulation.
    # It is disabled by default and is explicitly forbidden in production.
    enable_uat_2026_controls: bool = False

    database_url: str = "postgresql+psycopg://asset_user:asset_password@db:5432/asset_management"
    database_pool_size: int = 5
    database_max_overflow: int = 5
    database_pool_timeout_seconds: int = 30
    database_pool_recycle_seconds: int = 1800

    jwt_secret: str = "change-this-secret-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    cors_origins: str = "http://localhost:3100,http://localhost:8088"
    trusted_hosts: str = "localhost,127.0.0.1"

    # Employee portal authentication and ticketing. Existing department logins
    # continue to work when these features are not yet configured.
    employee_portal_enabled: bool = True
    allowed_email_domains: str = "nakshatech.com"
    email_delivery_mode: str = "console"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@nakshatech.com"
    smtp_from_name: str = "NakshaTech CRM"
    smtp_use_tls: bool = True
    smtp_use_ssl: bool = False
    it_support_email: str = "software.team@nakshatech.com"
    ticket_email_heading: str = "NakshaTech IT Support"
    finance_email_heading: str = "NakshaTech Finance CRM"
    finance_admin_notification_emails: str = "admin@nakshatech.com"
    finance_team_notification_emails: str = "finance@nakshatech.com"
    app_public_url: str = "http://localhost:3100"
    email_otp_expiry_minutes: int = 10
    email_otp_resend_seconds: int = 60
    email_otp_max_attempts: int = 5
    email_otp_max_requests_per_hour: int = 5
    temporary_token_minutes: int = 15
    totp_issuer: str = "NakshaTech CRM"
    totp_encryption_key: str = ""
    totp_valid_window: int = 1

    # Purchase approval email channel. PURCHASE_APPROVAL_PUBLIC_URL may point to
    # a LAN/staging URL during UAT so a test colleague can open the secure link.
    # When blank it falls back to APP_PUBLIC_URL.
    purchase_approval_public_url: str = ""
    purchase_approval_email_heading: str = "NakshaTech Purchase Approval"
    purchase_approval_email_token_hours: int = 72

    seed_excel_path: str = str(Path(__file__).resolve().parents[1] / "data" / "nakshatech_asset_template.xlsx")

    # Historical/server backup settings.
    backup_root: str = str(Path.home() / "nakshatech_backups")
    backup_timezone: str = "Asia/Kolkata"
    backup_database_enabled: bool = True
    backup_minio_enabled: bool = False
    backup_daily_retention_days: int = 90
    backup_database_retention_days: int = 30
    backup_command_timeout_seconds: int = 1800
    backup_stale_lock_seconds: int = 21600
    pg_dump_bin: str = "pg_dump"

    minio_endpoint: str = "minio:9000"
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin123"
    minio_bucket: str = "asset-files"
    minio_secure: bool = False

    # Local Windows backup-agent settings.
    local_backup_agent_enabled: bool = False
    local_backup_agent_token: str = ""
    # The backup agent authenticates with one shared secret, so the export roles it
    # may request are pinned server-side instead of being asserted by the caller.
    # "admin" and "software_team" are deliberately absent: both resolve to the
    # full-access export scope that includes the System Users sheet.
    local_backup_agent_roles: str = "it,drone,management"

    # Naksha Copilot: backend-only, read-only Gemini integration.
    naksha_copilot_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    naksha_copilot_timeout_seconds: float = 25.0
    naksha_copilot_requests_per_hour: int = 20
    naksha_copilot_max_output_tokens: int = 900
    redis_url: str = "redis://redis:6379/0"

    # Software Team desktop-agent monitoring gateway. The admin key remains
    # backend-only and is never returned to the browser.
    agent_monitor_enabled: bool = False
    agent_monitor_base_url: str = ""
    agent_monitor_admin_key: str = ""
    agent_monitor_timeout_seconds: float = 10.0

    # Project commercial / FX. Provider details are configuration, never hard-wired into
    # the data model: every stored rate records its own source. No provider credential is
    # ever sent to the browser. If every provider fails the API reports FX_UNAVAILABLE and
    # the user may enter a documented manual rate; the system never invents a rate.
    fx_provider_order: str = "frankfurter,open_er_api"
    fx_frankfurter_base_url: str = "https://api.frankfurter.dev/v1"
    fx_open_er_api_base_url: str = "https://open.er-api.com/v6"
    fx_timeout_seconds: float = 8.0
    fx_max_retries: int = 2
    fx_cache_ttl_seconds: int = 900
    commercial_estimate_required_on_submit: bool = False
    # New (never-submitted) projects must carry Commercial Revision 1 when BD submits them to Finance.
    # Legacy projects that were already submitted/returned before the commercial layer stay resubmittable.
    commercial_revision1_required_on_submit: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def is_production(self) -> bool:
        return "production" in {self.environment.strip().lower(), self.app_env.strip().lower()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

    @property
    def local_backup_agent_role_list(self) -> list[str]:
        return [item.strip().lower() for item in self.local_backup_agent_roles.split(",") if item.strip()]

    @property
    def allowed_email_domain_list(self) -> list[str]:
        return [item.strip().lower().lstrip("@") for item in self.allowed_email_domains.split(",") if item.strip()]

    @property
    def purchase_approval_base_url(self) -> str:
        return (self.purchase_approval_public_url.strip() or self.app_public_url.strip()).rstrip("/")

    @property
    def docs_url(self) -> str | None:
        return "/docs" if self.docs_enabled else None

    @property
    def redoc_url(self) -> str | None:
        return "/redoc" if self.docs_enabled else None

    @property
    def openapi_url(self) -> str | None:
        return "/openapi.json" if self.docs_enabled else None

    def validate_baseline_settings(self) -> None:
        """Reject secrets that are public knowledge, in ANY environment.

        This runs unconditionally, unlike :meth:`validate_production_settings`,
        because the strings rejected here are published in this repository
        (source, example files and git history). Anyone who can read them can
        mint a valid HS256 token for any identity, so accepting one is an
        authentication bypass rather than a stylistic problem. Production-only
        checks stay behind :attr:`is_production`.
        """
        secret = self.jwt_secret.strip()
        if len(secret) < 32:
            raise RuntimeError(
                "JWT_SECRET must be at least 32 characters. Generate one with: "
                "python -c \"import secrets,sys; sys.stdout.write(secrets.token_hex(32))\""
            )
        if secret.lower() in _PUBLICLY_KNOWN_SECRETS:
            raise RuntimeError(
                "JWT_SECRET is a placeholder published in this repository, which lets anyone "
                "forge access tokens for any account. Generate a private secret with: "
                "python -c \"import secrets,sys; sys.stdout.write(secrets.token_hex(32))\""
            )

    def validate_production_settings(self) -> None:
        """Fail fast when an unsafe production configuration is detected."""
        if not self.is_production:
            self.validate_baseline_settings()
            return
        # Test-only operational accounts must never be enabled in production.
        # Check this before unrelated production-secret validation so the guard
        # remains deterministic even when multiple unsafe settings are present.
        if self.seed_operations_test_users_enabled:
            raise RuntimeError("SEED_OPERATIONS_TEST_USERS_ENABLED must be false in production")
        if self.enable_test_employee_seed:
            raise RuntimeError("ENABLE_TEST_EMPLOYEE_SEED must be false in production")
        if self.enable_uat_2026_controls:
            raise RuntimeError("ENABLE_UAT_2026_CONTROLS must be false in production")
        if self.docs_enabled:
            raise RuntimeError(
                "DOCS_ENABLED must be false in production: /docs, /redoc and /openapi.json "
                "publish the full route and schema map to anonymous callers"
            )
        self.validate_baseline_settings()
        if "asset_password@db" in self.database_url or "REPLACE_ME" in self.database_url:
            raise RuntimeError("DATABASE_URL still contains a development or placeholder value")
        if not self.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must include the production frontend origin")
        if self.local_backup_agent_enabled and len(self.local_backup_agent_token.strip()) < 32:
            raise RuntimeError("LOCAL_BACKUP_AGENT_TOKEN must be at least 32 characters when enabled")
        if self.local_backup_agent_enabled:
            forbidden = {"admin", "software_team"} & set(self.local_backup_agent_role_list)
            if forbidden:
                raise RuntimeError(
                    "LOCAL_BACKUP_AGENT_ROLES must not grant the full-access export scope in production: "
                    + ", ".join(sorted(forbidden))
                )
        # Admin and Drone are included deliberately: both are provisioned by
        # _ensure_admin_role / the seed roster with no MFA and no forced password
        # change, so a published default for either is a direct login.
        privileged_temporary_passwords = {
            "SEED_ADMIN_PASSWORD": self.seed_admin_password,
            "SEED_DRONE_PASSWORD": self.seed_drone_password,
            "SEED_MANAGEMENT_PASSWORD": self.seed_management_password,
            "SEED_MANAGEMENT_SECONDARY_PASSWORD": self.seed_management_secondary_password,
            "SEED_SOFTWARE_TEAM_PASSWORD": self.seed_software_team_password,
            "SEED_IT_PASSWORD": self.seed_it_password,
            "SEED_FINANCE_PASSWORD": self.seed_finance_password,
            "SEED_HR_PASSWORD": self.seed_hr_password,
        }
        unsafe = sorted(
            name
            for name, value in privileged_temporary_passwords.items()
            if len(value.strip()) < 10
            or value.strip().startswith("ChangeMe")
            or _is_unedited_template(value)
        )
        if unsafe:
            raise RuntimeError(
                "Production requires strong private values for: "
                + ", ".join(unsafe)
                + " (found a default, a placeholder, or a value shorter than 10 characters)"
            )
        if self.employee_portal_enabled:
            if not self.allowed_email_domain_list:
                raise RuntimeError("ALLOWED_EMAIL_DOMAINS must contain at least one organization domain")
            if self.email_delivery_mode.strip().lower() != "smtp":
                raise RuntimeError("EMAIL_DELIVERY_MODE must be smtp when the employee portal is enabled in production")
            if not self.smtp_host.strip() or not self.smtp_from_email.strip():
                raise RuntimeError("SMTP_HOST and SMTP_FROM_EMAIL are required when EMAIL_DELIVERY_MODE=smtp")
            if self.smtp_use_ssl and self.smtp_use_tls:
                raise RuntimeError("Enable only one of SMTP_USE_SSL or SMTP_USE_TLS")
            if len(self.totp_encryption_key.strip()) < 32:
                raise RuntimeError("TOTP_ENCRYPTION_KEY must be a separate production secret of at least 32 characters")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
