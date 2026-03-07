from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


DEFAULT_SCOPES = [
    "channels:read",
    "channels:write",
    "messages:read",
    "messages:write",
    "files:read",
    "files:write",
]


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "dev-admin-token"}


def _issue_bearer_headers(client: TestClient) -> dict[str, str]:
    user_response = client.post(
        "/admin/v1/users",
        json={"username": "load-user", "display_name": "Load User"},
        headers=_admin_headers(),
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user_id, "token_type": "user_token", "scopes": DEFAULT_SCOPES},
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    return {"Authorization": f"Bearer {token_response.json()['token']}"}


def test_bulk_message_and_file_smoke_flow(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS", "0")
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    channel_response = client.post("/v1/channels", json={"name": "load-channel"}, headers=headers)
    assert channel_response.status_code == 201
    channel_id = channel_response.json()["channel_id"]

    file_ids: list[str] = []
    for index in range(5):
        upload_response = client.post(
            "/v1/files",
            headers=headers,
            files={"file": (f"load-{index}.txt", f"payload-{index}".encode("utf-8"), "text/plain")},
        )
        assert upload_response.status_code == 201
        file_ids.append(upload_response.json()["file_id"])

    for index in range(60):
        payload = {"text": f"bulk-message-{index}", "idempotency_key": f"bulk-{index}"}
        if index < len(file_ids):
            payload["attachments"] = [file_ids[index]]
        message_response = client.post(
            f"/v1/channels/{channel_id}/messages",
            json=payload,
            headers=headers,
        )
        assert message_response.status_code == 201

    listed_texts: list[str] = []
    cursor: str | None = None
    while True:
        params = {"limit": 25}
        if cursor is not None:
            params["cursor"] = cursor
        list_response = client.get(
            f"/v1/channels/{channel_id}/messages",
            params=params,
            headers=headers,
        )
        assert list_response.status_code == 200
        page = list_response.json()
        listed_texts.extend(item["text"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert len(listed_texts) == 60
    assert listed_texts[0] == "bulk-message-0"
    assert listed_texts[-1] == "bulk-message-59"
