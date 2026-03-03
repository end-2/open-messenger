import asyncio
import json

import pytest

from app.storage.mysql_store import MySQLMetadataStore, _parse_mysql_dsn


class InMemoryMySQLMetadataStore(MySQLMetadataStore):
    def __init__(self) -> None:
        super().__init__("mysql+pymysql://app:app@localhost:3306/open_messenger")
        self._users: dict[str, str] = {}
        self._tokens: dict[str, str] = {}
        self._channels: dict[str, str] = {}
        self._threads: dict[str, str] = {}
        self._messages: dict[str, dict[str, object]] = {}
        self._files: dict[str, str] = {}
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
        if "insert into" in normalized and self._table("files") in normalized:
            entity_id, payload = params
            self._files[str(entity_id)] = str(payload)
            return 1
        return 0

    def _run_fetchone_sync(self, sql: str, params=()):
        normalized = " ".join(sql.lower().split())

        if "from" in normalized and self._table("users") in normalized:
            entity_id = str(params[0])
            payload = self._users.get(entity_id)
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("tokens") in normalized:
            entity_id = str(params[0])
            payload = self._tokens.get(entity_id)
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("channels") in normalized:
            entity_id = str(params[0])
            payload = self._channels.get(entity_id)
            return {"payload": payload} if payload is not None else None
        if "from" in normalized and self._table("threads") in normalized:
            entity_id = str(params[0])
            payload = self._threads.get(entity_id)
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
            message_id = str(params[0])
            row = self._messages.get(message_id)
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
            entity_id = str(params[0])
            payload = self._files.get(entity_id)
            return {"payload": payload} if payload is not None else None
        return None

    def _run_fetchall_sync(self, sql: str, params=()):
        normalized = " ".join(sql.lower().split())
        if "from" not in normalized or self._table("messages") not in normalized:
            return []

        ordered = sorted(self._messages.values(), key=lambda item: int(item["sequence_id"]))
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

        channel_id = str(params[0])
        limit = int(params[1])
        selected = [
            {"payload": row["payload"]}
            for row in ordered
            if str(row["channel_id"]) == channel_id
        ]
        return selected[:limit]


def test_parse_mysql_dsn_success() -> None:
    settings = _parse_mysql_dsn("mysql+pymysql://app:pass@localhost:3306/open_messenger")

    assert settings.host == "localhost"
    assert settings.port == 3306
    assert settings.user == "app"
    assert settings.password == "pass"
    assert settings.database == "open_messenger"


def test_parse_mysql_dsn_rejects_invalid_scheme() -> None:
    with pytest.raises(ValueError):
        _parse_mysql_dsn("postgresql://app:pass@localhost:5432/open_messenger")


def test_mysql_metadata_store_contract_with_in_memory_backend() -> None:
    store = InMemoryMySQLMetadataStore()

    user = asyncio.run(
        store.create_user(
            {
                "user_id": "usr-1",
                "username": "alice",
                "display_name": "Alice",
                "created_at": "2026-03-03T00:00:00Z",
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
                "created_at": "2026-03-03T00:00:00Z",
                "revoked_at": None,
            }
        )
    )
    assert asyncio.run(store.get_token("tok-1")) == token
    updated_token = asyncio.run(store.update_token("tok-1", {"revoked_at": "2026-03-03T01:00:00Z"}))
    assert updated_token is not None
    assert updated_token["revoked_at"] == "2026-03-03T01:00:00Z"

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
                "last_message_at": "2026-03-03T00:00:00Z",
                "created_at": "2026-03-03T00:00:00Z",
            }
        )
    )
    assert asyncio.run(store.get_thread("th-1")) == thread
    updated_thread = asyncio.run(
        store.update_thread(
            "th-1",
            {"reply_count": 2, "last_message_at": "2026-03-03T02:00:00Z"},
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
    page2 = asyncio.run(store.list_channel_messages("channel-a", cursor=page1[-1]["message_id"], limit=2))

    assert page1 == [
        {"message_id": "msg-1", "channel_id": "channel-a", "content_ref": "content-1"},
        {"message_id": "msg-2", "channel_id": "channel-a", "content_ref": "content-2"},
    ]
    assert page2 == [{"message_id": "msg-3", "channel_id": "channel-a", "content_ref": "content-3"}]
    assert asyncio.run(store.get_message(m1["message_id"])) == m1

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
                "storage_path": "/tmp/hello.txt",
                "sha256": "abc123",
            }
        )
    )
    assert asyncio.run(store.get_file("fil-1")) == created_file


def test_mysql_metadata_store_serialization_roundtrip() -> None:
    payload = {"a": 1, "nested": {"b": 2}}

    encoded = MySQLMetadataStore._serialize(payload)
    decoded = MySQLMetadataStore._deserialize_row({"payload": encoded})

    assert json.loads(encoded) == payload
    assert decoded == payload
