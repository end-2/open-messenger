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

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        ...

    async def create_token(self, token: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_token(self, token_id: str) -> dict[str, Any] | None:
        ...

    async def update_token(self, token_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        ...

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        ...

    async def create_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        ...

    async def update_thread(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
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

    async def find_message_by_idempotency(
        self,
        channel_id: str,
        thread_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        ...

    async def create_file(self, file_object: dict[str, Any]) -> dict[str, Any]:
        ...

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        ...
