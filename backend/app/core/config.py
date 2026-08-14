from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NakshaTech Asset Management System"
    app_version: str = "1.0.0"
    environment: str = "development"

    # Local Docker serves the API under /api. For cPanel Passenger, the app is
    # mounted externally at /api, so API_PREFIX is intentionally set to an
    # empty string in the cPanel environment.
    api_prefix: str = "/api"
    root_path: str = ""
    docs_enabled: bool = True
    enable_background_watcher: bool = True
    seed_default_users: bool = True

    # Privileged department accounts are provisioned by NakshaTech and are not
    # available through public employee registration. Temporary first-login
    # passwords are stored only in protected environment configuration.
    seed_admin_email: str = "admin@nakshatech.com"
    seed_admin_password: str = "ChangeMeLocalAdmin@2026!"
    seed_software_team_email: str = "software.team@nakshatech.com"
    seed_software_team_password: str = "ChangeMeLocalSoftwareTeam@2026!"
    # Optional additional organization Admin retained for backward compatibility.
    seed_organization_admin_name: str = "NakshaTech Administrator"
    seed_organization_admin_email: str = ""
    seed_organization_admin_password: str = ""
    # Management access is restricted to the two authoritative accounts in
    # app.core.management_access. These settings contain only their temporary
    # first-login passwords; permanent passwords are stored as database hashes.
    seed_management_email: str = "vinod@nakshatech.com"
    seed_management_password: str = "ChangeMeLocalVinod@2026!"
    seed_management_secondary_email: str = "chethan@nakshatech.com"
    seed_management_secondary_password: str = "ChangeMeLocalChethan@2026!"
    seed_it_email: str = "it-support@nakshatech.com"
    seed_it_password: str = "ChangeMeLocalITSupport@2026!"
    seed_drone_email: str = "drone@nakshatech.com"
    seed_drone_password: str = "ChangeMeLocalDrone@2026!"

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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [item.strip() for item in self.trusted_hosts.split(",") if item.strip()]

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

    def validate_production_settings(self) -> None:
        """Fail fast when an unsafe production configuration is detected."""
        if not self.is_production:
            return
        weak_secrets = {
            "change-this-secret-before-production",
            "change-this-secret-before-production-with-at-least-32-characters",
            "secret",
            "password",
        }
        if len(self.jwt_secret.strip()) < 32 or self.jwt_secret.strip() in weak_secrets:
            raise RuntimeError("JWT_SECRET must be a unique production secret of at least 32 characters")
        if "asset_password@db" in self.database_url or "REPLACE_ME" in self.database_url:
            raise RuntimeError("DATABASE_URL still contains a development or placeholder value")
        if not self.cors_origin_list:
            raise RuntimeError("CORS_ORIGINS must include the production frontend origin")
        if self.local_backup_agent_enabled and len(self.local_backup_agent_token.strip()) < 32:
            raise RuntimeError("LOCAL_BACKUP_AGENT_TOKEN must be at least 32 characters when enabled")
        privileged_temporary_passwords = (
            self.seed_management_password.strip(),
            self.seed_management_secondary_password.strip(),
            self.seed_software_team_password.strip(),
            self.seed_it_password.strip(),
        )
        if any(len(value) < 10 or value.startswith("ChangeMe") for value in privileged_temporary_passwords):
            raise RuntimeError(
                "Management, Software Team, and IT temporary passwords must be replaced with strong private values"
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
