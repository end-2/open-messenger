from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.storage.interfaces import MessageContentStore, MetadataStore


class InMemoryMessageContentStore(MessageContentStore):
    """In-memory implementation for message body content."""

    def __init__(self) -> None:
        self._content: dict[str, dict[str, Any]] = {}

    async def put(self, content_id: str, payload: dict[str, Any]) -> None:
        self._content[content_id] = deepcopy(payload)

    async def get(self, content_id: str) -> dict[str, Any] | None:
        payload = self._content.get(content_id)
        if payload is None:
            return None
        return deepcopy(payload)

    async def delete(self, content_id: str) -> None:
        self._content.pop(content_id, None)


class InMemoryMetadataStore(MetadataStore):
    """In-memory implementation for metadata entities."""

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, Any]] = {}
        self._messages: dict[str, dict[str, Any]] = {}
        self._channel_index: dict[str, list[str]] = {}

    async def create_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        message_id = str(msg["message_id"])
        channel_id = str(msg["channel_id"])

        record = deepcopy(msg)
        self._messages[message_id] = record
        self._channel_index.setdefault(channel_id, []).append(message_id)
        return deepcopy(record)

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        msg = self._messages.get(message_id)
        if msg is None:
            return None
        return deepcopy(msg)

    async def list_channel_messages(
        self,
        channel_id: str,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        message_ids = self._channel_index.get(channel_id, [])
        start_idx = 0

        if cursor:
            try:
                start_idx = message_ids.index(cursor) + 1
            except ValueError:
                start_idx = 0

        selected_ids = message_ids[start_idx : start_idx + max(limit, 0)]
        return [deepcopy(self._messages[msg_id]) for msg_id in selected_ids]

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel["channel_id"])
        record = deepcopy(channel)
        self._channels[channel_id] = record
        self._channel_index.setdefault(channel_id, [])
        return deepcopy(record)
