from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

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


def _issue_bearer_headers(client: TestClient, scopes: list[str] | None = None) -> dict[str, str]:
    granted_scopes = scopes if scopes is not None else DEFAULT_NATIVE_SCOPES

    user_response = client.post(
        "/admin/v1/users",
        json={"username": "native-user", "display_name": "Native User"},
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


def _create_channel(client: TestClient, headers: dict[str, str], name: str = "general") -> str:
    response = client.post("/v1/channels", json={"name": name}, headers=headers)
    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == name
    assert is_valid_prefixed_ulid(payload["channel_id"], "ch")
    assert parse_iso8601_utc(payload["created_at"]).isoformat().endswith("+00:00")
    return payload["channel_id"]


def test_native_api_requires_bearer_token() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/channels", json={"name": "general"})

    assert response.status_code == 401


def test_native_api_requires_scope() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client, scopes=["channels:read"])

    response = client.post("/v1/channels", json={"name": "general"}, headers=headers)

    assert response.status_code == 403


def test_create_and_get_channel() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    response = client.get(f"/v1/channels/{channel_id}", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["channel_id"] == channel_id
    assert payload["name"] == "general"
    assert payload["created_at"]


def test_post_and_list_channel_messages_with_cursor() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    posted_ids: list[str] = []
    for index in range(1, 4):
        response = client.post(
            f"/v1/channels/{channel_id}/messages",
            json={
                "text": f"message-{index}",
                "sender_user_id": "user-1",
                "idempotency_key": f"req-{index}",
                "metadata": {"source": "test"},
            },
            headers=headers,
        )
        assert response.status_code == 201
        payload = response.json()
        assert is_valid_prefixed_ulid(payload["message_id"], "msg")
        assert payload["channel_id"] == channel_id
        assert payload["text"] == f"message-{index}"
        assert is_valid_prefixed_ulid(payload["content_ref"], "cnt")
        assert parse_iso8601_utc(payload["created_at"]).isoformat().endswith("+00:00")
        assert parse_iso8601_utc(payload["updated_at"]).isoformat().endswith("+00:00")
        posted_ids.append(payload["message_id"])

    page1 = client.get(
        f"/v1/channels/{channel_id}/messages",
        params={"limit": 2},
        headers=headers,
    )
    assert page1.status_code == 200
    page1_payload = page1.json()
    assert [item["text"] for item in page1_payload["items"]] == ["message-1", "message-2"]
    assert page1_payload["next_cursor"] == posted_ids[1]

    page2 = client.get(
        f"/v1/channels/{channel_id}/messages",
        params={"limit": 2, "cursor": page1_payload["next_cursor"]},
        headers=headers,
    )
    assert page2.status_code == 200
    page2_payload = page2.json()
    assert [item["text"] for item in page2_payload["items"]] == ["message-3"]
    assert page2_payload["next_cursor"] is None


def test_create_message_with_uploaded_attachment() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    upload_response = client.post(
        "/v1/files",
        headers=headers,
        files={"file": ("notes.txt", b"attachment-body", "text/plain")},
    )
    assert upload_response.status_code == 201
    file_id = upload_response.json()["file_id"]

    message_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "with attachment", "attachments": [file_id]},
        headers=headers,
    )

    assert message_response.status_code == 201
    assert message_response.json()["attachments"] == [file_id]


def test_create_message_rejects_missing_attachment() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "missing attachment", "attachments": ["fil_missing"]},
        headers=headers,
    )

    assert response.status_code == 404
    assert response.json()["code"] == "attachment_not_found"


def test_messages_endpoint_returns_404_for_missing_channel() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    post_response = client.post(
        "/v1/channels/ch_missing/messages",
        json={"text": "hello"},
        headers=headers,
    )
    list_response = client.get("/v1/channels/ch_missing/messages", headers=headers)

    assert post_response.status_code == 404
    assert list_response.status_code == 404


def test_create_thread_and_post_thread_message() -> None:
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

    thread_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root_message_id},
        headers=headers,
    )
    assert thread_response.status_code == 201
    thread_payload = thread_response.json()
    assert thread_payload["channel_id"] == channel_id
    assert thread_payload["root_message_id"] == root_message_id
    assert thread_payload["reply_count"] == 0
    assert is_valid_prefixed_ulid(thread_payload["thread_id"], "th")
    assert parse_iso8601_utc(thread_payload["created_at"]).isoformat().endswith("+00:00")
    assert parse_iso8601_utc(thread_payload["last_message_at"]).isoformat().endswith("+00:00")

    reply_response = client.post(
        f"/v1/threads/{thread_payload['thread_id']}/messages",
        json={"text": "reply"},
        headers=headers,
    )
    assert reply_response.status_code == 201
    reply_payload = reply_response.json()
    assert is_valid_prefixed_ulid(reply_payload["message_id"], "msg")
    assert is_valid_prefixed_ulid(reply_payload["content_ref"], "cnt")
    assert reply_payload["thread_id"] == thread_payload["thread_id"]
    assert reply_payload["channel_id"] == channel_id

    channel_messages_response = client.get(f"/v1/channels/{channel_id}/messages", headers=headers)
    assert channel_messages_response.status_code == 200
    items = channel_messages_response.json()["items"]
    assert [item["text"] for item in items] == ["root", "reply"]
    assert items[1]["thread_id"] == thread_payload["thread_id"]


def test_thread_endpoints_validate_target_entities() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)
    other_channel_id = _create_channel(client, headers, name="random")

    missing_root_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": "msg_missing"},
        headers=headers,
    )
    assert missing_root_response.status_code == 404

    root_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "root"},
        headers=headers,
    )
    assert root_response.status_code == 201
    root_message_id = root_response.json()["message_id"]

    mismatched_root_response = client.post(
        f"/v1/channels/{other_channel_id}/threads",
        json={"root_message_id": root_message_id},
        headers=headers,
    )
    assert mismatched_root_response.status_code == 400

    wrong_thread_response = client.post(
        "/v1/threads/th_missing/messages",
        json={"text": "hello"},
        headers=headers,
    )
    assert wrong_thread_response.status_code == 404


def test_native_api_works_with_file_backends(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_FILE_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("OPEN_MESSENGER_FILES_ROOT_DIR", str(tmp_path / "files"))

    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers, name="ops")

    message_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "persisted"},
        headers=headers,
    )
    assert message_response.status_code == 201
    root_message_id = message_response.json()["message_id"]

    thread_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root_message_id},
        headers=headers,
    )
    assert thread_response.status_code == 201
    thread_id = thread_response.json()["thread_id"]

    reply_response = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"text": "persisted-reply"},
        headers=headers,
    )
    assert reply_response.status_code == 201
    assert reply_response.json()["thread_id"] == thread_id

    list_response = client.get(f"/v1/channels/{channel_id}/messages", headers=headers)
    assert list_response.status_code == 200
    assert [item["text"] for item in list_response.json()["items"]] == [
        "persisted",
        "persisted-reply",
    ]

    metadata_file = Path(tmp_path) / "metadata.json"
    content_dir = Path(tmp_path) / "content"
    assert metadata_file.exists()
    assert content_dir.exists()
    assert any(content_dir.iterdir())


def test_channel_message_idempotency_reuses_existing_message() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    first = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "hello", "idempotency_key": "req-1"},
        headers=headers,
    )
    second = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "hello", "idempotency_key": "req-1"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["message_id"] == first.json()["message_id"]
    assert second.json()["content_ref"] == first.json()["content_ref"]

    listed = client.get(f"/v1/channels/{channel_id}/messages", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1


def test_thread_message_idempotency_reuses_existing_message() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)
    channel_id = _create_channel(client, headers)

    root = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "root"},
        headers=headers,
    )
    assert root.status_code == 201

    thread = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root.json()["message_id"]},
        headers=headers,
    )
    assert thread.status_code == 201
    thread_id = thread.json()["thread_id"]

    first = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"text": "reply", "idempotency_key": "req-thread-1"},
        headers=headers,
    )
    second = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"text": "reply", "idempotency_key": "req-thread-1"},
        headers=headers,
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["message_id"] == first.json()["message_id"]

    listed = client.get(f"/v1/channels/{channel_id}/messages", headers=headers)
    assert listed.status_code == 200
    assert [item["text"] for item in listed.json()["items"]] == ["root", "reply"]


def test_upload_and_download_file() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    payload = b"hello file"
    upload = client.post(
        "/v1/files",
        files={"file": ("hello.txt", payload, "text/plain")},
        headers=headers,
    )
    assert upload.status_code == 201
    uploaded = upload.json()
    assert is_valid_prefixed_ulid(uploaded["file_id"], "fil")
    assert uploaded["filename"] == "hello.txt"
    assert uploaded["mime_type"] == "text/plain"
    assert uploaded["size_bytes"] == len(payload)
    assert uploaded["sha256"] == hashlib.sha256(payload).hexdigest()

    download = client.get(f"/v1/files/{uploaded['file_id']}", headers=headers)
    assert download.status_code == 200
    assert download.content == payload
    assert download.headers["content-type"].startswith("text/plain")


def test_files_endpoints_require_scope() -> None:
    client = TestClient(create_app())
    scoped_headers = _issue_bearer_headers(client, scopes=["messages:read", "messages:write"])

    upload_denied = client.post(
        "/v1/files",
        files={"file": ("hello.txt", b"hello", "text/plain")},
        headers=scoped_headers,
    )
    assert upload_denied.status_code == 403

    full_headers = _issue_bearer_headers(client)
    uploaded = client.post(
        "/v1/files",
        files={"file": ("hello.txt", b"hello", "text/plain")},
        headers=full_headers,
    )
    assert uploaded.status_code == 201

    download_denied = client.get(
        f"/v1/files/{uploaded.json()['file_id']}",
        headers=scoped_headers,
    )
    assert download_denied.status_code == 403


def test_file_upload_rejects_payload_over_max_size(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_MAX_UPLOAD_MB", "1")
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    too_large = b"a" * (1024 * 1024 + 1)
    response = client.post(
        "/v1/files",
        files={"file": ("big.bin", too_large, "application/octet-stream")},
        headers=headers,
    )

    assert response.status_code == 413
    payload = response.json()
    assert payload["code"] == "file_too_large"
