from __future__ import annotations

import pytest

from scripts.e2e_storage_assertions import (
    NativeApiStorageArtifacts,
    NativeApiStorageSnapshot,
    assert_native_api_storage_snapshot,
    load_storage_verification_config,
)


def _artifacts() -> NativeApiStorageArtifacts:
    return NativeApiStorageArtifacts(
        user_id="usr_01TESTUSER0000000000000000",
        channel_id="ch_01TESTCHAN0000000000000000",
        thread_id="th_01TESTTHRD0000000000000000",
        root_message_id="msg_01TESTROOT000000000000000",
        root_content_ref="cnt_01TESTROOT000000000000000",
        reply_message_id="msg_01TESTREPL000000000000000",
        reply_content_ref="cnt_01TESTREPL000000000000000",
        file_id="fil_01TESTFILE0000000000000000",
        root_idempotency_key="e2e-request-1",
        reply_idempotency_key="e2e-thread-request-1",
    )


def _snapshot() -> NativeApiStorageSnapshot:
    artifacts = _artifacts()
    return NativeApiStorageSnapshot(
        user_payload={
            "user_id": artifacts.user_id,
            "username": "e2e-user",
            "display_name": "E2E User",
        },
        channel_payload={
            "channel_id": artifacts.channel_id,
            "name": "e2e-general",
        },
        thread_payload={
            "thread_id": artifacts.thread_id,
            "root_message_id": artifacts.root_message_id,
            "reply_count": 1,
        },
        root_message_payload={
            "message_id": artifacts.root_message_id,
            "content_ref": artifacts.root_content_ref,
            "sender_user_id": artifacts.user_id,
            "thread_id": None,
            "idempotency_key": artifacts.root_idempotency_key,
        },
        reply_message_payload={
            "message_id": artifacts.reply_message_id,
            "content_ref": artifacts.reply_content_ref,
            "sender_user_id": artifacts.user_id,
            "thread_id": artifacts.thread_id,
            "idempotency_key": artifacts.reply_idempotency_key,
        },
        root_content_payload={"text": "hello from e2e"},
        reply_content_payload={"text": "thread reply"},
        file_payload={"file_id": artifacts.file_id, "filename": "e2e.txt"},
        root_idempotency_matches=1,
        reply_idempotency_matches=1,
    )


def test_load_storage_verification_config_returns_none_without_required_env() -> None:
    assert load_storage_verification_config({}) is None
    assert load_storage_verification_config({"OPEN_MESSENGER_E2E_VERIFY_REDIS_URL": "redis://redis:6379/0"}) is None


def test_load_storage_verification_config_reads_defaults() -> None:
    config = load_storage_verification_config(
        {
            "OPEN_MESSENGER_E2E_VERIFY_REDIS_URL": "redis://redis:6379/0",
            "OPEN_MESSENGER_E2E_VERIFY_MYSQL_DSN": "mysql+pymysql://app:app@mysql:3306/open_messenger",
        }
    )

    assert config is not None
    assert config.redis_key_prefix == "open_messenger:content"
    assert config.mysql_table_prefix == "open_messenger"


def test_assert_native_api_storage_snapshot_accepts_expected_records() -> None:
    assert_native_api_storage_snapshot(_snapshot(), _artifacts())


def test_assert_native_api_storage_snapshot_rejects_duplicate_idempotency_rows() -> None:
    snapshot = _snapshot()
    broken = NativeApiStorageSnapshot(
        **{
            **snapshot.__dict__,
            "reply_idempotency_matches": 2,
        }
    )

    with pytest.raises(AssertionError, match="Expected one MySQL row for reply idempotency key"):
        assert_native_api_storage_snapshot(broken, _artifacts())
