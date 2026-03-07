from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


DEFAULT_COMPAT_SCOPES = [
    "channels:read",
    "channels:write",
    "messages:read",
    "messages:write",
    "files:read",
    "files:write",
]


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "dev-admin-token"}


def _bootstrap_user_token(client: TestClient, username: str) -> tuple[str, str]:
    user_response = client.post(
        "/admin/v1/users",
        json={"username": username, "display_name": username},
        headers=_admin_headers(),
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user_id, "token_type": "bot_token", "scopes": DEFAULT_COMPAT_SCOPES},
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    payload = token_response.json()
    return payload["token"], user_id


def _create_channel(client: TestClient, token: str, name: str = "compat-general") -> str:
    response = client.post(
        "/v1/channels",
        json={"name": name},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    return response.json()["channel_id"]


def test_slack_post_message_and_thread_reply() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "slack-bot")
    channel_id = _create_channel(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "root message"},
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["ok"] is True

    reply = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "reply message", "thread_ts": first_payload["ts"]},
        headers=headers,
    )
    assert reply.status_code == 200
    reply_payload = reply.json()
    assert reply_payload["message"]["thread_ts"] == first_payload["ts"]

    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["slack", "slack"]
    assert items[0]["thread_id"] is None
    assert items[1]["thread_id"] is not None


def test_slack_files_upload_creates_file_and_message() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "slack-files")
    channel_id = _create_channel(client, token)

    response = client.post(
        "/compat/slack/files.upload",
        headers={"Authorization": f"Bearer {token}"},
        data={"channels": channel_id, "initial_comment": "file comment"},
        files={"file": ("slack.txt", b"slack-file", "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["file"]["name"] == "slack.txt"
    assert payload["message"]["channel"] == channel_id

    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["slack"]
    assert items[0]["attachments"] == [payload["file"]["id"]]


def test_telegram_send_message_and_reply_mapping() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "telegram-bot")
    channel_id = _create_channel(client, token)

    first = client.post(
        f"/compat/telegram/bot{token}/sendMessage",
        json={"chat_id": channel_id, "text": "hello telegram"},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["ok"] is True

    reply = client.post(
        f"/compat/telegram/bot{token}/sendMessage",
        json={
            "chat_id": channel_id,
            "text": "telegram reply",
            "reply_to_message_id": first_payload["result"]["message_id"],
        },
    )
    assert reply.status_code == 200
    reply_payload = reply.json()
    assert reply_payload["result"]["message_id"] == first_payload["result"]["message_id"] + 1

    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["telegram", "telegram"]
    assert items[1]["thread_id"] is not None


def test_telegram_send_document_uploads_file() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "telegram-docs")
    channel_id = _create_channel(client, token)

    response = client.post(
        f"/compat/telegram/bot{token}/sendDocument",
        data={"chat_id": channel_id, "caption": "spec"},
        files={"document": ("spec.txt", b"telegram-doc", "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["result"]["document"]["file_name"] == "spec.txt"

    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["telegram"]
    assert items[0]["attachments"] == [payload["result"]["document"]["file_id"]]


def test_discord_create_message_and_reply_mapping() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "discord-bot")
    channel_id = _create_channel(client, token)
    headers = {"Authorization": f"Bot {token}"}

    first = client.post(
        f"/compat/discord/channels/{channel_id}/messages",
        json={"content": "hello discord"},
        headers=headers,
    )
    assert first.status_code == 200
    first_payload = first.json()

    reply = client.post(
        f"/compat/discord/channels/{channel_id}/messages",
        json={
            "content": "discord reply",
            "message_reference": {"message_id": first_payload["id"]},
        },
        headers=headers,
    )
    assert reply.status_code == 200
    assert reply.json()["message_reference"]["message_id"] == first_payload["id"]

    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["discord", "discord"]
    assert items[1]["thread_id"] is not None


def test_discord_create_message_with_attachment() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "discord-files")
    channel_id = _create_channel(client, token)

    response = client.post(
        f"/compat/discord/channels/{channel_id}/messages",
        headers={"Authorization": f"Bot {token}"},
        data={"content": "discord file"},
        files={"file": ("discord.txt", b"discord-file", "text/plain")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["attachments"][0]["filename"] == "discord.txt"
    listed = client.get(
        f"/v1/channels/{channel_id}/messages",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert [item["compat_origin"] for item in items] == ["discord"]
    assert items[0]["attachments"] == [payload["attachments"][0]["id"]]


def test_slack_reply_reuses_same_internal_thread() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "slack-thread-reuse")
    channel_id = _create_channel(client, token)
    headers = {"Authorization": f"Bearer {token}"}

    root = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "root"},
        headers=headers,
    )
    assert root.status_code == 200
    thread_ts = root.json()["ts"]

    first_reply = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "reply-1", "thread_ts": thread_ts},
        headers=headers,
    )
    second_reply = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "reply-2", "thread_ts": thread_ts},
        headers=headers,
    )

    assert first_reply.status_code == 200
    assert second_reply.status_code == 200

    listed = client.get(f"/v1/channels/{channel_id}/messages", headers=headers)
    items = listed.json()["items"]
    assert items[1]["thread_id"] == items[2]["thread_id"]


def test_compat_reply_to_unknown_message_returns_404() -> None:
    client = TestClient(create_app())
    token, _ = _bootstrap_user_token(client, "compat-missing-reply")
    channel_id = _create_channel(client, token)

    slack = client.post(
        "/compat/slack/chat.postMessage",
        json={"channel": channel_id, "text": "reply", "thread_ts": "1710000000.000001"},
        headers={"Authorization": f"Bearer {token}"},
    )
    telegram = client.post(
        f"/compat/telegram/bot{token}/sendMessage",
        json={"chat_id": channel_id, "text": "reply", "reply_to_message_id": 999},
    )
    discord = client.post(
        f"/compat/discord/channels/{channel_id}/messages",
        json={"content": "reply", "message_reference": {"message_id": "999"}},
        headers={"Authorization": f"Bot {token}"},
    )

    assert slack.status_code == 404
    assert telegram.status_code == 404
    assert discord.status_code == 404
    assert slack.json()["code"] == "message_not_found"
    assert telegram.json()["code"] == "message_not_found"
    assert discord.json()["code"] == "message_not_found"
