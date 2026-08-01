from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "NakshaTech Asset Management System"
    api_prefix: str = "/api"
    database_url: str = "postgresql+psycopg://asset_user:asset_password@db:5432/asset_management"
    jwt_secret: str = "change-this-secret-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480
    cors_origins: str = "http://localhost:3100,http://localhost:8088"
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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
