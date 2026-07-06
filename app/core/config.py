from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TASKFLOW_", extra="ignore")

    app_name: str = "TaskFlow API"
    environment: str = "dev"
    database_url: str = "postgresql+psycopg://taskflow:taskflow@localhost:5432/taskflow"
    # HS256 wants >= 32 bytes; real deployments must override via env.
    jwt_secret: str = "dev-only-secret-change-me-minimum-32-bytes!"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 120
    rate_limit_burst: int = 40


@lru_cache
def get_settings() -> Settings:
    return Settings()
