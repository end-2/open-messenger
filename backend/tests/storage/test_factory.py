import asyncio

import pytest

from app.config import Settings
from app.storage.file import FileMessageContentStore, FileMetadataStore
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


def test_build_storage_registry_selects_file_implementations(tmp_path) -> None:
    settings = Settings(
        content_backend="file",
        metadata_backend="file",
        storage_dir=str(tmp_path),
    )

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, FileMessageContentStore)
    assert isinstance(metadata_store, FileMetadataStore)


def test_build_storage_registry_returns_unsupported_placeholders() -> None:
    settings = Settings(content_backend="redis", metadata_backend="mysql")

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, UnsupportedMessageContentStore)
    assert isinstance(metadata_store, UnsupportedMetadataStore)

    with pytest.raises(NotImplementedError):
        asyncio.run(content_store.put("content-1", {"text": "hello"}))

    with pytest.raises(NotImplementedError):
        asyncio.run(metadata_store.create_channel({"channel_id": "channel-a"}))

    with pytest.raises(NotImplementedError):
        asyncio.run(
            metadata_store.create_thread(
                {"thread_id": "th-1", "channel_id": "channel-a", "root_message_id": "msg-1"}
            )
        )

    with pytest.raises(NotImplementedError):
        asyncio.run(
            metadata_store.create_user(
                {"user_id": "usr-1", "username": "alice", "created_at": "2026-03-03T00:00:00+00:00"}
            )
        )
