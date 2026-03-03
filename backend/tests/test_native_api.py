from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _create_channel(client: TestClient, name: str = "general") -> str:
    response = client.post("/v1/channels", json={"name": name})
    assert response.status_code == 201
    payload = response.json()
    assert payload["name"] == name
    assert payload["channel_id"].startswith("ch_")
    return payload["channel_id"]


def test_create_and_get_channel() -> None:
    client = TestClient(create_app())
    channel_id = _create_channel(client)

    response = client.get(f"/v1/channels/{channel_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["channel_id"] == channel_id
    assert payload["name"] == "general"
    assert payload["created_at"]


def test_post_and_list_channel_messages_with_cursor() -> None:
    client = TestClient(create_app())
    channel_id = _create_channel(client)

    posted_ids: list[str] = []
    for index in range(1, 4):
        response = client.post(
            f"/v1/channels/{channel_id}/messages",
            json={
                "text": f"message-{index}",
                "sender_user_id": "user-1",
                "attachments": [f"file-{index}"],
                "idempotency_key": f"req-{index}",
                "metadata": {"source": "test"},
            },
        )
        assert response.status_code == 201
        payload = response.json()
        assert payload["channel_id"] == channel_id
        assert payload["text"] == f"message-{index}"
        assert payload["content_ref"].startswith("cnt_")
        posted_ids.append(payload["message_id"])

    page1 = client.get(f"/v1/channels/{channel_id}/messages", params={"limit": 2})
    assert page1.status_code == 200
    page1_payload = page1.json()
    assert [item["text"] for item in page1_payload["items"]] == ["message-1", "message-2"]
    assert page1_payload["next_cursor"] == posted_ids[1]

    page2 = client.get(
        f"/v1/channels/{channel_id}/messages",
        params={"limit": 2, "cursor": page1_payload["next_cursor"]},
    )
    assert page2.status_code == 200
    page2_payload = page2.json()
    assert [item["text"] for item in page2_payload["items"]] == ["message-3"]
    assert page2_payload["next_cursor"] is None


def test_messages_endpoint_returns_404_for_missing_channel() -> None:
    client = TestClient(create_app())

    post_response = client.post(
        "/v1/channels/ch_missing/messages",
        json={"text": "hello"},
    )
    list_response = client.get("/v1/channels/ch_missing/messages")

    assert post_response.status_code == 404
    assert list_response.status_code == 404


def test_create_thread_and_post_thread_message() -> None:
    client = TestClient(create_app())
    channel_id = _create_channel(client)

    root_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "root"},
    )
    assert root_response.status_code == 201
    root_message_id = root_response.json()["message_id"]

    thread_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root_message_id},
    )
    assert thread_response.status_code == 201
    thread_payload = thread_response.json()
    assert thread_payload["channel_id"] == channel_id
    assert thread_payload["root_message_id"] == root_message_id
    assert thread_payload["reply_count"] == 0
    assert thread_payload["thread_id"].startswith("th_")

    reply_response = client.post(
        f"/v1/threads/{thread_payload['thread_id']}/messages",
        json={"text": "reply"},
    )
    assert reply_response.status_code == 201
    reply_payload = reply_response.json()
    assert reply_payload["thread_id"] == thread_payload["thread_id"]
    assert reply_payload["channel_id"] == channel_id

    channel_messages_response = client.get(f"/v1/channels/{channel_id}/messages")
    assert channel_messages_response.status_code == 200
    items = channel_messages_response.json()["items"]
    assert [item["text"] for item in items] == ["root", "reply"]
    assert items[1]["thread_id"] == thread_payload["thread_id"]


def test_thread_endpoints_validate_target_entities() -> None:
    client = TestClient(create_app())
    channel_id = _create_channel(client)
    other_channel_id = _create_channel(client, name="random")

    missing_root_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": "msg_missing"},
    )
    assert missing_root_response.status_code == 404

    root_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "root"},
    )
    assert root_response.status_code == 201
    root_message_id = root_response.json()["message_id"]

    mismatched_root_response = client.post(
        f"/v1/channels/{other_channel_id}/threads",
        json={"root_message_id": root_message_id},
    )
    assert mismatched_root_response.status_code == 400

    wrong_thread_response = client.post(
        "/v1/threads/th_missing/messages",
        json={"text": "hello"},
    )
    assert wrong_thread_response.status_code == 404


def test_native_api_works_with_file_backends(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))

    client = TestClient(create_app())
    channel_id = _create_channel(client, name="ops")

    message_response = client.post(
        f"/v1/channels/{channel_id}/messages",
        json={"text": "persisted"},
    )
    assert message_response.status_code == 201
    root_message_id = message_response.json()["message_id"]

    thread_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root_message_id},
    )
    assert thread_response.status_code == 201
    thread_id = thread_response.json()["thread_id"]

    reply_response = client.post(
        f"/v1/threads/{thread_id}/messages",
        json={"text": "persisted-reply"},
    )
    assert reply_response.status_code == 201
    assert reply_response.json()["thread_id"] == thread_id

    list_response = client.get(f"/v1/channels/{channel_id}/messages")
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
