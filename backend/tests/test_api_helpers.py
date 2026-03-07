from __future__ import annotations

import asyncio

import pytest

from app.api.helpers import (
    build_event,
    hydrate_message_responses,
    discord_message_id_from_sequence,
    format_sse_event,
    has_required_scope,
    sanitize_filename,
    slack_ts_from_sequence,
    unix_timestamp_seconds,
)


def test_sanitize_filename_removes_path_segments_and_invalid_characters() -> None:
    assert sanitize_filename("../unsafe name?.txt") == "unsafe_name_.txt"
    assert sanitize_filename("") == "upload.bin"
    assert sanitize_filename(None) == "upload.bin"


def test_has_required_scope_accepts_exact_namespace_wildcard_and_global_wildcard() -> None:
    assert has_required_scope(["messages:write"], "messages:write") is True
    assert has_required_scope(["messages:*"], "messages:write") is True
    assert has_required_scope(["*"], "messages:write") is True
    assert has_required_scope(["messages:read"], "messages:write") is False


def test_build_event_rejects_unsupported_event_type() -> None:
    with pytest.raises(ValueError):
        build_event("message.unknown", "2026-03-07T00:00:00Z", {})


def test_event_formatting_and_external_timestamp_helpers() -> None:
    occurred_at = "2026-03-07T12:34:56Z"
    event = build_event("message.created", occurred_at, {"message_id": "msg_123"})

    formatted = format_sse_event(event)

    assert formatted.startswith(f"id: {event['event_id']}\n")
    assert "event: message.created\n" in formatted
    assert '"message_id":"msg_123"' in formatted
    assert unix_timestamp_seconds(occurred_at) == 1772886896
    assert slack_ts_from_sequence(7, occurred_at) == "1772886896.000007"
    assert discord_message_id_from_sequence(7, occurred_at) == "1772886896000007"


class _SpyMetadataStore:
    def __init__(self) -> None:
        self.get_users_calls = 0

    async def get_users(self, user_ids: list[str]) -> dict[str, dict[str, str]]:
        self.get_users_calls += 1
        return {
            "usr-1": {"user_id": "usr-1", "username": "alice", "display_name": "Alice"},
            "usr-2": {"user_id": "usr-2", "username": "bob", "display_name": "Bob"},
        }


class _SpyContentStore:
    def __init__(self) -> None:
        self.get_many_calls = 0

    async def get_many(self, content_ids: list[str]) -> dict[str, dict[str, str]]:
        self.get_many_calls += 1
        return {
            "cnt-1": {"text": "first"},
            "cnt-2": {"text": "second"},
        }


def test_hydrate_message_responses_batches_content_and_user_lookups() -> None:
    metadata_store = _SpyMetadataStore()
    content_store = _SpyContentStore()

    items = asyncio.run(
        hydrate_message_responses(
            [
                {
                    "message_id": "msg-1",
                    "channel_id": "ch-1",
                    "thread_id": None,
                    "sender_user_id": "usr-1",
                    "content_ref": "cnt-1",
                    "attachments": [],
                    "created_at": "2026-03-07T00:00:00Z",
                    "updated_at": "2026-03-07T00:00:00Z",
                    "deleted_at": None,
                    "compat_origin": "native",
                    "idempotency_key": None,
                    "metadata": {},
                },
                {
                    "message_id": "msg-2",
                    "channel_id": "ch-1",
                    "thread_id": None,
                    "sender_user_id": "usr-2",
                    "content_ref": "cnt-2",
                    "attachments": [],
                    "created_at": "2026-03-07T00:00:01Z",
                    "updated_at": "2026-03-07T00:00:01Z",
                    "deleted_at": None,
                    "compat_origin": "native",
                    "idempotency_key": None,
                    "metadata": {},
                },
            ],
            metadata_store,
            content_store,
        )
    )

    assert metadata_store.get_users_calls == 1
    assert content_store.get_many_calls == 1
    assert [item["text"] for item in items] == ["first", "second"]
    assert [item["sender_username"] for item in items] == ["alice", "bob"]
