from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables."""

    app_name: str = "open-messenger"
    api_version: str = "v0.1"
    environment: Literal["dev", "staging", "prod", "test"] = "dev"
    content_backend: Literal["memory", "file", "redis"] = "memory"
    metadata_backend: Literal["memory", "file", "mysql"] = "memory"
    file_storage_backend: Literal["local"] = "local"
    storage_dir: str = "data/storage"
    redis_url: str = "redis://localhost:6379/0"
    redis_content_key_prefix: str = "open_messenger:content"
    mysql_dsn: str = "mysql+pymysql://app:app@localhost:3306/open_messenger"
    mysql_table_prefix: str = "open_messenger"
    files_root_dir: str = "data/files"
    max_upload_mb: int = 50
    admin_api_token: str = "dev-admin-token"
    token_signing_secret: str = "dev-signing-secret"
    rate_limit_max_requests: int = 60
    rate_limit_window_seconds: int = 60
    tracing_enabled: bool = False
    tracing_service_name: str = "open-messenger-api"
    otlp_traces_endpoint: str = "http://localhost:4318/v1/traces"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPEN_MESSENGER_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
