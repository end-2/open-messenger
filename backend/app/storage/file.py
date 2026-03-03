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

    def _initialize(self) -> None:
        if self._db_path.exists():
            return
        empty_db: dict[str, Any] = {
            "users": {},
            "tokens": {},
            "channels": {},
            "threads": {},
            "messages": {},
            "channel_index": {},
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
        database.setdefault("channel_index", {})
        return database

    def _write_database(self, payload: dict[str, Any]) -> None:
        tmp_path = self._db_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, ensure_ascii=True, separators=(",", ":"))
        tmp_path.replace(self._db_path)
