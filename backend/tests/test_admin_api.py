import asyncio
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from app.auth import decode_and_verify_jwt_like_token
from app.main import create_app
from app.utils import is_valid_prefixed_ulid, parse_iso8601_utc


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
    assert is_valid_prefixed_ulid(payload["user_id"], "usr")
    assert payload["username"] == username
    assert parse_iso8601_utc(payload["created_at"]).isoformat().endswith("+00:00")
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
    assert is_valid_prefixed_ulid(token_payload["token_id"], "tok")
    assert token_payload["token_type"] == "bot_token"
    assert token_payload["token"]
    assert token_payload["token"].count(".") == 2
    assert parse_iso8601_utc(token_payload["created_at"]).isoformat().endswith("+00:00")

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


def test_rotate_token_revokes_previous_token_and_returns_new_plaintext_token() -> None:
    client = TestClient(create_app())
    user = _create_user(client)

    create_response = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user["user_id"],
            "token_type": "service_token",
            "scopes": ["messages:read"],
        },
        headers=_admin_headers(),
    )
    assert create_response.status_code == 201
    original = create_response.json()

    rotate_response = client.post(
        f"/admin/v1/tokens/{original['token_id']}/rotate",
        headers=_admin_headers(),
    )
    assert rotate_response.status_code == 201
    rotated = rotate_response.json()

    assert rotated["token_id"] != original["token_id"]
    assert rotated["user_id"] == user["user_id"]
    assert rotated["token_type"] == "service_token"
    assert rotated["scopes"] == ["messages:read"]
    assert rotated["token"]
    assert rotated["token"] != original["token"]
    assert parse_iso8601_utc(rotated["created_at"]).isoformat().endswith("+00:00")

    decoded_rotated = decode_and_verify_jwt_like_token(rotated["token"], "dev-signing-secret")
    assert decoded_rotated["tid"] == rotated["token_id"]
    assert decoded_rotated["sub"] == user["user_id"]
    assert decoded_rotated["token_type"] == "service_token"
    assert decoded_rotated["scopes"] == ["messages:read"]

    original_stored = asyncio.run(client.app.state.metadata_store.get_token(original["token_id"]))
    rotated_stored = asyncio.run(client.app.state.metadata_store.get_token(rotated["token_id"]))
    assert original_stored is not None
    assert rotated_stored is not None
    assert original_stored["revoked_at"] is not None
    assert rotated_stored["revoked_at"] is None
    assert rotated_stored["token_hash"] == hashlib.sha256(rotated["token"].encode("utf-8")).hexdigest()


def test_rotate_token_fails_for_missing_token() -> None:
    client = TestClient(create_app())

    response = client.post("/admin/v1/tokens/tok_missing/rotate", headers=_admin_headers())

    assert response.status_code == 404


def test_rotate_token_fails_for_revoked_token() -> None:
    client = TestClient(create_app())
    user = _create_user(client)

    create_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user["user_id"], "token_type": "user_token", "scopes": []},
        headers=_admin_headers(),
    )
    assert create_response.status_code == 201
    token_id = create_response.json()["token_id"]

    revoke_response = client.delete(f"/admin/v1/tokens/{token_id}", headers=_admin_headers())
    assert revoke_response.status_code == 204

    rotate_response = client.post(f"/admin/v1/tokens/{token_id}/rotate", headers=_admin_headers())
    assert rotate_response.status_code == 409


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
    rotate_response = client.post("/admin/v1/tokens/tok_missing/rotate")
    revoke_response = client.delete("/admin/v1/tokens/tok_missing")

    assert create_user_response.status_code == 403
    assert create_token_response.status_code == 403
    assert rotate_response.status_code == 403
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


def test_rotate_token_works_with_file_backends(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))

    client = TestClient(create_app())
    user = _create_user(client, username="rotate-bot")

    create_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user["user_id"], "token_type": "bot_token", "scopes": ["files:read"]},
        headers=_admin_headers(),
    )
    assert create_response.status_code == 201
    original_token_id = create_response.json()["token_id"]

    rotate_response = client.post(
        f"/admin/v1/tokens/{original_token_id}/rotate",
        headers=_admin_headers(),
    )
    assert rotate_response.status_code == 201
    rotated_token_id = rotate_response.json()["token_id"]

    reloaded = create_app()
    original = asyncio.run(reloaded.state.metadata_store.get_token(original_token_id))
    rotated = asyncio.run(reloaded.state.metadata_store.get_token(rotated_token_id))
    assert original is not None
    assert rotated is not None
    assert original["revoked_at"] is not None
    assert rotated["revoked_at"] is None


def test_revoked_token_can_no_longer_access_native_api() -> None:
    client = TestClient(create_app())
    user = _create_user(client, username="revoked-native-user")

    token_response = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user["user_id"],
            "token_type": "user_token",
            "scopes": ["channels:write"],
        },
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    token_payload = token_response.json()
    headers = {"Authorization": f"Bearer {token_payload['token']}"}

    allowed = client.post("/v1/channels", json={"name": "allowed"}, headers=headers)
    assert allowed.status_code == 201

    revoke_response = client.delete(
        f"/admin/v1/tokens/{token_payload['token_id']}",
        headers=_admin_headers(),
    )
    assert revoke_response.status_code == 204

    denied = client.post("/v1/channels", json={"name": "denied"}, headers=headers)
    assert denied.status_code == 401


def test_rotated_token_invalidates_old_plaintext_token_for_native_api() -> None:
    client = TestClient(create_app())
    user = _create_user(client, username="rotated-native-user")

    create_response = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user["user_id"],
            "token_type": "user_token",
            "scopes": ["channels:write"],
        },
        headers=_admin_headers(),
    )
    assert create_response.status_code == 201
    original_token = create_response.json()

    rotate_response = client.post(
        f"/admin/v1/tokens/{original_token['token_id']}/rotate",
        headers=_admin_headers(),
    )
    assert rotate_response.status_code == 201
    rotated_token = rotate_response.json()

    old_headers = {"Authorization": f"Bearer {original_token['token']}"}
    new_headers = {"Authorization": f"Bearer {rotated_token['token']}"}

    denied = client.post("/v1/channels", json={"name": "stale-token"}, headers=old_headers)
    allowed = client.post("/v1/channels", json={"name": "fresh-token"}, headers=new_headers)

    assert denied.status_code == 401
    assert allowed.status_code == 201
