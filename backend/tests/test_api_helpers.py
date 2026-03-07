from __future__ import annotations

import pytest

from app.api.helpers import (
    build_event,
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
