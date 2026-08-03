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

    seed_admin_email: str = "software-support@nakshatech.com"
    seed_admin_password: str = "ChangeMeLocalAdmin@2026!"
    # The legacy SEED_ADMIN_* variables now preserve the existing Software Team account.
    # A separate organization Admin can be seeded with the optional variables below.
    seed_organization_admin_name: str = "NakshaTech Administrator"
    seed_organization_admin_email: str = ""
    seed_organization_admin_password: str = ""
    seed_management_email: str = "management@nakshatech.com"
    seed_management_password: str = "ChangeMeLocalManagement@2026!"
    seed_it_email: str = "it@nakshatech.com"
    seed_it_password: str = "ChangeMeLocalIT@2026!"
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
