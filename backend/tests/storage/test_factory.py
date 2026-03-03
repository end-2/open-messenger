import asyncio

import pytest

from app.config import Settings
from app.storage.factory import (
    UnsupportedMessageContentStore,
    UnsupportedMetadataStore,
    build_storage_registry,
)
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore


def test_build_storage_registry_selects_memory_implementations() -> None:
    settings = Settings(content_backend="memory", metadata_backend="memory")

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, InMemoryMessageContentStore)
    assert isinstance(metadata_store, InMemoryMetadataStore)


def test_build_storage_registry_returns_unsupported_placeholders() -> None:
    settings = Settings(content_backend="redis", metadata_backend="mysql")

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, UnsupportedMessageContentStore)
    assert isinstance(metadata_store, UnsupportedMetadataStore)

    with pytest.raises(NotImplementedError):
        asyncio.run(content_store.put("content-1", {"text": "hello"}))

    with pytest.raises(NotImplementedError):
        asyncio.run(metadata_store.create_channel({"channel_id": "channel-a"}))
