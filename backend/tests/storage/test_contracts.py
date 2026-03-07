from __future__ import annotations

import asyncio
import json

import pytest

from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def set(self, key: str, value: str) -> bool:
        self.data[key] = value
        return True

    def get(self, key: str) -> str | None:
        return self.data.get(key)

    def delete(self, key: str) -> int:
        if key in self.data:
            del self.data[key]
            return 1
        return 0


class InMemoryMySQLMetadataStore(MySQLMetadataStore):
    def __init__(self) -> None:
        super().__init__("mysql+pymysql://app:app@localhost:3306/open_messenger")
        self._users: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._channels: dict[str, str] = {}
        self._threads: dict[str, str] = {}
        self._messages: dict[str, dict[str, object]] = {}
        self._files: dict[str, str] = {}
        self._compat_mappings: dict[tuple[str, str, str | None, str], str] = {}
        self._compat_sequences: dict[tuple[str, str], int] = {}
        self._schema_initialized = True
        self._sequence_id = 0

    def _ensure_schema(self) -> None:
        return

    def _run_write_sync(self, sql: str, params=()):
        normalized = " ".join(sql.lower().split())

        if "insert into" in normalized and self._table("users") in normalized:
            entity_id, payload = params
            self._users[str(entity_id)] = str(payload)
            return 1
        if "insert into" in normalized and self._table("tokens") in normalized:
            entity_id, payload = params
            self._tokens[str(entity_id)] = str(payload)
            return 1
        if "update" in normalized and self._table("tokens") in normalized:
            payload, entity_id = params
            if str(entity_id) in self._tokens:
                self._tokens[str(entity_id)] = str(payload)
                return 1
            return 0
        if "insert into" in normalized and self._table("channels") in normalized:
            entity_id, payload = params
            self._channels[str(entity_id)] = str(payload)
            return 1
        if "delete from" in normalized and self._table("channels") in normalized:
            entity_id = str(params[0])
            existed = entity_id in self._channels
            self._channels.pop(entity_id, None)
            return 1 if existed else 0
        if "insert into" in normalized and self._table("threads") in normalized:
            entity_id, payload = params
            self._threads[str(entity_id)] = str(payload)
            return 1
        if "update" in normalized and self._table("threads") in normalized:
            payload, entity_id = params
            if str(entity_id) in self._threads:
                self._threads[str(entity_id)] = str(payload)
                return 1
            return 0
        if "delete from" in normalized and self._table("threads") in normalized:
            if "root_message_id" in normalized:
                root_message_id = str(params[0])
                thread_ids = [
                    thread_id
                    for thread_id, payload in self._threads.items()
                    if str(json.loads(payload).get("root_message_id")) == root_message_id
                ]
            else:
                channel_id = str(params[0])
                thread_ids = [
                    thread_id
                    for thread_id, payload in self._threads.items()
                    if str(json.loads(payload).get("channel_id")) == channel_id
                ]
            for thread_id in thread_ids:
                self._threads.pop(thread_id, None)
            return len(thread_ids)
        if "insert into" in normalized and self._table("messages") in normalized:
            message_id, channel_id, payload = params
            existing = self._messages.get(str(message_id))
            if existing is None:
                self._sequence_id += 1
                self._messages[str(message_id)] = {
                    "sequence_id": self._sequence_id,
                    "message_id": str(message_id),
                    "channel_id": str(channel_id),
                    "payload": str(payload),
                }
            else:
                existing["channel_id"] = str(channel_id)
                existing["payload"] = str(payload)
            return 1
        if "delete from" in normalized and self._table("messages") in normalized:
            channel_id = str(params[0])
            message_ids = [
                message_id
                for message_id, row in self._messages.items()
                if str(row["channel_id"]) == channel_id
            ]
            for message_id in message_ids:
                self._messages.pop(message_id, None)
            return len(message_ids)
        if "insert into" in normalized and self._table("files") in normalized:
            entity_id, payload = params
            self._files[str(entity_id)] = str(payload)
            return 1
        if "insert into" in normalized and self._table("compat_mappings") in normalized:
            mapping_id, origin, entity_type, channel_id, external_id, payload = params
            del mapping_id
            self._compat_mappings[(str(origin), str(entity_type), channel_id, str(external_id))] = str(
                payload
            )
            return 1
        if "delete from" in normalized and self._table("compat_mappings") in normalized:
            channel_id = str(params[0])
            mapping_keys = [key for key in self._compat_mappings if key[2] == channel_id]
            for key in mapping_keys:
                self._compat_mappings.pop(key, None)
            return len(mapping_keys)
        if "delete from" in normalized and self._table("compat_sequences") in normalized:
            channel_id = str(params[0])
            sequence_keys = [key for key in self._compat_sequences if key[1] == channel_id]
            for key in sequence_keys:
                self._compat_sequences.pop(key, None)
            return len(sequence_keys)
        return 0

    def _run_fetchone_sync(self, sql: str, params=()):
        normalized = " ".join(sql.lower().split())

        if "from" in normalized and self._table("users") in normalized:
            payload = self._users.get(str(params[0]))
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("tokens") in normalized:
            payload = self._tokens.get(str(params[0]))
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("channels") in normalized:
            payload = self._channels.get(str(params[0]))
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("threads") in normalized:
            if "root_message_id" in normalized:
                root_message_id = str(params[0])
                for payload in self._threads.values():
                    decoded = json.loads(payload)
                    if str(decoded.get("root_message_id")) == root_message_id:
                        return {"payload": payload}
                return None
            payload = self._threads.get(str(params[0]))
            return {"payload": payload} if payload is not None else None
        if (
            "from" in normalized
            and self._table("messages") in normalized
            and "idempotency_key" in normalized
        ):
            channel_id = str(params[0])
            idempotency_key = str(params[1])
            thread_id = params[2]
            ordered = sorted(self._messages.values(), key=lambda item: int(item["sequence_id"]))
            for row in ordered:
                if str(row["channel_id"]) != channel_id:
                    continue
                payload = json.loads(str(row["payload"]))
                if payload.get("idempotency_key") != idempotency_key:
                    continue
                if payload.get("thread_id") != thread_id:
                    continue
                return {"payload": row["payload"]}
            return None
        if (
            "from" in normalized
            and self._table("messages") in normalized
            and "message_id=%s" in normalized
            and "channel_id=%s" not in normalized
        ):
            row = self._messages.get(str(params[0]))
            return {"payload": row["payload"]} if row is not None else None
        if (
            "from" in normalized
            and self._table("messages") in normalized
            and "channel_id=%s and message_id=%s" in normalized
        ):
            channel_id = str(params[0])
            message_id = str(params[1])
            row = self._messages.get(message_id)
            if row is None or str(row["channel_id"]) != channel_id:
                return None
            return {"sequence_id": int(row["sequence_id"])}
        if "from" in normalized and self._table("files") in normalized:
            payload = self._files.get(str(params[0]))
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("compat_mappings") in normalized:
            if "channel_id is null" in normalized:
                origin, entity_type, external_id = params
                payload = self._compat_mappings.get((str(origin), str(entity_type), None, str(external_id)))
            else:
                origin, entity_type, channel_id, external_id = params
                payload = self._compat_mappings.get(
                    (str(origin), str(entity_type), str(channel_id), str(external_id))
                )
            return {"payload": payload} if payload is not None else None
        return None

    def _run_fetchall_sync(self, sql: str, params=()):
        normalized = " ".join(sql.lower().split())
        if "from" not in normalized or self._table("messages") not in normalized:
            return []

        ordered = sorted(self._messages.values(), key=lambda item: int(item["sequence_id"]))
        if "thread_id" in normalized:
            channel_id = str(params[0])
            thread_id = str(params[1])
            limit = int(params[2])
            selected = []
            for row in ordered:
                if str(row["channel_id"]) != channel_id:
                    continue
                payload = json.loads(str(row["payload"]))
                if payload.get("thread_id") != thread_id:
                    continue
                selected.append({"payload": row["payload"]})
            return selected[:limit]
        if "sequence_id>%s" in normalized:
            channel_id = str(params[0])
            sequence_id = int(params[1])
            limit = int(params[2])
            selected = [
                {"payload": row["payload"]}
                for row in ordered
                if str(row["channel_id"]) == channel_id and int(row["sequence_id"]) > sequence_id
            ]
            return selected[:limit]
        if len(params) == 1:
            channel_id = str(params[0])
            return [
                {"payload": row["payload"]}
                for row in ordered
                if str(row["channel_id"]) == channel_id
            ]

        channel_id = str(params[0])
        limit = int(params[1])
        selected = [
            {"payload": row["payload"]}
            for row in ordered
            if str(row["channel_id"]) == channel_id
        ]
        return selected[:limit]

    def _next_compat_sequence_sync(self, origin: str, channel_id: str) -> int:
        key = (origin, channel_id)
        value = self._compat_sequences.get(key, 0) + 1
        self._compat_sequences[key] = value
        return value


@pytest.fixture(params=["memory", "file", "redis"])
def content_store(request, tmp_path):
    if request.param == "memory":
        return InMemoryMessageContentStore()
    if request.param == "file":
        return FileMessageContentStore(tmp_path / "content")
    return RedisMessageContentStore(
        redis_url="redis://unused",
        key_prefix=f"test:{request.node.name}",
        client=FakeRedis(),
    )


@pytest.fixture(params=["memory", "file", "mysql"])
def metadata_store(request, tmp_path):
    if request.param == "memory":
        return InMemoryMetadataStore()
    if request.param == "file":
        return FileMetadataStore(tmp_path / "metadata.json")
    return InMemoryMySQLMetadataStore()


def test_message_content_store_contract(content_store) -> None:
    asyncio.run(
        content_store.put(
            "content-1",
            {"text": "hello", "metadata": {"mentions": ["usr_1"]}},
        )
    )

    loaded = asyncio.run(content_store.get("content-1"))

    assert loaded == {"text": "hello", "metadata": {"mentions": ["usr_1"]}}
    assert loaded is not None

    loaded["metadata"]["mentions"].append("usr_2")
    reloaded = asyncio.run(content_store.get("content-1"))
    assert reloaded == {"text": "hello", "metadata": {"mentions": ["usr_1"]}}

    asyncio.run(content_store.delete("content-1"))
    assert asyncio.run(content_store.get("content-1")) is None


def test_metadata_store_entity_and_pagination_contract(metadata_store) -> None:
    user = asyncio.run(
        metadata_store.create_user(
            {
                "user_id": "usr-1",
                "username": "alice",
                "display_name": "Alice",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )
    token = asyncio.run(
        metadata_store.create_token(
            {
                "token_id": "tok-1",
                "user_id": "usr-1",
                "token_type": "user_token",
                "scopes": ["messages:write"],
                "token_hash": "hash-1",
                "created_at": "2026-03-03T00:00:00Z",
                "revoked_at": None,
            }
        )
    )
    channel = asyncio.run(
        metadata_store.create_channel(
            {"channel_id": "channel-a", "name": "general", "created_at": "2026-03-03T00:00:00Z"}
        )
    )
    thread = asyncio.run(
        metadata_store.create_thread(
            {
                "thread_id": "th-1",
                "channel_id": "channel-a",
                "root_message_id": "msg-root",
                "reply_count": 0,
                "last_message_at": "2026-03-03T00:00:00Z",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )

    root_message = asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-root",
                "channel_id": "channel-a",
                "thread_id": None,
                "content_ref": "content-root",
            }
        )
    )
    thread_message = asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-thread-1",
                "channel_id": "channel-a",
                "thread_id": "th-1",
                "content_ref": "content-thread-1",
            }
        )
    )
    asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-thread-2",
                "channel_id": "channel-a",
                "thread_id": "th-1",
                "content_ref": "content-thread-2",
            }
        )
    )

    updated_token = asyncio.run(
        metadata_store.update_token("tok-1", {"revoked_at": "2026-03-03T01:00:00Z"})
    )
    updated_thread = asyncio.run(
        metadata_store.update_thread(
            "th-1",
            {"reply_count": 2, "last_message_at": "2026-03-03T02:00:00Z"},
        )
    )

    page1 = asyncio.run(metadata_store.list_channel_messages("channel-a", cursor=None, limit=2))
    page2 = asyncio.run(
        metadata_store.list_channel_messages("channel-a", cursor=page1[-1]["message_id"], limit=2)
    )
    reset_page = asyncio.run(
        metadata_store.list_channel_messages("channel-a", cursor="msg-missing", limit=1)
    )
    thread_page = asyncio.run(metadata_store.list_thread_messages("channel-a", "th-1", limit=10))

    assert asyncio.run(metadata_store.get_user("usr-1")) == user
    stored_token = asyncio.run(metadata_store.get_token("tok-1"))
    assert stored_token is not None
    assert stored_token["token_id"] == token["token_id"]
    assert stored_token["revoked_at"] == "2026-03-03T01:00:00Z"
    assert updated_token is not None
    assert updated_token["revoked_at"] == "2026-03-03T01:00:00Z"
    assert asyncio.run(metadata_store.get_channel("channel-a")) == channel
    stored_thread = asyncio.run(metadata_store.get_thread("th-1"))
    assert stored_thread is not None
    assert stored_thread["thread_id"] == thread["thread_id"]
    assert stored_thread["reply_count"] == 2
    assert stored_thread["last_message_at"] == "2026-03-03T02:00:00Z"
    assert updated_thread is not None
    assert updated_thread["reply_count"] == 2
    assert asyncio.run(metadata_store.get_thread_by_root_message("msg-root")) == updated_thread
    assert asyncio.run(metadata_store.get_message("msg-root")) == root_message
    assert asyncio.run(metadata_store.get_message("msg-thread-1")) == thread_message
    assert [item["message_id"] for item in page1] == ["msg-root", "msg-thread-1"]
    assert [item["message_id"] for item in page2] == ["msg-thread-2"]
    assert [item["message_id"] for item in reset_page] == ["msg-root"]
    assert [item["message_id"] for item in thread_page] == ["msg-thread-1", "msg-thread-2"]


def test_metadata_store_idempotency_file_and_compat_contract(metadata_store) -> None:
    asyncio.run(metadata_store.create_channel({"channel_id": "channel-a", "name": "general"}))
    asyncio.run(metadata_store.create_channel({"channel_id": "channel-b", "name": "random"}))

    channel_message = asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-idemp-channel",
                "channel_id": "channel-a",
                "thread_id": None,
                "content_ref": "content-a",
                "idempotency_key": "req-1",
            }
        )
    )
    thread_message = asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-idemp-thread",
                "channel_id": "channel-a",
                "thread_id": "th-1",
                "content_ref": "content-b",
                "idempotency_key": "req-1",
            }
        )
    )

    created_file = asyncio.run(
        metadata_store.create_file(
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
    channel_mapping = asyncio.run(
        metadata_store.create_compat_mapping(
            {
                "mapping_id": "map-1",
                "origin": "slack",
                "entity_type": "message",
                "channel_id": "channel-a",
                "external_id": "1710000000.000001",
                "internal_id": "msg-idemp-channel",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )
    global_mapping = asyncio.run(
        metadata_store.create_compat_mapping(
            {
                "mapping_id": "map-2",
                "origin": "telegram",
                "entity_type": "bot",
                "channel_id": None,
                "external_id": "bot-1",
                "internal_id": "usr-1",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )

    assert (
        asyncio.run(metadata_store.find_message_by_idempotency("channel-a", None, "req-1"))
        == channel_message
    )
    assert (
        asyncio.run(metadata_store.find_message_by_idempotency("channel-a", "th-1", "req-1"))
        == thread_message
    )
    assert asyncio.run(metadata_store.find_message_by_idempotency("channel-b", None, "req-1")) is None
    assert asyncio.run(metadata_store.get_file("fil-1")) == created_file
    assert (
        asyncio.run(
            metadata_store.get_compat_mapping("slack", "message", "1710000000.000001", "channel-a")
        )
        == channel_mapping
    )
    assert asyncio.run(metadata_store.get_compat_mapping("telegram", "bot", "bot-1")) == global_mapping
    assert asyncio.run(metadata_store.next_compat_sequence("discord", "channel-a")) == 1
    assert asyncio.run(metadata_store.next_compat_sequence("discord", "channel-a")) == 2
    assert asyncio.run(metadata_store.next_compat_sequence("discord", "channel-b")) == 1


def test_metadata_store_delete_channel_contract(metadata_store) -> None:
    created_channel = asyncio.run(
        metadata_store.create_channel(
            {"channel_id": "channel-a", "name": "general", "created_at": "2026-03-03T00:00:00Z"}
        )
    )
    asyncio.run(
        metadata_store.create_thread(
            {
                "thread_id": "th-1",
                "channel_id": "channel-a",
                "root_message_id": "msg-root",
                "reply_count": 1,
                "last_message_at": "2026-03-03T00:00:00Z",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )
    asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-root",
                "channel_id": "channel-a",
                "thread_id": None,
                "content_ref": "content-root",
            }
        )
    )
    asyncio.run(
        metadata_store.create_message(
            {
                "message_id": "msg-reply",
                "channel_id": "channel-a",
                "thread_id": "th-1",
                "content_ref": "content-reply",
            }
        )
    )
    asyncio.run(
        metadata_store.create_compat_mapping(
            {
                "mapping_id": "map-1",
                "origin": "discord",
                "entity_type": "message",
                "channel_id": "channel-a",
                "external_id": "42",
                "internal_id": "msg-root",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )
    asyncio.run(metadata_store.next_compat_sequence("discord", "channel-a"))

    deleted_channel = asyncio.run(metadata_store.delete_channel("channel-a"))

    assert deleted_channel == created_channel
    assert asyncio.run(metadata_store.get_channel("channel-a")) is None
    assert asyncio.run(metadata_store.get_message("msg-root")) is None
    assert asyncio.run(metadata_store.get_message("msg-reply")) is None
    assert asyncio.run(metadata_store.get_thread("th-1")) is None
    assert asyncio.run(metadata_store.get_thread_by_root_message("msg-root")) is None
    assert asyncio.run(metadata_store.list_channel_messages("channel-a", cursor=None, limit=10)) == []
    assert (
        asyncio.run(metadata_store.get_compat_mapping("discord", "message", "42", "channel-a"))
        is None
    )
    assert asyncio.run(metadata_store.next_compat_sequence("discord", "channel-a")) == 1
    assert asyncio.run(metadata_store.delete_channel("channel-a")) is None
