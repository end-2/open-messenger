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
    storage_dir: str = "data/storage"
    redis_url: str = "redis://localhost:6379/0"
    redis_content_key_prefix: str = "open_messenger:content"
    mysql_dsn: str = "mysql+pymysql://app:app@localhost:3306/open_messenger"
    mysql_table_prefix: str = "open_messenger"
    admin_api_token: str = "dev-admin-token"
    token_signing_secret: str = "dev-signing-secret"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPEN_MESSENGER_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
