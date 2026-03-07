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

    async def get_thread_by_root_message(self, root_message_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"""
            SELECT payload
            FROM {self._table("threads")}
            WHERE JSON_UNQUOTE(JSON_EXTRACT(payload, '$.root_message_id'))=%s
            LIMIT 1
            """,
            (root_message_id,),
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

    async def find_message_by_idempotency(
        self,
        channel_id: str,
        thread_id: str | None,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"""
            SELECT payload
            FROM {self._table("messages")}
            WHERE channel_id=%s
              AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$.idempotency_key'))=%s
              AND (
                (%s IS NULL AND JSON_EXTRACT(payload, '$.thread_id') IS NULL)
                OR JSON_UNQUOTE(JSON_EXTRACT(payload, '$.thread_id'))=%s
              )
            ORDER BY sequence_id ASC
            LIMIT 1
            """,
            (channel_id, idempotency_key, thread_id, thread_id),
        )
        return self._deserialize_row(row)

    async def create_file(self, file_object: dict[str, Any]) -> dict[str, Any]:
        file_id = str(file_object["file_id"])
        record = deepcopy(file_object)
        await self._run_write(
            f"""
            INSERT INTO {self._table("files")} (entity_id, payload)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload)
            """,
            (file_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_file(self, file_id: str) -> dict[str, Any] | None:
        row = await self._run_fetchone(
            f"SELECT payload FROM {self._table('files')} WHERE entity_id=%s",
            (file_id,),
        )
        return self._deserialize_row(row)

    async def create_compat_mapping(self, mapping: dict[str, Any]) -> dict[str, Any]:
        mapping_id = str(mapping["mapping_id"])
        origin = str(mapping["origin"])
        entity_type = str(mapping["entity_type"])
        external_id = str(mapping["external_id"])
        channel_id = mapping.get("channel_id")
        record = deepcopy(mapping)
        await self._run_write(
            f"""
            INSERT INTO {self._table("compat_mappings")}
                (mapping_id, origin, entity_type, channel_id, external_id, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE payload=VALUES(payload), mapping_id=VALUES(mapping_id)
            """,
            (mapping_id, origin, entity_type, channel_id, external_id, self._serialize(record)),
        )
        return deepcopy(record)

    async def get_compat_mapping(
        self,
        origin: str,
        entity_type: str,
        external_id: str,
        channel_id: str | None = None,
    ) -> dict[str, Any] | None:
        if channel_id is None:
            row = await self._run_fetchone(
                f"""
                SELECT payload
                FROM {self._table("compat_mappings")}
                WHERE origin=%s AND entity_type=%s AND channel_id IS NULL AND external_id=%s
                LIMIT 1
                """,
                (origin, entity_type, external_id),
            )
        else:
            row = await self._run_fetchone(
                f"""
                SELECT payload
                FROM {self._table("compat_mappings")}
                WHERE origin=%s AND entity_type=%s AND channel_id=%s AND external_id=%s
                LIMIT 1
                """,
                (origin, entity_type, channel_id, external_id),
            )
        return self._deserialize_row(row)

    async def next_compat_sequence(self, origin: str, channel_id: str) -> int:
        await asyncio.to_thread(self._ensure_schema)
        return await asyncio.to_thread(self._next_compat_sequence_sync, origin, channel_id)

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
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("files")} (
                entity_id VARCHAR(128) PRIMARY KEY,
                payload JSON NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("compat_mappings")} (
                mapping_id VARCHAR(128) PRIMARY KEY,
                origin VARCHAR(32) NOT NULL,
                entity_type VARCHAR(32) NOT NULL,
                channel_id VARCHAR(128) NULL,
                external_id VARCHAR(191) NOT NULL,
                payload JSON NOT NULL,
                UNIQUE KEY uniq_{self._table_prefix}_compat_lookup (origin, entity_type, channel_id, external_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """,
            f"""
            CREATE TABLE IF NOT EXISTS {self._table("compat_sequences")} (
                origin VARCHAR(32) NOT NULL,
                channel_id VARCHAR(128) NOT NULL,
                sequence_value BIGINT NOT NULL,
                PRIMARY KEY (origin, channel_id)
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

    def _next_compat_sequence_sync(self, origin: str, channel_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    INSERT INTO {self._table("compat_sequences")} (origin, channel_id, sequence_value)
                    VALUES (%s, %s, 1)
                    ON DUPLICATE KEY UPDATE sequence_value=LAST_INSERT_ID(sequence_value + 1)
                    """,
                    (origin, channel_id),
                )
                cursor.execute("SELECT LAST_INSERT_ID() AS sequence_value")
                row = cursor.fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("Failed to allocate compatibility sequence")
        return int(row["sequence_value"])

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
