from __future__ import annotations

from typing import Any, Protocol


class MessageContentStore(Protocol):
    """Stores message body payloads by content reference."""

    async def put(self, content_id: str, payload: dict[str, Any]) -> None:
        ...

    async def get(self, content_id: str) -> dict[str, Any] | None:
        ...

    async def delete(self, content_id: str) -> None:
        ...


class MetadataStore(Protocol):
    """Stores messaging metadata entities."""

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        ...

    async def create_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        ...

    async def list_channel_messages(
        self,
        channel_id: str,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        ...
