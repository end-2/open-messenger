from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

from redis import Redis

from app.storage.interfaces import MessageContentStore


class RedisMessageContentStore(MessageContentStore):
    """Redis implementation for message body content."""

    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "open_messenger:content",
        client: Redis | None = None,
    ) -> None:
        self._key_prefix = key_prefix
        self._client = client if client is not None else Redis.from_url(redis_url)

    async def put(self, content_id: str, payload: dict[str, Any]) -> None:
        serialized = json.dumps(deepcopy(payload), ensure_ascii=True, separators=(",", ":"))
        await asyncio.to_thread(self._client.set, self._key(content_id), serialized)

    async def get(self, content_id: str) -> dict[str, Any] | None:
        raw_value = await asyncio.to_thread(self._client.get, self._key(content_id))
        if raw_value is None:
            return None

        return self._deserialize(raw_value)

    async def get_many(self, content_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not content_ids:
            return {}

        keys = [self._key(content_id) for content_id in content_ids]
        raw_values = await asyncio.to_thread(self._client.mget, keys)
        items: dict[str, dict[str, Any]] = {}
        for content_id, raw_value in zip(content_ids, raw_values):
            if raw_value is None:
                continue
            items[content_id] = self._deserialize(raw_value)
        return items

    @staticmethod
    def _deserialize(raw_value: bytes | str) -> dict[str, Any]:
        if isinstance(raw_value, bytes):
            decoded = raw_value.decode("utf-8")
        else:
            decoded = str(raw_value)
        return json.loads(decoded)

    async def delete(self, content_id: str) -> None:
        await asyncio.to_thread(self._client.delete, self._key(content_id))

    def _key(self, content_id: str) -> str:
        return f"{self._key_prefix}:{content_id}"
