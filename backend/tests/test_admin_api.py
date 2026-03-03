import asyncio
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def _create_user(client: TestClient, username: str = "alice") -> dict:
    response = client.post(
        "/admin/v1/users",
        json={"username": username, "display_name": "Alice"},
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["user_id"].startswith("usr_")
    assert payload["username"] == username
    return payload


def test_create_user_and_token_then_revoke() -> None:
    client = TestClient(create_app())
    user = _create_user(client)

    token_response = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user["user_id"],
            "token_type": "bot_token",
            "scopes": ["messages:write", "channels:read"],
        },
    )
    assert token_response.status_code == 201
    token_payload = token_response.json()
    assert token_payload["token_id"].startswith("tok_")
    assert token_payload["token_type"] == "bot_token"
    assert token_payload["token"]

    stored_token = asyncio.run(client.app.state.metadata_store.get_token(token_payload["token_id"]))
    assert stored_token is not None
    assert stored_token["token_hash"] == hashlib.sha256(
        token_payload["token"].encode("utf-8")
    ).hexdigest()
    assert "token" not in stored_token

    revoke_response = client.delete(f"/admin/v1/tokens/{token_payload['token_id']}")
    assert revoke_response.status_code == 204

    revoked = asyncio.run(client.app.state.metadata_store.get_token(token_payload["token_id"]))
    assert revoked is not None
    assert revoked["revoked_at"] is not None


def test_create_token_fails_for_missing_user() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/admin/v1/tokens",
        json={"user_id": "usr_missing", "token_type": "user_token", "scopes": []},
    )

    assert response.status_code == 404


def test_revoke_token_fails_for_missing_token() -> None:
    client = TestClient(create_app())

    response = client.delete("/admin/v1/tokens/tok_missing")

    assert response.status_code == 404


def test_admin_api_works_with_file_backends(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))

    client = TestClient(create_app())
    user = _create_user(client, username="ops-bot")

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user["user_id"], "token_type": "service_token", "scopes": []},
    )
    assert token_response.status_code == 201
    token_id = token_response.json()["token_id"]

    revoke_response = client.delete(f"/admin/v1/tokens/{token_id}")
    assert revoke_response.status_code == 204

    metadata_file = Path(tmp_path) / "metadata.json"
    assert metadata_file.exists()

    reloaded = create_app()
    reloaded_token = asyncio.run(reloaded.state.metadata_store.get_token(token_id))
    assert reloaded_token is not None
    assert reloaded_token["revoked_at"] is not None
