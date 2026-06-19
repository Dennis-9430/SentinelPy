"""Application configuration via pydantic-settings."""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Configuration loaded from environment variables (.env)."""

    app_name: str = "SentinelPy"
    app_version: str = "0.1.0"
    debug: bool = True

    # Database
    database_url: str = "postgresql+asyncpg://sentinel:sentinel_dev@localhost:5432/sentinelpy"

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 30

    # Collector
    syslog_host: str = "0.0.0.0"
    syslog_port: int = 5140

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
