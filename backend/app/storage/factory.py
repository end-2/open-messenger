from __future__ import annotations

from typing import Any

from app.config import Settings
from app.storage.interfaces import MessageContentStore, MetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore


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

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        self._raise_not_supported()

    def _raise_not_supported(self) -> None:
        raise NotImplementedError(
            f"Metadata backend '{self.backend_name}' is not implemented yet."
        )


def build_storage_registry(settings: Settings) -> tuple[MessageContentStore, MetadataStore]:
    """Build store instances selected by runtime configuration."""

    content_store: MessageContentStore
    metadata_store: MetadataStore

    if settings.content_backend == "memory":
        content_store = InMemoryMessageContentStore()
    else:
        content_store = UnsupportedMessageContentStore(settings.content_backend)

    if settings.metadata_backend == "memory":
        metadata_store = InMemoryMetadataStore()
    else:
        metadata_store = UnsupportedMetadataStore(settings.metadata_backend)

    return content_store, metadata_store
