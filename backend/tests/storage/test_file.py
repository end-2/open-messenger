import asyncio

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

    asyncio.run(store.create_channel({"channel_id": "channel-a", "name": "general"}))
    assert asyncio.run(store.get_channel("channel-a")) == {
        "channel_id": "channel-a",
        "name": "general",
    }

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

    assert db_path.exists()
    assert page1 == [
        {"message_id": "msg-1", "channel_id": "channel-a", "content_ref": "content-1"},
        {"message_id": "msg-2", "channel_id": "channel-a", "content_ref": "content-2"},
    ]
    assert page2 == [
        {"message_id": "msg-3", "channel_id": "channel-a", "content_ref": "content-3"}
    ]

    reloaded_store = FileMetadataStore(db_path)
    assert asyncio.run(reloaded_store.get_channel("channel-a")) == {
        "channel_id": "channel-a",
        "name": "general",
    }
    assert asyncio.run(reloaded_store.get_message(m1["message_id"])) == m1
