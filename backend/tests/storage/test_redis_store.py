from __future__ import annotations

import asyncio

from app.storage.redis_store import RedisMessageContentStore


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key: str, value: str) -> bool:
        self.data[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.data.get(key) for key in keys]

    def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            return 1
        return 0


def test_redis_message_content_store_crud_with_fake_client() -> None:
    client = FakeRedis()
    store = RedisMessageContentStore(
        redis_url="redis://unused",
        key_prefix="test:content",
        client=client,
    )

    asyncio.run(store.put("content-1", {"text": "hello", "metadata": {"x": 1}}))
    loaded = asyncio.run(store.get("content-1"))

    assert loaded == {"text": "hello", "metadata": {"x": 1}}

    loaded["text"] = "changed"
    reloaded = asyncio.run(store.get("content-1"))
    assert reloaded == {"text": "hello", "metadata": {"x": 1}}

    asyncio.run(store.delete("content-1"))
    assert asyncio.run(store.get("content-1")) is None


def test_redis_message_content_store_get_many_with_fake_client() -> None:
    client = FakeRedis()
    store = RedisMessageContentStore(
        redis_url="redis://unused",
        key_prefix="test:content",
        client=client,
    )

    asyncio.run(store.put("content-1", {"text": "hello"}))
    asyncio.run(store.put("content-2", {"text": "world"}))

    loaded = asyncio.run(store.get_many(["content-2", "content-1", "content-missing"]))

    assert loaded == {
        "content-1": {"text": "hello"},
        "content-2": {"text": "world"},
    }
