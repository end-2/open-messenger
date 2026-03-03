from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import Settings
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.interfaces import MessageContentStore, MetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore


class UnsupportedMessageContentStore(MessageContentStore):
    """Placeholder for backends not implemented yet."""

    def __init__(self, backend_name: str) -> None:
        self.backend_name = backend_name

    async def put(self, content_id: str, payload: dict[str, Any]) -> None:
        self._raise_not_supported()

    async def get(self, content_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def delete(self, content_id: str) -> None:
        self._raise_not_supported()

    def _raise_not_supported(self) -> None:
        raise NotImplementedError(
            f"Message content backend '{self.backend_name}' is not implemented yet."
        )


class UnsupportedMetadataStore(MetadataStore):
    """Placeholder for backends not implemented yet."""

    def __init__(self, backend_name: str) -> None:
        self.backend_name = backend_name

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def create_token(self, token: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_token(self, token_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def update_token(self, token_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def create_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def update_thread(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def create_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def list_channel_messages(
        self,
        channel_id: str,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        self._raise_not_supported()

    async def find_message_by_idempotency(
        self,
        channel_id: str,
        thread_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        self._raise_not_supported()

    async def create_file(self, file_object: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        self._raise_not_supported()

    def _raise_not_supported(self) -> None:
        raise NotImplementedError(
            f"Metadata backend '{self.backend_name}' is not implemented yet."
        )


def build_storage_registry(settings: Settings) -> tuple[MessageContentStore, MetadataStore]:
    """Build store instances selected by runtime configuration."""

    storage_root = Path(settings.storage_dir)

    content_store: MessageContentStore
    metadata_store: MetadataStore

    if settings.content_backend == "memory":
        content_store = InMemoryMessageContentStore()
    elif settings.content_backend == "file":
        content_store = FileMessageContentStore(storage_root / "content")
    elif settings.content_backend == "redis":
        content_store = RedisMessageContentStore(
            redis_url=settings.redis_url,
            key_prefix=settings.redis_content_key_prefix,
        )
    else:
        content_store = UnsupportedMessageContentStore(settings.content_backend)

    if settings.metadata_backend == "memory":
        metadata_store = InMemoryMetadataStore()
    elif settings.metadata_backend == "file":
        metadata_store = FileMetadataStore(storage_root / "metadata.json")
    elif settings.metadata_backend == "mysql":
        metadata_store = MySQLMetadataStore(
            dsn=settings.mysql_dsn,
            table_prefix=settings.mysql_table_prefix,
        )
    else:
        metadata_store = UnsupportedMetadataStore(settings.metadata_backend)

    return content_store, metadata_store
