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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="OPEN_MESSENGER_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
