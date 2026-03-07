from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import unquote, urlparse

import pymysql
from pymysql.cursors import DictCursor
from redis import Redis


@dataclass(frozen=True)
class StorageVerificationConfig:
    redis_url: str
    redis_key_prefix: str
    mysql_dsn: str
    mysql_table_prefix: str


@dataclass(frozen=True)
class NativeApiStorageArtifacts:
    user_id: str
    channel_id: str
    thread_id: str
    root_message_id: str
    root_content_ref: str
    reply_message_id: str
    reply_content_ref: str
    file_id: str
    root_idempotency_key: str
    reply_idempotency_key: str


@dataclass(frozen=True)
class NativeApiStorageSnapshot:
    user_payload: dict[str, Any] | None
    channel_payload: dict[str, Any] | None
    thread_payload: dict[str, Any] | None
    root_message_payload: dict[str, Any] | None
    reply_message_payload: dict[str, Any] | None
    root_content_payload: dict[str, Any] | None
    reply_content_payload: dict[str, Any] | None
    file_payload: dict[str, Any] | None
    root_idempotency_matches: int
    reply_idempotency_matches: int


def load_storage_verification_config(
    env: Mapping[str, str] | None = None,
) -> StorageVerificationConfig | None:
    env_map = os.environ if env is None else env
    redis_url = env_map.get("OPEN_MESSENGER_E2E_VERIFY_REDIS_URL")
    mysql_dsn = env_map.get("OPEN_MESSENGER_E2E_VERIFY_MYSQL_DSN")
    if not redis_url or not mysql_dsn:
        return None

    return StorageVerificationConfig(
        redis_url=redis_url,
        redis_key_prefix=env_map.get(
            "OPEN_MESSENGER_E2E_VERIFY_REDIS_KEY_PREFIX",
            "open_messenger:content",
        ),
        mysql_dsn=mysql_dsn,
        mysql_table_prefix=env_map.get(
            "OPEN_MESSENGER_E2E_VERIFY_MYSQL_TABLE_PREFIX",
            "open_messenger",
        ),
    )


def assert_native_api_storage_snapshot(
    snapshot: NativeApiStorageSnapshot,
    artifacts: NativeApiStorageArtifacts,
) -> None:
    _expect(snapshot.user_payload is not None, "MySQL user record missing")
    _expect(snapshot.user_payload["user_id"] == artifacts.user_id, "MySQL user_id mismatch")
    _expect(snapshot.user_payload["username"] == "e2e-user", "MySQL username mismatch")

    _expect(snapshot.channel_payload is not None, "MySQL channel record missing")
    _expect(snapshot.channel_payload["channel_id"] == artifacts.channel_id, "MySQL channel_id mismatch")
    _expect(snapshot.channel_payload["name"] == "e2e-general", "MySQL channel name mismatch")

    _expect(snapshot.thread_payload is not None, "MySQL thread record missing")
    _expect(snapshot.thread_payload["thread_id"] == artifacts.thread_id, "MySQL thread_id mismatch")
    _expect(
        snapshot.thread_payload["root_message_id"] == artifacts.root_message_id,
        "MySQL thread root_message_id mismatch",
    )
    _expect(snapshot.thread_payload["reply_count"] == 1, "MySQL thread reply_count mismatch")

    _expect(snapshot.root_message_payload is not None, "MySQL root message record missing")
    _expect(
        snapshot.root_message_payload["message_id"] == artifacts.root_message_id,
        "MySQL root message_id mismatch",
    )
    _expect(
        snapshot.root_message_payload["content_ref"] == artifacts.root_content_ref,
        "MySQL root content_ref mismatch",
    )
    _expect(
        snapshot.root_message_payload["sender_user_id"] == artifacts.user_id,
        "MySQL root sender_user_id mismatch",
    )
    _expect(snapshot.root_message_payload["thread_id"] is None, "MySQL root thread_id mismatch")
    _expect(
        snapshot.root_message_payload["idempotency_key"] == artifacts.root_idempotency_key,
        "MySQL root idempotency_key mismatch",
    )

    _expect(snapshot.reply_message_payload is not None, "MySQL thread reply record missing")
    _expect(
        snapshot.reply_message_payload["message_id"] == artifacts.reply_message_id,
        "MySQL reply message_id mismatch",
    )
    _expect(
        snapshot.reply_message_payload["content_ref"] == artifacts.reply_content_ref,
        "MySQL reply content_ref mismatch",
    )
    _expect(
        snapshot.reply_message_payload["sender_user_id"] == artifacts.user_id,
        "MySQL reply sender_user_id mismatch",
    )
    _expect(
        snapshot.reply_message_payload["thread_id"] == artifacts.thread_id,
        "MySQL reply thread_id mismatch",
    )
    _expect(
        snapshot.reply_message_payload["idempotency_key"] == artifacts.reply_idempotency_key,
        "MySQL reply idempotency_key mismatch",
    )

    _expect(snapshot.root_content_payload is not None, "Redis root content missing")
    _expect(snapshot.root_content_payload["text"] == "hello from e2e", "Redis root content mismatch")

    _expect(snapshot.reply_content_payload is not None, "Redis thread reply content missing")
    _expect(
        snapshot.reply_content_payload["text"] == "thread reply",
        "Redis thread reply content mismatch",
    )

    _expect(snapshot.file_payload is not None, "MySQL file metadata record missing")
    _expect(snapshot.file_payload["file_id"] == artifacts.file_id, "MySQL file_id mismatch")
    _expect(snapshot.file_payload["filename"] == "e2e.txt", "MySQL file filename mismatch")

    _expect(
        snapshot.root_idempotency_matches == 1,
        f"Expected one MySQL row for root idempotency key, found {snapshot.root_idempotency_matches}",
    )
    _expect(
        snapshot.reply_idempotency_matches == 1,
        f"Expected one MySQL row for reply idempotency key, found {snapshot.reply_idempotency_matches}",
    )


def load_native_api_storage_snapshot(
    config: StorageVerificationConfig,
    artifacts: NativeApiStorageArtifacts,
) -> NativeApiStorageSnapshot:
    redis_client = Redis.from_url(config.redis_url)

    with _connect_mysql(config.mysql_dsn) as mysql_conn:
        return NativeApiStorageSnapshot(
            user_payload=_fetch_entity_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "users"),
                entity_id=artifacts.user_id,
            ),
            channel_payload=_fetch_entity_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "channels"),
                entity_id=artifacts.channel_id,
            ),
            thread_payload=_fetch_entity_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "threads"),
                entity_id=artifacts.thread_id,
            ),
            root_message_payload=_fetch_message_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "messages"),
                message_id=artifacts.root_message_id,
            ),
            reply_message_payload=_fetch_message_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "messages"),
                message_id=artifacts.reply_message_id,
            ),
            root_content_payload=_fetch_redis_payload(
                redis_client,
                key=_redis_key(config.redis_key_prefix, artifacts.root_content_ref),
            ),
            reply_content_payload=_fetch_redis_payload(
                redis_client,
                key=_redis_key(config.redis_key_prefix, artifacts.reply_content_ref),
            ),
            file_payload=_fetch_entity_payload(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "files"),
                entity_id=artifacts.file_id,
            ),
            root_idempotency_matches=_count_messages_by_idempotency(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "messages"),
                channel_id=artifacts.channel_id,
                thread_id=None,
                idempotency_key=artifacts.root_idempotency_key,
            ),
            reply_idempotency_matches=_count_messages_by_idempotency(
                mysql_conn,
                table=_table_name(config.mysql_table_prefix, "messages"),
                channel_id=artifacts.channel_id,
                thread_id=artifacts.thread_id,
                idempotency_key=artifacts.reply_idempotency_key,
            ),
        )


def verify_native_api_storage(
    config: StorageVerificationConfig,
    artifacts: NativeApiStorageArtifacts,
) -> None:
    snapshot = load_native_api_storage_snapshot(config, artifacts)
    assert_native_api_storage_snapshot(snapshot, artifacts)


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _table_name(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _redis_key(prefix: str, content_ref: str) -> str:
    return f"{prefix}:{content_ref}"


def _fetch_entity_payload(
    mysql_conn: Any,
    *,
    table: str,
    entity_id: str,
) -> dict[str, Any] | None:
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SELECT payload FROM {table} WHERE entity_id=%s", (entity_id,))
        row = cursor.fetchone()
    return _decode_payload_row(row)


def _fetch_message_payload(
    mysql_conn: Any,
    *,
    table: str,
    message_id: str,
) -> dict[str, Any] | None:
    with mysql_conn.cursor() as cursor:
        cursor.execute(f"SELECT payload FROM {table} WHERE message_id=%s", (message_id,))
        row = cursor.fetchone()
    return _decode_payload_row(row)


def _count_messages_by_idempotency(
    mysql_conn: Any,
    *,
    table: str,
    channel_id: str,
    thread_id: str | None,
    idempotency_key: str,
) -> int:
    with mysql_conn.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS record_count
            FROM {table}
            WHERE channel_id=%s
              AND JSON_UNQUOTE(JSON_EXTRACT(payload, '$.idempotency_key'))=%s
              AND (
                (
                  %s IS NULL
                  AND (
                    JSON_EXTRACT(payload, '$.thread_id') IS NULL
                    OR JSON_TYPE(JSON_EXTRACT(payload, '$.thread_id'))='NULL'
                  )
                )
                OR JSON_UNQUOTE(JSON_EXTRACT(payload, '$.thread_id'))=%s
              )
            """,
            (channel_id, idempotency_key, thread_id, thread_id),
        )
        row = cursor.fetchone()
    return int((row or {}).get("record_count", 0))


def _fetch_redis_payload(redis_client: Any, *, key: str) -> dict[str, Any] | None:
    raw_value = redis_client.get(key)
    if raw_value is None:
        return None
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8")
    return json.loads(str(raw_value))


def _decode_payload_row(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = row.get("payload")
    if payload is None:
        return None
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        return json.loads(payload)
    return dict(payload)


def _connect_mysql(dsn: str) -> Any:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise ValueError("MySQL DSN must use mysql:// or mysql+pymysql:// scheme")
    if not parsed.hostname or not parsed.path or parsed.path == "/":
        raise ValueError("MySQL DSN must include host and database name")

    return pymysql.connect(
        host=parsed.hostname,
        port=int(parsed.port or 3306),
        user=unquote(parsed.username or ""),
        password=unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=True,
    )
