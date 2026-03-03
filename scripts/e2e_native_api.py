#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from typing import Any

import httpx

ULID_RE = re.compile(r"^[a-z][a-z0-9]*_[0-9A-HJKMNP-TV-Z]{26}$")


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _request(
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


def _wait_for_health(client: httpx.Client, timeout_seconds: float = 30.0) -> None:
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


def run(base_url: str, admin_token: str) -> None:
    default_scopes = [
        "channels:read",
        "channels:write",
        "messages:read",
        "messages:write",
        "files:read",
        "files:write",
    ]

    with httpx.Client(base_url=base_url, timeout=20.0) as client:
        _wait_for_health(client)
        _request(client, "GET", "/v1/info", 200)

        admin_headers = {"X-Admin-Token": admin_token}
        user_response = _request(
            client,
            "POST",
            "/admin/v1/users",
            201,
            headers=admin_headers,
            json={"username": "e2e-user", "display_name": "E2E User"},
        )
        user = user_response.json()
        user_id = user["user_id"]
        _expect(bool(ULID_RE.match(user_id)), f"Invalid user_id format: {user_id}")

        token_response = _request(
            client,
            "POST",
            "/admin/v1/tokens",
            201,
            headers=admin_headers,
            json={"user_id": user_id, "token_type": "user_token", "scopes": default_scopes},
        )
        bearer_token = token_response.json()["token"]
        native_headers = {"Authorization": f"Bearer {bearer_token}"}

        channel_response = _request(
            client,
            "POST",
            "/v1/channels",
            201,
            headers=native_headers,
            json={"name": "e2e-general"},
        )
        channel_id = channel_response.json()["channel_id"]

        message_payload = {
            "text": "hello from e2e",
            "sender_user_id": "e2e-sender",
            "idempotency_key": "e2e-request-1",
        }
        first_message = _request(
            client,
            "POST",
            f"/v1/channels/{channel_id}/messages",
            201,
            headers=native_headers,
            json=message_payload,
        ).json()
        second_message = _request(
            client,
            "POST",
            f"/v1/channels/{channel_id}/messages",
            200,
            headers=native_headers,
            json=message_payload,
        ).json()
        _expect(
            first_message["message_id"] == second_message["message_id"],
            "Idempotency check failed for channel message",
        )

        thread_response = _request(
            client,
            "POST",
            f"/v1/channels/{channel_id}/threads",
            201,
            headers=native_headers,
            json={"root_message_id": first_message["message_id"]},
        ).json()
        thread_id = thread_response["thread_id"]

        reply_payload = {
            "text": "thread reply",
            "sender_user_id": "e2e-sender",
            "idempotency_key": "e2e-thread-request-1",
        }
        first_reply = _request(
            client,
            "POST",
            f"/v1/threads/{thread_id}/messages",
            201,
            headers=native_headers,
            json=reply_payload,
        ).json()
        second_reply = _request(
            client,
            "POST",
            f"/v1/threads/{thread_id}/messages",
            200,
            headers=native_headers,
            json=reply_payload,
        ).json()
        _expect(
            first_reply["message_id"] == second_reply["message_id"],
            "Idempotency check failed for thread message",
        )

        listed = _request(
            client,
            "GET",
            f"/v1/channels/{channel_id}/messages",
            200,
            headers=native_headers,
        ).json()
        texts = [item["text"] for item in listed["items"]]
        _expect("hello from e2e" in texts, "Channel message missing in list response")
        _expect("thread reply" in texts, "Thread reply missing in list response")

        file_bytes = b"open-messenger-e2e-file"
        uploaded = _request(
            client,
            "POST",
            "/v1/files",
            201,
            headers=native_headers,
            files={"file": ("e2e.txt", file_bytes, "text/plain")},
        ).json()
        _expect(
            uploaded["sha256"] == hashlib.sha256(file_bytes).hexdigest(),
            "Uploaded file checksum mismatch",
        )
        file_id = uploaded["file_id"]

        downloaded = _request(
            client,
            "GET",
            f"/v1/files/{file_id}",
            200,
            headers=native_headers,
        )
        _expect(downloaded.content == file_bytes, "Downloaded file content mismatch")

        missing_file = _request(
            client,
            "GET",
            "/v1/files/fil_01ARZ3NDEKTSV4RRFFQ69G5FAV",
            404,
            headers=native_headers,
        ).json()
        _expect(set(missing_file.keys()) == {"code", "message", "retryable"}, "Invalid error schema")
        _expect(missing_file["code"] == "file_not_found", "Unexpected error code for missing file")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Open Messenger Native API E2E checks.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("OPEN_MESSENGER_E2E_BASE_URL", "http://127.0.0.1:18000"),
        help="Base URL for API server.",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("OPEN_MESSENGER_E2E_ADMIN_TOKEN", "dev-admin-token"),
        help="Admin API token for bootstrap operations.",
    )
    args = parser.parse_args()

    try:
        run(base_url=args.base_url, admin_token=args.admin_token)
    except Exception as exc:  # noqa: BLE001
        print(f"E2E failed: {exc}", file=sys.stderr)
        return 1

    print("E2E passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
