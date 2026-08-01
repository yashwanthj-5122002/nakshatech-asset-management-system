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
    backup_timezone: str = "Asia/Kolkata"
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
