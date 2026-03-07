from __future__ import annotations

import json
import socket
import time
from contextlib import closing, contextmanager
from threading import Thread
from typing import Iterator

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.utils import is_valid_prefixed_ulid, parse_iso8601_utc


DEFAULT_NATIVE_SCOPES = [
    "channels:read",
    "channels:write",
    "messages:read",
    "messages:write",
    "files:read",
    "files:write",
]


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "dev-admin-token"}


def _issue_bearer_headers(client: httpx.Client, scopes: list[str] | None = None) -> dict[str, str]:
    granted_scopes = scopes if scopes is not None else DEFAULT_NATIVE_SCOPES

    user_response = client.post(
        "/admin/v1/users",
        json={"username": "events-user", "display_name": "Events User"},
        headers=_admin_headers(),
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user_id, "token_type": "user_token", "scopes": granted_scopes},
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    token = token_response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def _create_channel(client: httpx.Client, headers: dict[str, str], name: str = "events") -> str:
    response = client.post("/v1/channels", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["channel_id"]


def _read_sse_events(lines, expected_count: int) -> list[dict[str, object]]:
    current: dict[str, str] = {}
    events: list[dict[str, object]] = []

    for line in lines:
        if not line:
            if "data" in current:
                events.append(json.loads(current["data"]))
                if len(events) >= expected_count:
                    return events
            current = {}
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        current[field] = value.strip()

    return events


@contextmanager
def _run_live_server() -> Iterator[str]:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        host, port = sock.getsockname()

    config = uvicorn.Config(create_app(), host=host, port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://{host}:{port}"
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/healthz", timeout=0.5)
            if response.status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise AssertionError("Timed out waiting for live event test server")

    try:
        yield base_url
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_event_stream_emits_thread_and_message_events() -> None:
    with _run_live_server() as base_url:
        with (
            httpx.Client(base_url=base_url, timeout=5) as control_client,
            httpx.Client(base_url=base_url, timeout=5) as stream_client,
        ):
            headers = _issue_bearer_headers(control_client)
            channel_id = _create_channel(control_client, headers)

            root_response = control_client.post(
                f"/v1/channels/{channel_id}/messages",
                json={"text": "root"},
                headers=headers,
            )
            assert root_response.status_code == 201
            root_message_id = root_response.json()["message_id"]

            with stream_client.stream("GET", "/v1/events/stream", headers=headers) as stream_response:
                lines = stream_response.iter_lines()
                assert next(lines) == ": connected"
                thread_response = control_client.post(
                    f"/v1/channels/{channel_id}/threads",
                    json={"root_message_id": root_message_id},
                    headers=headers,
                )
                assert thread_response.status_code == 201
                thread_id = thread_response.json()["thread_id"]

                reply_response = control_client.post(
                    f"/v1/threads/{thread_id}/messages",
                    json={"text": "reply"},
                    headers=headers,
                )
                assert reply_response.status_code == 201
                message_id = reply_response.json()["message_id"]

                events = _read_sse_events(lines, expected_count=2)

    assert [event["type"] for event in events] == ["thread.created", "message.created"]

    thread_event = events[0]
    assert is_valid_prefixed_ulid(str(thread_event["event_id"]), "evt")
    assert parse_iso8601_utc(str(thread_event["occurred_at"])).isoformat().endswith("+00:00")
    assert thread_event["data"] == {
        "channel_id": channel_id,
        "thread_id": thread_id,
        "root_message_id": root_message_id,
        "reply_count": 0,
    }

    message_event = events[1]
    assert is_valid_prefixed_ulid(str(message_event["event_id"]), "evt")
    assert parse_iso8601_utc(str(message_event["occurred_at"])).isoformat().endswith("+00:00")
    assert message_event["data"] == {
        "channel_id": channel_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "sender_user_id": "system",
        "compat_origin": "native",
        "attachments": [],
    }


def test_event_stream_emits_file_uploaded_event() -> None:
    with _run_live_server() as base_url:
        with (
            httpx.Client(base_url=base_url, timeout=5) as control_client,
            httpx.Client(base_url=base_url, timeout=5) as stream_client,
        ):
            headers = _issue_bearer_headers(control_client)

            with stream_client.stream("GET", "/v1/events/stream", headers=headers) as stream_response:
                lines = stream_response.iter_lines()
                assert next(lines) == ": connected"
                upload_response = control_client.post(
                    "/v1/files",
                    headers=headers,
                    files={"file": ("event.txt", b"event payload", "text/plain")},
                )
                assert upload_response.status_code == 201

                events = _read_sse_events(lines, expected_count=1)

    file_event = events[0]
    file_data = file_event["data"]

    assert file_event["type"] == "file.uploaded"
    assert is_valid_prefixed_ulid(str(file_event["event_id"]), "evt")
    assert parse_iso8601_utc(str(file_event["occurred_at"])).isoformat().endswith("+00:00")
    assert is_valid_prefixed_ulid(str(file_data["file_id"]), "fil")
    assert str(file_data["uploader_user_id"]).startswith("usr_")
    assert file_data["filename"] == "event.txt"
    assert file_data["mime_type"] == "text/plain"
    assert file_data["size_bytes"] == len(b"event payload")


def test_websocket_event_gateway_emits_standard_events() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    root_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "root"},
        headers=headers,
    )
    assert root_response.status_code == 201
    root_message_id = root_response.json()["message_id"]

    with client.websocket_connect("/v1/events/ws", headers=headers) as websocket:
        thread_response = client.post(
            f"/v1/channels/{channel_id}/threads",
            json={"root_message_id": root_message_id},
            headers=headers,
        )
        assert thread_response.status_code == 201
        thread_id = thread_response.json()["thread_id"]

        reply_response = client.post(
            f"/v1/threads/{thread_id}/messages",
            json={"text": "reply"},
            headers=headers,
        )
        assert reply_response.status_code == 201
        message_id = reply_response.json()["message_id"]

        thread_event = websocket.receive_json()
        message_event = websocket.receive_json()

        websocket.send_text("ping")
        assert websocket.receive_json() == {"type": "pong"}

    assert thread_event["type"] == "thread.created"
    assert thread_event["data"] == {
        "channel_id": channel_id,
        "thread_id": thread_id,
        "root_message_id": root_message_id,
        "reply_count": 0,
    }
    assert message_event["type"] == "message.created"
    assert message_event["data"] == {
        "channel_id": channel_id,
        "thread_id": thread_id,
        "message_id": message_id,
        "sender_user_id": "system",
        "compat_origin": "native",
        "attachments": [],
    }


def test_websocket_event_gateway_requires_token_and_scope() -> None:
    client = TestClient(create_app())

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/events/ws"):
            pass

    headers = _issue_bearer_headers(client, scopes=["channels:read"])
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/v1/events/ws", headers=headers):
            pass


def test_websocket_event_gateway_accepts_query_token() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    raw_token = headers["Authorization"].split(" ", 1)[1]

    with client.websocket_connect(f"/v1/events/ws?access_token={raw_token}") as websocket:
        websocket.send_text("ping")
        assert websocket.receive_json() == {"type": "pong"}
