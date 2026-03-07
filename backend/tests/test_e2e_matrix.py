from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.e2e_matrix_lib import (
    EXPECTED_CHANNEL_TRANSCRIPTS,
    assert_matches,
    canonicalize_batch_get,
    canonicalize_thread_context,
)


def test_canonicalize_batch_get_maps_users_channels_and_threads() -> None:
    actual = canonicalize_batch_get(
        [
            {
                "channel_id": "ch_release",
                "thread_id": None,
                "sender_user_id": "usr_bob",
                "text": "Release branch is cut.",
            },
            {
                "channel_id": "ch_ops",
                "thread_id": "th_ops",
                "sender_user_id": "usr_alice",
                "text": "Batch thread follow-up from Alice.",
            },
        ],
        channel_alias_by_id={"ch_release": "release", "ch_ops": "ops"},
        actor_alias_by_user_id={"usr_bob": "bob", "usr_alice": "alice"},
        thread_alias_by_id={"th_ops": "ops_incident"},
    )

    assert actual == [
        {
            "channel": "release",
            "sender": "bob",
            "text": "Release branch is cut.",
            "thread": None,
        },
        {
            "channel": "ops",
            "sender": "alice",
            "text": "Batch thread follow-up from Alice.",
            "thread": "ops_incident",
        },
    ]


def test_canonicalize_thread_context_maps_root_and_replies() -> None:
    actual = canonicalize_thread_context(
        {
            "thread": {"reply_count": 2},
            "root_message": {
                "channel_id": "ch_release",
                "thread_id": None,
                "sender_user_id": "usr_bob",
                "text": "Release branch is cut.",
            },
            "replies": [
                {
                    "channel_id": "ch_release",
                    "thread_id": "th_release",
                    "sender_user_id": "usr_alice",
                    "text": "Smoke tests are green.",
                }
            ],
            "has_more_replies": False,
        },
        actor_alias_by_user_id={"usr_bob": "bob", "usr_alice": "alice"},
        thread_alias_by_id={"th_release": "release_war_room"},
    )

    assert actual == {
        "root": {"sender": "bob", "text": "Release branch is cut.", "thread": None},
        "replies": [
            {
                "sender": "alice",
                "text": "Smoke tests are green.",
                "thread": "release_war_room",
            }
        ],
        "reply_count": 2,
        "has_more_replies": False,
    }


def test_assert_matches_raises_with_clear_diff() -> None:
    with pytest.raises(AssertionError, match="ops transcript did not match expectation"):
        assert_matches(
            "ops transcript",
            EXPECTED_CHANNEL_TRANSCRIPTS["ops"][:-1],
            EXPECTED_CHANNEL_TRANSCRIPTS["ops"],
        )
