import asyncio
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import decode_and_verify_jwt_like_token
from app.main import create_app


def _admin_headers(token: str = "dev-admin-token") -> dict[str, str]:
    return {"X-Admin-Token": token}


def _create_user(client: TestClient, username: str = "alice") -> dict:
    response = client.post(
        "/admin/v1/users",
        json={"username": username, "display_name": "Alice"},
        headers=_admin_headers(),
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
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    token_payload = token_response.json()
    assert token_payload["token_id"].startswith("tok_")
    assert token_payload["token_type"] == "bot_token"
    assert token_payload["token"]
    assert token_payload["token"].count(".") == 2

    decoded_token = decode_and_verify_jwt_like_token(token_payload["token"], "dev-signing-secret")
    assert decoded_token["tid"] == token_payload["token_id"]
    assert decoded_token["sub"] == user["user_id"]
    assert decoded_token["token_type"] == "bot_token"
    assert decoded_token["scopes"] == ["messages:write", "channels:read"]

    stored_token = asyncio.run(client.app.state.metadata_store.get_token(token_payload["token_id"]))
    assert stored_token is not None
    assert stored_token["token_hash"] == hashlib.sha256(
        token_payload["token"].encode("utf-8")
    ).hexdigest()
    assert "token" not in stored_token

    revoke_response = client.delete(
        f"/admin/v1/tokens/{token_payload['token_id']}",
        headers=_admin_headers(),
    )
    assert revoke_response.status_code == 204

    revoked = asyncio.run(client.app.state.metadata_store.get_token(token_payload["token_id"]))
    assert revoked is not None
    assert revoked["revoked_at"] is not None


def test_create_token_fails_for_missing_user() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/admin/v1/tokens",
        json={"user_id": "usr_missing", "token_type": "user_token", "scopes": []},
        headers=_admin_headers(),
    )

    assert response.status_code == 404


def test_revoke_token_fails_for_missing_token() -> None:
    client = TestClient(create_app())

    response = client.delete("/admin/v1/tokens/tok_missing", headers=_admin_headers())

    assert response.status_code == 404


def test_admin_api_requires_admin_token_header() -> None:
    client = TestClient(create_app())

    create_user_response = client.post(
        "/admin/v1/users",
        json={"username": "alice"},
    )
    create_token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": "usr_missing", "token_type": "user_token", "scopes": []},
    )
    revoke_response = client.delete("/admin/v1/tokens/tok_missing")

    assert create_user_response.status_code == 403
    assert create_token_response.status_code == 403
    assert revoke_response.status_code == 403


def test_admin_api_rejects_invalid_admin_token() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/admin/v1/users",
        json={"username": "alice"},
        headers=_admin_headers("wrong-token"),
    )

    assert response.status_code == 403


def test_admin_api_uses_configured_admin_token(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_ADMIN_API_TOKEN", "custom-admin-token")
    client = TestClient(create_app())

    denied = client.post(
        "/admin/v1/users",
        json={"username": "alice"},
        headers=_admin_headers(),
    )
    allowed = client.post(
        "/admin/v1/users",
        json={"username": "alice"},
        headers=_admin_headers("custom-admin-token"),
    )

    assert denied.status_code == 403
    assert allowed.status_code == 201


def test_v1_does_not_allow_user_or_token_creation() -> None:
    client = TestClient(create_app())

    create_user_response = client.post("/v1/users", json={"username": "alice"})
    create_token_response = client.post(
        "/v1/tokens",
        json={"user_id": "usr_123", "token_type": "user_token", "scopes": []},
    )

    assert create_user_response.status_code == 404
    assert create_token_response.status_code == 404


def test_admin_api_works_with_file_backends(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))

    client = TestClient(create_app())
    user = _create_user(client, username="ops-bot")

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user["user_id"], "token_type": "service_token", "scopes": []},
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    token_id = token_response.json()["token_id"]

    revoke_response = client.delete(f"/admin/v1/tokens/{token_id}", headers=_admin_headers())
    assert revoke_response.status_code == 204

    metadata_file = Path(tmp_path) / "metadata.json"
    assert metadata_file.exists()

    reloaded = create_app()
    reloaded_token = asyncio.run(reloaded.state.metadata_store.get_token(token_id))
    assert reloaded_token is not None
    assert reloaded_token["revoked_at"] is not None
