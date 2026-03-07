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
        self._users: dict[str, dict[str, Any]] = {}
        self._tokens: dict[str, dict[str, Any]] = {}
        self._channels: dict[str, dict[str, Any]] = {}
        self._threads: dict[str, dict[str, Any]] = {}
        self._messages: dict[str, dict[str, Any]] = {}
        self._files: dict[str, dict[str, Any]] = {}
        self._compat_mappings: dict[tuple[str, str, str | None, str], dict[str, Any]] = {}
        self._compat_sequences: dict[tuple[str, str], int] = {}
        self._channel_index: dict[str, list[str]] = {}

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = str(user["user_id"])
        record = deepcopy(user)
        self._users[user_id] = record
        return deepcopy(record)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        user = self._users.get(user_id)
        if user is None:
            return None
        return deepcopy(user)

    async def create_token(self, token: dict[str, Any]) -> dict[str, Any]:
        token_id = str(token["token_id"])
        record = deepcopy(token)
        self._tokens[token_id] = record
        return deepcopy(record)

    async def get_token(self, token_id: str) -> dict[str, Any] | None:
        token = self._tokens.get(token_id)
        if token is None:
            return None
        return deepcopy(token)

    async def update_token(self, token_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        token = self._tokens.get(token_id)
        if token is None:
            return None
        token.update(deepcopy(patch))
        return deepcopy(token)

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel["channel_id"])
        record = deepcopy(channel)
        self._channels[channel_id] = record
        self._channel_index.setdefault(channel_id, [])
        return deepcopy(record)

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        channel = self._channels.get(channel_id)
        if channel is None:
            return None
        return deepcopy(channel)

    async def create_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        thread_id = str(thread["thread_id"])
        record = deepcopy(thread)
        self._threads[thread_id] = record
        return deepcopy(record)

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        thread = self._threads.get(thread_id)
        if thread is None:
            return None
        return deepcopy(thread)

    async def get_thread_by_root_message(self, root_message_id: str) -> dict[str, Any] | None:
        for thread in self._threads.values():
            if str(thread.get("root_message_id")) == root_message_id:
                return deepcopy(thread)
        return None

    async def update_thread(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        thread = self._threads.get(thread_id)
        if thread is None:
            return None
        thread.update(deepcopy(patch))
        return deepcopy(thread)

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

    async def list_thread_messages(
        self,
        channel_id: str,
        thread_id: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        selected_ids = self._channel_index.get(channel_id, [])
        items: list[dict[str, Any]] = []
        for message_id in selected_ids:
            record = self._messages[message_id]
            if record.get("thread_id") != thread_id:
                continue
            items.append(deepcopy(record))
            if len(items) >= max(limit, 0):
                break
        return items

    async def find_message_by_idempotency(
        self,
        channel_id: str,
        thread_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        for message_id in self._channel_index.get(channel_id, []):
            record = self._messages[message_id]
            if (
                record.get("idempotency_key") == idempotency_key
                and record.get("thread_id") == thread_id
            ):
                return deepcopy(record)
        return None

    async def create_file(self, file_object: dict[str, Any]) -> dict[str, Any]:
        file_id = str(file_object["file_id"])
        record = deepcopy(file_object)
        self._files[file_id] = record
        return deepcopy(record)

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        record = self._files.get(file_id)
        if record is None:
            return None
        return deepcopy(record)

    async def create_compat_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        record = deepcopy(mapping)
        key = (
            str(record["origin"]),
            str(record["entity_type"]),
            record.get("channel_id"),
            str(record["external_id"]),
        )
        self._compat_mappings[key] = record
        return deepcopy(record)

    async def get_compat_mapping(
        self,
        origin: str,
        entity_type: str,
        external_id: str,
        channel_id: str | None = None,
    ) -> dict[str, Any] | None:
        record = self._compat_mappings.get((origin, entity_type, channel_id, external_id))
        if record is None:
            return None
        return deepcopy(record)

    async def next_compat_sequence(self, origin: str, channel_id: str) -> int:
        key = (origin, channel_id)
        current = self._compat_sequences.get(key, 0) + 1
        self._compat_sequences[key] = current
        return current
