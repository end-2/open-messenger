from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx


FULL_SCOPES = [
    "channels:read",
    "channels:write",
    "messages:read",
    "messages:write",
    "files:read",
    "files:write",
]

ACTOR_SPECS = {
    "alice": {
        "username": "matrix-alice",
        "display_name": "Matrix Alice",
        "scopes": FULL_SCOPES,
    },
    "bob": {
        "username": "matrix-bob",
        "display_name": "Matrix Bob",
        "scopes": FULL_SCOPES,
    },
    "carol": {
        "username": "matrix-carol",
        "display_name": "Matrix Carol",
        "scopes": ["channels:read", "messages:read"],
    },
    "dave": {
        "username": "matrix-dave",
        "display_name": "Matrix Dave",
        "scopes": ["messages:write"],
    },
    "erin": {
        "username": "matrix-erin",
        "display_name": "Matrix Erin",
        "scopes": ["channels:read"],
    },
    "frank": {
        "username": "matrix-frank",
        "display_name": "Matrix Frank",
        "scopes": ["messages:read"],
    },
    "grace": {
        "username": "matrix-grace",
        "display_name": "Matrix Grace",
        "scopes": ["channels:write"],
    },
}

EXPECTED_CHANNEL_TRANSCRIPTS = {
    "ops": [
        {"sender": "alice", "text": "Ops standup starts now.", "thread": None},
        {"sender": "dave", "text": "Write-only bot confirms deployment.", "thread": None},
        {"sender": "bob", "text": "Acknowledged by Bob.", "thread": "ops_incident"},
        {"sender": "dave", "text": "Metrics look stable from Dave.", "thread": "ops_incident"},
        {"sender": "alice", "text": "Batch sync note from Alice.", "thread": None},
        {
            "sender": "alice",
            "text": "Batch thread follow-up from Alice.",
            "thread": "ops_incident",
        },
    ],
    "release": [
        {"sender": "bob", "text": "Release branch is cut.", "thread": None},
        {"sender": "alice", "text": "Smoke tests are green.", "thread": "release_war_room"},
        {"sender": "bob", "text": "Release notes are drafted.", "thread": None},
        {
            "sender": "bob",
            "text": "Rotated token confirms go-live.",
            "thread": "release_war_room",
        },
    ],
    "staging": [
        {"sender": "alice", "text": "Staging smoke test scheduled.", "thread": None},
        {"sender": "bob", "text": "Staging checklist completed.", "thread": "staging_rollup"},
    ],
}

EXPECTED_THREAD_CONTEXTS = {
    "ops_incident": {
        "root": {"sender": "alice", "text": "Ops standup starts now.", "thread": None},
        "replies": [
            {"sender": "bob", "text": "Acknowledged by Bob.", "thread": "ops_incident"},
            {
                "sender": "dave",
                "text": "Metrics look stable from Dave.",
                "thread": "ops_incident",
            },
            {
                "sender": "alice",
                "text": "Batch thread follow-up from Alice.",
                "thread": "ops_incident",
            },
        ],
        "reply_count": 3,
        "has_more_replies": False,
    },
    "release_war_room": {
        "root": {"sender": "bob", "text": "Release branch is cut.", "thread": None},
        "replies": [
            {
                "sender": "alice",
                "text": "Smoke tests are green.",
                "thread": "release_war_room",
            },
            {
                "sender": "bob",
                "text": "Rotated token confirms go-live.",
                "thread": "release_war_room",
            },
        ],
        "reply_count": 2,
        "has_more_replies": False,
    },
    "staging_rollup": {
        "root": {"sender": "alice", "text": "Staging smoke test scheduled.", "thread": None},
        "replies": [
            {
                "sender": "bob",
                "text": "Staging checklist completed.",
                "thread": "staging_rollup",
            }
        ],
        "reply_count": 1,
        "has_more_replies": False,
    },
}

EXPECTED_BATCH_GET = [
    {"channel": "release", "sender": "bob", "text": "Release branch is cut.", "thread": None},
    {
        "channel": "ops",
        "sender": "alice",
        "text": "Batch thread follow-up from Alice.",
        "thread": "ops_incident",
    },
    {
        "channel": "staging",
        "sender": "bob",
        "text": "Staging checklist completed.",
        "thread": "staging_rollup",
    },
]


@dataclass
class ActorSession:
    alias: str
    user_id: str
    token_id: str
    token: str
    scopes: list[str]

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


def expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def wait_for_health(client: httpx.Client, timeout_seconds: float = 30.0) -> None:
    deadline = time.time() + timeout_seconds
    last_error: str | None = None
    while time.time() < deadline:
        try:
            response = client.get("/healthz")
            if response.status_code == 200 and response.json().get("status") == "ok":
                return
            last_error = f"unexpected health payload: {response.text}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Service did not become healthy within {timeout_seconds}s: {last_error}")


def request(
    client: httpx.Client,
    method: str,
    path: str,
    expected_status: int,
    **kwargs: Any,
) -> httpx.Response:
    response = client.request(method, path, **kwargs)
    if response.status_code != expected_status:
        raise AssertionError(
            f"{method} {path} expected {expected_status}, got {response.status_code}: {response.text}"
        )
    return response


def canonicalize_message(
    item: dict[str, Any],
    *,
    channel_alias_by_id: dict[str, str],
    actor_alias_by_user_id: dict[str, str],
    thread_alias_by_id: dict[str, str],
    include_channel: bool,
) -> dict[str, Any]:
    normalized = {
        "sender": actor_alias_by_user_id[str(item["sender_user_id"])],
        "text": str(item["text"]),
        "thread": (
            thread_alias_by_id[str(item["thread_id"])]
            if item.get("thread_id") is not None
            else None
        ),
    }
    if include_channel:
        normalized["channel"] = channel_alias_by_id[str(item["channel_id"])]
    return normalized


def canonicalize_channel_messages(
    items: list[dict[str, Any]],
    *,
    actor_alias_by_user_id: dict[str, str],
    thread_alias_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        canonicalize_message(
            item,
            channel_alias_by_id={},
            actor_alias_by_user_id=actor_alias_by_user_id,
            thread_alias_by_id=thread_alias_by_id,
            include_channel=False,
        )
        for item in items
    ]


def canonicalize_batch_get(
    items: list[dict[str, Any]],
    *,
    channel_alias_by_id: dict[str, str],
    actor_alias_by_user_id: dict[str, str],
    thread_alias_by_id: dict[str, str],
) -> list[dict[str, Any]]:
    return [
        canonicalize_message(
            item,
            channel_alias_by_id=channel_alias_by_id,
            actor_alias_by_user_id=actor_alias_by_user_id,
            thread_alias_by_id=thread_alias_by_id,
            include_channel=True,
        )
        for item in items
    ]


def canonicalize_thread_context(
    payload: dict[str, Any],
    *,
    actor_alias_by_user_id: dict[str, str],
    thread_alias_by_id: dict[str, str],
) -> dict[str, Any]:
    return {
        "root": canonicalize_message(
            payload["root_message"],
            channel_alias_by_id={},
            actor_alias_by_user_id=actor_alias_by_user_id,
            thread_alias_by_id=thread_alias_by_id,
            include_channel=False,
        ),
        "replies": canonicalize_channel_messages(
            payload["replies"],
            actor_alias_by_user_id=actor_alias_by_user_id,
            thread_alias_by_id=thread_alias_by_id,
        ),
        "reply_count": int(payload["thread"]["reply_count"]),
        "has_more_replies": bool(payload["has_more_replies"]),
    }


def assert_matches(name: str, actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(
            f"{name} did not match expectation\n"
            f"expected={json.dumps(expected, indent=2, sort_keys=True)}\n"
            f"actual={json.dumps(actual, indent=2, sort_keys=True)}"
        )


def run_matrix_scenario(base_url: str, admin_token: str) -> None:
    with httpx.Client(base_url=base_url, timeout=20.0) as client:
        wait_for_health(client)
        request(client, "GET", "/v1/info", 200)

        admin_headers = {"X-Admin-Token": admin_token}
        actors: dict[str, ActorSession] = {}
        actor_alias_by_user_id: dict[str, str] = {}

        for alias, spec in ACTOR_SPECS.items():
            user = request(
                client,
                "POST",
                "/admin/v1/users",
                201,
                headers=admin_headers,
                json={
                    "username": spec["username"],
                    "display_name": spec["display_name"],
                },
            ).json()
            token = request(
                client,
                "POST",
                "/admin/v1/tokens",
                201,
                headers=admin_headers,
                json={
                    "user_id": user["user_id"],
                    "token_type": "user_token",
                    "scopes": spec["scopes"],
                },
            ).json()
            actors[alias] = ActorSession(
                alias=alias,
                user_id=str(user["user_id"]),
                token_id=str(token["token_id"]),
                token=str(token["token"]),
                scopes=list(spec["scopes"]),
            )
            actor_alias_by_user_id[str(user["user_id"])] = alias

        request(client, "POST", "/v1/channels", 403, headers=actors["carol"].headers, json={"name": "denied-read-only"})
        request(client, "POST", "/v1/channels", 403, headers=actors["dave"].headers, json={"name": "denied-write-only"})

        channel_alias_by_id: dict[str, str] = {}
        channels: dict[str, str] = {}

        for alias, actor_alias in (
            ("ops", "alice"),
            ("release", "bob"),
            ("staging", "grace"),
        ):
            payload = request(
                client,
                "POST",
                "/v1/channels",
                201,
                headers=actors[actor_alias].headers,
                json={"name": alias},
            ).json()
            channels[alias] = str(payload["channel_id"])
            channel_alias_by_id[str(payload["channel_id"])] = alias

        request(
            client,
            "POST",
            f"/v1/channels/{channels['ops']}/messages",
            403,
            headers=actors["carol"].headers,
            json={"text": "carol should not write"},
        )
        request(client, "GET", f"/v1/channels/{channels['ops']}", 200, headers=actors["erin"].headers)
        request(client, "GET", f"/v1/channels/{channels['ops']}", 403, headers=actors["frank"].headers)
        request(client, "GET", f"/v1/channels/{channels['ops']}/messages", 403, headers=actors["erin"].headers)
        request(client, "GET", f"/v1/channels/{channels['ops']}/messages", 403, headers=actors["dave"].headers)
        request(
            client,
            "POST",
            f"/v1/channels/{channels['staging']}/messages",
            403,
            headers=actors["grace"].headers,
            json={"text": "grace should not write"},
        )

        messages: dict[str, dict[str, Any]] = {}
        thread_alias_by_id: dict[str, str] = {}
        threads: dict[str, str] = {}

        messages["ops_root"] = request(
            client,
            "POST",
            f"/v1/channels/{channels['ops']}/messages",
            201,
            headers=actors["alice"].headers,
            json={"text": "Ops standup starts now."},
        ).json()
        expect(
            messages["ops_root"]["sender_user_id"] == actors["alice"].user_id,
            "alice sender mismatch on ops_root",
        )

        messages["ops_write_only_root"] = request(
            client,
            "POST",
            f"/v1/channels/{channels['ops']}/messages",
            201,
            headers=actors["dave"].headers,
            json={"text": "Write-only bot confirms deployment."},
        ).json()
        expect(
            messages["ops_write_only_root"]["sender_user_id"] == actors["dave"].user_id,
            "dave sender mismatch on ops_write_only_root",
        )

        ops_thread = request(
            client,
            "POST",
            f"/v1/channels/{channels['ops']}/threads",
            201,
            headers=actors["alice"].headers,
            json={"root_message_id": messages["ops_root"]["message_id"]},
        ).json()
        threads["ops_incident"] = str(ops_thread["thread_id"])
        thread_alias_by_id[threads["ops_incident"]] = "ops_incident"

        messages["ops_reply_bob"] = request(
            client,
            "POST",
            f"/v1/threads/{threads['ops_incident']}/messages",
            201,
            headers=actors["bob"].headers,
            json={"text": "Acknowledged by Bob."},
        ).json()
        messages["ops_reply_dave"] = request(
            client,
            "POST",
            f"/v1/threads/{threads['ops_incident']}/messages",
            201,
            headers=actors["dave"].headers,
            json={"text": "Metrics look stable from Dave."},
        ).json()

        ops_batch_payload = {
            "items": [
                {
                    "channel_id": channels["ops"],
                    "text": "Batch sync note from Alice.",
                    "idempotency_key": "ops-batch-1",
                },
                {
                    "channel_id": channels["ops"],
                    "thread_id": threads["ops_incident"],
                    "text": "Batch thread follow-up from Alice.",
                    "idempotency_key": "ops-batch-2",
                },
            ]
        }
        ops_batch_first = request(
            client,
            "POST",
            "/v1/messages:batchCreate",
            201,
            headers=actors["alice"].headers,
            json=ops_batch_payload,
        ).json()
        ops_batch_second = request(
            client,
            "POST",
            "/v1/messages:batchCreate",
            201,
            headers=actors["alice"].headers,
            json=ops_batch_payload,
        ).json()
        expect(
            [item["message_id"] for item in ops_batch_first["items"]]
            == [item["message_id"] for item in ops_batch_second["items"]],
            "ops batch idempotency failed",
        )
        messages["ops_batch_root"] = ops_batch_first["items"][0]
        messages["ops_batch_reply"] = ops_batch_first["items"][1]

        messages["release_root"] = request(
            client,
            "POST",
            f"/v1/channels/{channels['release']}/messages",
            201,
            headers=actors["bob"].headers,
            json={"text": "Release branch is cut."},
        ).json()
        release_thread = request(
            client,
            "POST",
            f"/v1/channels/{channels['release']}/threads",
            201,
            headers=actors["alice"].headers,
            json={"root_message_id": messages["release_root"]["message_id"]},
        ).json()
        threads["release_war_room"] = str(release_thread["thread_id"])
        thread_alias_by_id[threads["release_war_room"]] = "release_war_room"

        messages["release_reply_alice"] = request(
            client,
            "POST",
            f"/v1/threads/{threads['release_war_room']}/messages",
            201,
            headers=actors["alice"].headers,
            json={"text": "Smoke tests are green."},
        ).json()
        messages["release_root_second"] = request(
            client,
            "POST",
            f"/v1/channels/{channels['release']}/messages",
            201,
            headers=actors["bob"].headers,
            json={"text": "Release notes are drafted."},
        ).json()

        rotated_bob = request(
            client,
            "POST",
            f"/admin/v1/tokens/{actors['bob'].token_id}/rotate",
            201,
            headers=admin_headers,
        ).json()
        stale_bob_headers = actors["bob"].headers
        actors["bob"] = ActorSession(
            alias="bob",
            user_id=actors["bob"].user_id,
            token_id=str(rotated_bob["token_id"]),
            token=str(rotated_bob["token"]),
            scopes=actors["bob"].scopes,
        )

        request(
            client,
            "POST",
            f"/v1/threads/{threads['release_war_room']}/messages",
            401,
            headers=stale_bob_headers,
            json={"text": "old token should fail"},
        )
        messages["release_reply_bob_rotated"] = request(
            client,
            "POST",
            f"/v1/threads/{threads['release_war_room']}/messages",
            201,
            headers=actors["bob"].headers,
            json={"text": "Rotated token confirms go-live."},
        ).json()

        messages["staging_root"] = request(
            client,
            "POST",
            f"/v1/channels/{channels['staging']}/messages",
            201,
            headers=actors["alice"].headers,
            json={"text": "Staging smoke test scheduled."},
        ).json()
        staging_thread = request(
            client,
            "POST",
            f"/v1/channels/{channels['staging']}/threads",
            201,
            headers=actors["bob"].headers,
            json={"root_message_id": messages["staging_root"]["message_id"]},
        ).json()
        threads["staging_rollup"] = str(staging_thread["thread_id"])
        thread_alias_by_id[threads["staging_rollup"]] = "staging_rollup"
        messages["staging_reply_bob"] = request(
            client,
            "POST",
            f"/v1/threads/{threads['staging_rollup']}/messages",
            201,
            headers=actors["bob"].headers,
            json={"text": "Staging checklist completed."},
        ).json()

        request(
            client,
            "DELETE",
            f"/admin/v1/tokens/{actors['dave'].token_id}",
            204,
            headers=admin_headers,
        )
        request(
            client,
            "POST",
            f"/v1/channels/{channels['ops']}/messages",
            401,
            headers=actors["dave"].headers,
            json={"text": "revoked dave should fail"},
        )

        request(
            client,
            "POST",
            "/v1/messages:batchCreate",
            403,
            headers=actors["carol"].headers,
            json={
                "items": [
                    {
                        "channel_id": channels["ops"],
                        "text": "carol cannot batch create",
                    }
                ]
            },
        )

        for reader_alias, channel_aliases in (
            ("alice", ["ops", "release", "staging"]),
            ("carol", ["ops", "release", "staging"]),
            ("frank", ["ops", "release"]),
        ):
            for channel_alias in channel_aliases:
                listed = request(
                    client,
                    "GET",
                    f"/v1/channels/{channels[channel_alias]}/messages",
                    200,
                    headers=actors[reader_alias].headers,
                ).json()
                actual = canonicalize_channel_messages(
                    listed["items"],
                    actor_alias_by_user_id=actor_alias_by_user_id,
                    thread_alias_by_id=thread_alias_by_id,
                )
                assert_matches(
                    f"{reader_alias} transcript for {channel_alias}",
                    actual,
                    EXPECTED_CHANNEL_TRANSCRIPTS[channel_alias],
                )

        for reader_alias in ("carol", "frank"):
            for thread_alias in ("ops_incident", "release_war_room", "staging_rollup"):
                context = request(
                    client,
                    "GET",
                    f"/v1/threads/{threads[thread_alias]}/context",
                    200,
                    headers=actors[reader_alias].headers,
                ).json()
                actual = canonicalize_thread_context(
                    context,
                    actor_alias_by_user_id=actor_alias_by_user_id,
                    thread_alias_by_id=thread_alias_by_id,
                )
                assert_matches(
                    f"{reader_alias} thread context for {thread_alias}",
                    actual,
                    EXPECTED_THREAD_CONTEXTS[thread_alias],
                )

        batch_get = request(
            client,
            "POST",
            "/v1/messages:batchGet",
            200,
            headers=actors["carol"].headers,
            json={
                "message_ids": [
                    messages["release_root"]["message_id"],
                    messages["ops_batch_reply"]["message_id"],
                    "msg_missing_matrix",
                    messages["staging_reply_bob"]["message_id"],
                ]
            },
        ).json()
        expect(batch_get["not_found_ids"] == ["msg_missing_matrix"], "batchGet missing IDs mismatch")
        batch_get_actual = canonicalize_batch_get(
            batch_get["items"],
            channel_alias_by_id=channel_alias_by_id,
            actor_alias_by_user_id=actor_alias_by_user_id,
            thread_alias_by_id=thread_alias_by_id,
        )
        assert_matches("batchGet canonical results", batch_get_actual, EXPECTED_BATCH_GET)

        request(client, "GET", f"/v1/channels/{channels['release']}", 200, headers=actors["carol"].headers)
        request(client, "GET", f"/v1/channels/{channels['release']}", 403, headers=actors["frank"].headers)
