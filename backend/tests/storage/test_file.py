import asyncio

from app.storage.blob import LocalFileBinaryStore
from app.storage.file import FileMessageContentStore, FileMetadataStore


def test_file_message_content_store_crud(tmp_path) -> None:
    store = FileMessageContentStore(tmp_path / "content")

    asyncio.run(store.put("content-1", {"text": "hello"}))
    loaded = asyncio.run(store.get("content-1"))

    assert loaded == {"text": "hello"}
    assert loaded is not None

    loaded["text"] = "changed"
    reloaded = asyncio.run(store.get("content-1"))

    assert reloaded == {"text": "hello"}

    asyncio.run(store.delete("content-1"))
    assert asyncio.run(store.get("content-1")) is None


def test_file_metadata_store_persists_and_paginates(tmp_path) -> None:
    db_path = tmp_path / "metadata" / "store.json"
    store = FileMetadataStore(db_path)

    user = asyncio.run(
        store.create_user(
            {
                "user_id": "usr-1",
                "username": "alice",
                "display_name": "Alice",
                "created_at": "2026-03-03T00:00:00+00:00",
            }
        )
    )
    assert asyncio.run(store.get_user("usr-1")) == user

    token = asyncio.run(
        store.create_token(
            {
                "token_id": "tok-1",
                "user_id": "usr-1",
                "token_type": "user_token",
                "scopes": ["messages:write"],
                "token_hash": "hash-1",
                "created_at": "2026-03-03T00:00:00+00:00",
                "revoked_at": None,
            }
        )
    )
    assert asyncio.run(store.get_token("tok-1")) == token
    updated_token = asyncio.run(
        store.update_token("tok-1", {"revoked_at": "2026-03-03T01:00:00+00:00"})
    )
    assert updated_token is not None
    assert updated_token["revoked_at"] == "2026-03-03T01:00:00+00:00"

    asyncio.run(store.create_channel({"channel_id": "channel-a", "name": "general"}))
    assert asyncio.run(store.get_channel("channel-a")) == {
        "channel_id": "channel-a",
        "name": "general",
    }
    thread = asyncio.run(
        store.create_thread(
            {
                "thread_id": "th-1",
                "channel_id": "channel-a",
                "root_message_id": "msg-1",
                "reply_count": 0,
                "last_message_at": "2026-03-03T00:00:00+00:00",
                "created_at": "2026-03-03T00:00:00+00:00",
            }
        )
    )
    assert asyncio.run(store.get_thread("th-1")) == thread
    updated_thread = asyncio.run(
        store.update_thread(
            "th-1",
            {"reply_count": 2, "last_message_at": "2026-03-03T02:00:00+00:00"},
        )
    )
    assert updated_thread is not None
    assert updated_thread["reply_count"] == 2

    m1 = asyncio.run(
        store.create_message(
            {
                "message_id": "msg-1",
                "channel_id": "channel-a",
                "content_ref": "content-1",
            }
        )
    )
    asyncio.run(
        store.create_message(
            {
                "message_id": "msg-2",
                "channel_id": "channel-a",
                "content_ref": "content-2",
            }
        )
    )
    asyncio.run(
        store.create_message(
            {
                "message_id": "msg-3",
                "channel_id": "channel-a",
                "content_ref": "content-3",
            }
        )
    )

    page1 = asyncio.run(store.list_channel_messages("channel-a", cursor=None, limit=2))
    page2 = asyncio.run(
        store.list_channel_messages("channel-a", cursor=page1[-1]["message_id"], limit=2)
    )
    thread_page = asyncio.run(store.list_thread_messages("channel-a", "th-1", limit=10))

    assert db_path.exists()
    assert page1 == [
        {"message_id": "msg-1", "channel_id": "channel-a", "content_ref": "content-1"},
        {"message_id": "msg-2", "channel_id": "channel-a", "content_ref": "content-2"},
    ]
    assert page2 == [
        {"message_id": "msg-3", "channel_id": "channel-a", "content_ref": "content-3"}
    ]
    assert thread_page == []

    reloaded_store = FileMetadataStore(db_path)
    assert asyncio.run(reloaded_store.get_user("usr-1")) == user
    assert asyncio.run(reloaded_store.get_token("tok-1")) is not None
    assert asyncio.run(reloaded_store.get_channel("channel-a")) == {
        "channel_id": "channel-a",
        "name": "general",
    }
    assert asyncio.run(reloaded_store.get_thread("th-1")) is not None
    assert asyncio.run(reloaded_store.get_message(m1["message_id"])) == m1

    asyncio.run(
        store.create_message(
            {
                "message_id": "msg-idemp",
                "channel_id": "channel-b",
                "thread_id": None,
                "content_ref": "content-idemp",
                "idempotency_key": "req-1",
            }
        )
    )
    found = asyncio.run(store.find_message_by_idempotency("channel-b", None, "req-1"))
    assert found is not None
    assert found["message_id"] == "msg-idemp"

    created_file = asyncio.run(
        store.create_file(
            {
                "file_id": "fil-1",
                "filename": "hello.txt",
                "mime_type": "text/plain",
                "size_bytes": 5,
                "storage_backend": "local",
                "storage_path": "/tmp/hello.txt",
                "sha256": "abc123",
            }
        )
    )
    assert asyncio.run(store.get_file("fil-1")) == created_file
    assert asyncio.run(store.get_thread_by_root_message("msg-1")) == updated_thread

    mapping = asyncio.run(
        store.create_compat_mapping(
            {
                "mapping_id": "map-1",
                "origin": "discord",
                "entity_type": "message",
                "channel_id": "channel-a",
                "external_id": "42",
                "internal_id": "msg-1",
                "created_at": "2026-03-03T00:00:00+00:00",
            }
        )
    )
    assert (
        asyncio.run(store.get_compat_mapping("discord", "message", "42", "channel-a")) == mapping
    )
    assert asyncio.run(store.next_compat_sequence("discord", "channel-a")) == 1
    assert asyncio.run(store.next_compat_sequence("discord", "channel-a")) == 2

    reloaded_store = FileMetadataStore(db_path)
    assert (
        asyncio.run(reloaded_store.get_compat_mapping("discord", "message", "42", "channel-a"))
        == mapping
    )


def test_file_metadata_store_delete_channel_removes_related_records(tmp_path) -> None:
    db_path = tmp_path / "metadata" / "store.json"
    store = FileMetadataStore(db_path)

    created_channel = asyncio.run(
        store.create_channel(
            {"channel_id": "channel-a", "name": "general", "created_at": "2026-03-03T00:00:00+00:00"}
        )
    )
    asyncio.run(
        store.create_thread(
            {
                "thread_id": "th-1",
                "channel_id": "channel-a",
                "root_message_id": "msg-1",
                "reply_count": 1,
                "last_message_at": "2026-03-03T00:00:00+00:00",
                "created_at": "2026-03-03T00:00:00+00:00",
            }
        )
    )
    asyncio.run(
        store.create_message(
            {
                "message_id": "msg-1",
                "channel_id": "channel-a",
                "thread_id": None,
                "content_ref": "content-1",
            }
        )
    )
    asyncio.run(
        store.create_message(
            {
                "message_id": "msg-2",
                "channel_id": "channel-a",
                "thread_id": "th-1",
                "content_ref": "content-2",
            }
        )
    )
    asyncio.run(
        store.create_compat_mapping(
            {
                "mapping_id": "map-1",
                "origin": "discord",
                "entity_type": "message",
                "channel_id": "channel-a",
                "external_id": "42",
                "internal_id": "msg-1",
                "created_at": "2026-03-03T00:00:00+00:00",
            }
        )
    )
    asyncio.run(store.next_compat_sequence("discord", "channel-a"))

    deleted_channel = asyncio.run(store.delete_channel("channel-a"))

    assert deleted_channel == created_channel
    reloaded_store = FileMetadataStore(db_path)
    assert asyncio.run(reloaded_store.get_channel("channel-a")) is None
    assert asyncio.run(reloaded_store.get_message("msg-1")) is None
    assert asyncio.run(reloaded_store.get_message("msg-2")) is None
    assert asyncio.run(reloaded_store.get_thread("th-1")) is None
    assert (
        asyncio.run(reloaded_store.get_compat_mapping("discord", "message", "42", "channel-a"))
        is None
    )
    assert asyncio.run(reloaded_store.next_compat_sequence("discord", "channel-a")) == 1


async def _chunk_stream(chunks: list[bytes]):
    for chunk in chunks:
        yield chunk


def test_local_file_binary_store_saves_and_checks_files(tmp_path) -> None:
    store = LocalFileBinaryStore(tmp_path / "files")

    stored = asyncio.run(
        store.save(
            "fil-1",
            "hello.txt",
            _chunk_stream([b"hello", b"-world"]),
            max_size_bytes=64,
        )
    )

    assert stored["storage_backend"] == "local"
    assert stored["size_bytes"] == 11
    assert stored["sha256"]
    assert asyncio.run(store.exists(stored["storage_path"])) is True


def test_local_file_binary_store_enforces_size_limit(tmp_path) -> None:
    store = LocalFileBinaryStore(tmp_path / "files")

    try:
        asyncio.run(
            store.save(
                "fil-1",
                "large.txt",
                _chunk_stream([b"0123456789"]),
                max_size_bytes=5,
            )
        )
    except ValueError as exc:
        assert str(exc) == "file_too_large"
    else:
        raise AssertionError("Expected file_too_large error")
