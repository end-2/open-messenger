from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any
from urllib.parse import unquote, urlparse

import pymysql
from pymysql.cursors import DictCursor

from app.storage.interfaces import MetadataStore


@dataclass(frozen=True)
class _MySQLConnectionSettings:
    host: str
    port: int
    user: str
    password: str
    database: str


def _parse_mysql_dsn(dsn: str) -> _MySQLConnectionSettings:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("MySQL DSN must use mysql:// or mysql+pymysql:// scheme")

    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("MySQL DSN must include host and database name")

    return _MySQLConnectionSettings(
        host=parsed.hostname,
        port=int(parsed.port or 3306),
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
    )


class MySQLMetadataStore(MetadataStore):
    """MySQL implementation for metadata entities."""

    def __init__(
        self,
        dsn: str,
        table_prefix: str = "open_messenger",
    ) -> None:
        self._settings = _parse_mysql_dsn(dsn)
        self._table_prefix = table_prefix
        self._schema_initialized = False
        self._schema_lock = Lock()

    async def create_user(self, user: dict[str, Any]) -> dict[str, Any]:
        user_id = str(user["user_id"])
        record = deepcopy(user)
        await self._run_write(
            f"""
            INSERT INTO {self._table("users")} (entity_id, payload)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (user_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_user(self, user_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('users')} WHERE entity_id=%s",
            (user_id,),
        )
        return self._deserialize_row(row)

    async def create_token(self, token: dict[str, Any]) -> dict[str, Any]:
        token_id = str(token["token_id"])
        record = deepcopy(token)
        await self._run_write(
            f"""
            INSERT INTO {self._table("tokens")} (entity_id, payload)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (token_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_token(self, token_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('tokens')} WHERE entity_id=%s",
            (token_id,),
        )
        return self._deserialize_row(row)

    async def update_token(self, token_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = await self.get_token(token_id)
        if current is None:
            return None

        current.update(deepcopy(patch))
        await self._run_write(
            f"UPDATE {self._table('tokens')} SET payload=%s WHERE entity_id=%s",
            (self._serialize(current), token_id),
        )
        return deepcopy(current)

    async def create_channel(self, channel: dict[str, Any]) -> dict[str, Any]:
        channel_id = str(channel["channel_id"])
        record = deepcopy(channel)
        await self._run_write(
            f"""
            INSERT INTO {self._table("channels")} (entity_id, payload)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (channel_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_channel(self, channel_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('channels')} WHERE entity_id=%s",
            (channel_id,),
        )
        return self._deserialize_row(row)

    async def create_thread(self, thread: dict[str, Any]) -> dict[str, Any]:
        thread_id = str(thread["thread_id"])
        record = deepcopy(thread)
        await self._run_write(
            f"""
            INSERT INTO {self._table("threads")} (entity_id, payload)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (thread_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_thread(self, thread_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('threads')} WHERE entity_id=%s",
            (thread_id,),
        )
        return self._deserialize_row(row)

    async def update_thread(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        current = await self.get_thread(thread_id)
        if current is None:
            return None

        current.update(deepcopy(patch))
        await self._run_write(
            f"UPDATE {self._table('threads')} SET payload=%s WHERE entity_id=%s",
            (self._serialize(current), thread_id),
        )
        return deepcopy(current)

    async def create_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        message_id = str(msg["message_id"])
        channel_id = str(msg["channel_id"])
        record = deepcopy(msg)
        await self._run_write(
            f"""
            INSERT INTO {self._table("messages")} (message_id, channel_id, payload)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE channel_id=VALUES(channel_id), payload=VALUES(payload)
            """,
            (message_id, channel_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_message(self, message_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('messages')} WHERE message_id=%s",
            (message_id,),
        )
        return self._deserialize_row(row)

    async def list_channel_messages(
        self,
        channel_id: str,
        cursor: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized_limit = max(limit, 0)
        params: tuple[Any, ...]
        sql: str

        if cursor:
            cursor_row = await self._run_fetchone(
                f"""
                SELECT sequence_id
                FROM {self._table("messages")}
                WHERE channel_id=%s AND message_id=%s
                """,
                (channel_id, cursor),
            )
            if cursor_row is None:
                cursor = None
            else:
                sql = (
                    f"SELECT payload FROM {self._table('messages')} "
                    "WHERE channel_id=%s AND sequence_id>%s "
                    "ORDER BY sequence_id ASC LIMIT %s"
                )
                params = (channel_id, int(cursor_row["sequence_id"]), normalized_limit)
                rows = await self._run_fetchall(sql, params)
                items: list[dict[str, Any]] = []
                for row in rows:
                    payload = self._deserialize_row(row)
                    if payload is not None:
                        items.append(payload)
                return items

        sql = (
            f"SELECT payload FROM {self._table('messages')} "
            "WHERE channel_id=%s ORDER BY sequence_id ASC LIMIT %s"
        )
        params = (channel_id, normalized_limit)
        rows = await self._run_fetchall(sql, params)
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = self._deserialize_row(row)
            if payload is not None:
                items.append(payload)
        return items

    def _initialize(self) -> None:
        for statement in self._schema_statements():
            self._run_write_sync(statement)

    def _schema_statements(self) -> list[str]:
        return [
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("users")} (
                entity_id VARCHAR(128) PRIMARY KEY,
                payload JSON NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("tokens")} (
                entity_id VARCHAR(128) PRIMARY KEY,
                payload JSON NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("channels")} (
                entity_id VARCHAR(128) PRIMARY KEY,
                payload JSON NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("threads")} (
                entity_id VARCHAR(128) PRIMARY KEY,
                payload JSON NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("messages")} (
                sequence_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                message_id VARCHAR(128) NOT NULL UNIQUE,
                channel_id VARCHAR(128) NOT NULL,
                payload JSON NOT NULL,
                INDEX idx_{self._table_prefix}_messages_channel_sequence (channel_id, sequence_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
        ]

    def _table(self, suffix: str) -> str:
        return f"{self._table_prefix}_{suffix}"

    async def _run_write(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        await asyncio.to_thread(self._ensure_schema)
        return await asyncio.to_thread(self._run_write_sync, sql, params)

    async def _run_fetchone(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        await asyncio.to_thread(self._ensure_schema)
        return await asyncio.to_thread(self._run_fetchone_sync, sql, params)

    async def _run_fetchall(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        await asyncio.to_thread(self._ensure_schema)
        return await asyncio.to_thread(self._run_fetchall_sync, sql, params)

    def _ensure_schema(self) -> None:
        if self._schema_initialized:
            return
        with self._schema_lock:
            if self._schema_initialized:
                return
            self._initialize()
            self._schema_initialized = True

    def _run_write_sync(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, params)
            conn.commit()
        return int(affected)

    def _run_fetchone_sync(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        return row

    def _run_fetchall_sync(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                rows = cursor.fetchall()
        return list(rows)

    def _connect(self):
        return pymysql.connect(
            host=self._settings.host,
            port=self._settings.port,
            user=self._settings.user,
            password=self._settings.password,
            database=self._settings.database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=False,
        )

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))

    @staticmethod
    def _deserialize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if row is None:
            return None

        payload = row.get("payload")
        if isinstance(payload, dict):
            return deepcopy(payload)
        if isinstance(payload, bytes):
            return json.loads(payload.decode("utf-8"))
        if isinstance(payload, str):
            return json.loads(payload)
        return None
