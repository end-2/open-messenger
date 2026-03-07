from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any

from app.storage.interfaces import MessageContentStore, MetadataStore


class FileMessageContentStore(MessageContentStore):
    """Filesystem implementation for message body content."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, content_id: str, payload: dict[str, Any]) -> None:
        destination = self._content_path(content_id)
        self._write_json_atomic(destination, deepcopy(payload))

    async def get(self, content_id: str) -> dict[str, Any] | None:
        source = self._content_path(content_id)
        if not source.exists():
            return None
        return self._read_json(source)

    async def delete(self, content_id: str) -> None:
        self._content_path(content_id).unlink(missing_ok=True)

    def _content_path(self, content_id: str) -> Path:
        digest = hashlib.sha256(content_id.encode("utf-8")).hexdigest()
        return self._base_dir / f"{digest}.json"

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    @staticmethod
    def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
        tmp_path = path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=True, separators=(",", ":"))
        tmp_path.replace(path)


class FileMetadataStore(MetadataStore):
    """Filesystem implementation for metadata entities."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._initialize()

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = str(user["user_id"])
        record = deepcopy(user)

        with self._lock:
            database = self._read_database()
            database["users"][user_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["users"].get(user_id)
        if record is None:
            return None
        return deepcopy(record)

    async def create_token(self, token: dict[str, Any]) -> dict[str, Any]:
        token_id = str(token["token_id"])
        record = deepcopy(token)

        with self._lock:
            database = self._read_database()
            database["tokens"][token_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def get_token(self, token_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["tokens"].get(token_id)
        if record is None:
            return None
        return deepcopy(record)

    async def update_token(self, token_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["tokens"].get(token_id)
            if record is None:
                return None
            record.update(deepcopy(patch))
            database["tokens"][token_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel["channel_id"])
        record = deepcopy(channel)

        with self._lock:
            database = self._read_database()
            database["channels"][channel_id] = record
            database["channel_index"].setdefault(channel_id, [])
            self._write_database(database)
        return deepcopy(record)

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["channels"].get(channel_id)
        if record is None:
            return None
        return deepcopy(record)

    async def create_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        thread_id = str(thread["thread_id"])
        record = deepcopy(thread)

        with self._lock:
            database = self._read_database()
            database["threads"][thread_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["threads"].get(thread_id)
        if record is None:
            return None
        return deepcopy(record)

    async def get_thread_by_root_message(self, root_message_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            for thread in database["threads"].values():
                if str(thread.get("root_message_id")) == root_message_id:
                    return deepcopy(thread)
        return None

    async def update_thread(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["threads"].get(thread_id)
            if record is None:
                return None
            record.update(deepcopy(patch))
            database["threads"][thread_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def create_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        message_id = str(msg["message_id"])
        channel_id = str(msg["channel_id"])
        record = deepcopy(msg)

        with self._lock:
            database = self._read_database()
            database["messages"][message_id] = record
            database["channel_index"].setdefault(channel_id, []).append(message_id)
            self._write_database(database)
        return deepcopy(record)

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["messages"].get(message_id)
        if record is None:
            return None
        return deepcopy(record)

    async def list_channel_messages(
        self,
        channel_id: str,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._lock:
            database = self._read_database()
            message_ids = database["channel_index"].get(channel_id, [])
            start_idx = 0
            if cursor:
                try:
                    start_idx = message_ids.index(cursor) + 1
                except ValueError:
                    start_idx = 0

            selected_ids = message_ids[start_idx : start_idx + max(limit, 0)]
            records = [deepcopy(database["messages"][msg_id]) for msg_id in selected_ids]
        return records

    async def find_message_by_idempotency(
        self,
        channel_id: str,
        thread_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            for message_id in database["channel_index"].get(channel_id, []):
                record = database["messages"][message_id]
                if (
                    record.get("idempotency_key") == idempotency_key
                    and record.get("thread_id") == thread_id
                ):
                    return deepcopy(record)
        return None

    async def create_file(self, file_object: dict[str, Any]) -> dict[str, Any]:
        file_id = str(file_object["file_id"])
        record = deepcopy(file_object)

        with self._lock:
            database = self._read_database()
            database["files"][file_id] = record
            self._write_database(database)
        return deepcopy(record)

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        with self._lock:
            database = self._read_database()
            record = database["files"].get(file_id)
        if record is None:
            return None
        return deepcopy(record)

    async def create_compat_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        origin = str(mapping["origin"])
        entity_type = str(mapping["entity_type"])
        external_id = str(mapping["external_id"])
        channel_id = mapping.get("channel_id")
        record = deepcopy(mapping)
        key = self._compat_key(origin, entity_type, external_id, channel_id)

        with self._lock:
            database = self._read_database()
            database["compat_mappings"][key] = record
            self._write_database(database)
        return deepcopy(record)

    async def get_compat_mapping(
        self,
        origin: str,
        entity_type: str,
        external_id: str,
        channel_id: str | None = None,
    ) -> dict[str, Any] | None:
        key = self._compat_key(origin, entity_type, external_id, channel_id)
        with self._lock:
            database = self._read_database()
            record = database["compat_mappings"].get(key)
        if record is None:
            return None
        return deepcopy(record)

    async def next_compat_sequence(self, origin: str, channel_id: str) -> int:
        key = f"{origin}:{channel_id}"
        with self._lock:
            database = self._read_database()
            current = int(database["compat_sequences"].get(key, 0)) + 1
            database["compat_sequences"][key] = current
            self._write_database(database)
        return current

    def _initialize(self) -> None:
        if self._db_path.exists():
            return
        empty_db: dict[str, Any] = {
            "users": {},
            "tokens": {},
            "channels": {},
            "threads": {},
            "messages": {},
            "files": {},
            "channel_index": {},
            "compat_mappings": {},
            "compat_sequences": {},
        }
        self._write_database(empty_db)

    def _read_database(self) -> dict[str, Any]:
        with self._db_path.open("r", encoding="utf-8") as fp:
            database = json.load(fp)
        database.setdefault("users", {})
        database.setdefault("tokens", {})
        database.setdefault("channels", {})
        database.setdefault("threads", {})
        database.setdefault("messages", {})
        database.setdefault("files", {})
        database.setdefault("channel_index", {})
        database.setdefault("compat_mappings", {})
        database.setdefault("compat_sequences", {})
        return database

    def _write_database(self, payload: dict[str, Any]) -> None:
        tmp_path = self._db_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=True, separators=(",", ":"))
        tmp_path.replace(self._db_path)

    @staticmethod
    def _compat_key(
        origin: str,
        entity_type: str,
        external_id: str,
        channel_id: str | None,
    ) -> str:
        normalized_channel_id = channel_id if channel_id is not None else "*"
        return f"{origin}:{entity_type}:{normalized_channel_id}:{external_id}"
