from fastapi.testclient import TestClient

from app.main import create_app


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "dev-admin-token"}


def _issue_bearer_headers(client: TestClient) -> dict[str, str]:
    user_response = client.post(
        "/admin/v1/users",
        json={"username": "limited-user", "display_name": "Limited User"},
        headers=_admin_headers(),
    )
    assert user_response.status_code == 201
    user_id = user_response.json()["user_id"]

    token_response = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user_id,
            "token_type": "user_token",
            "scopes": ["channels:read", "channels:write", "messages:read", "messages:write"],
        },
        headers=_admin_headers(),
    )
    assert token_response.status_code == 201
    return {"Authorization": f"Bearer {token_response.json()['token']}"}


def test_rate_limit_applies_to_native_api_by_bearer_token(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS", "60")

    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    first = client.get("/v1/channels/ch_missing", headers=headers)
    second = client.get("/v1/channels/ch_missing", headers=headers)
    third = client.get("/v1/channels/ch_missing", headers=headers)

    assert first.status_code == 404
    assert second.status_code == 404
    assert third.status_code == 429
    assert third.json() == {
        "code": "rate_limited",
        "message": "Rate limit exceeded",
        "retryable": True,
    }
    assert int(third.headers["Retry-After"]) >= 1


def test_rate_limit_applies_to_admin_api_by_admin_token(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS", "60")

    client = TestClient(create_app())

    first = client.post("/admin/v1/users", json={"username": "alice"}, headers=_admin_headers())
    second = client.post("/admin/v1/users", json={"username": "bob"}, headers=_admin_headers())
    third = client.post("/admin/v1/users", json={"username": "charlie"}, headers=_admin_headers())

    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 429
    assert third.json()["code"] == "rate_limited"


def test_rate_limit_falls_back_to_client_ip_for_unauthenticated_requests(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS", "2")
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS", "60")

    client = TestClient(create_app())

    first = client.post("/v1/channels", json={"name": "general"})
    second = client.post("/v1/channels", json={"name": "general"})
    third = client.post("/v1/channels", json={"name": "general"})

    assert first.status_code == 401
    assert second.status_code == 401
    assert third.status_code == 429


def test_healthz_is_not_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_MAX_REQUESTS", "1")
    monkeypatch.setenv("OPEN_MESSENGER_RATE_LIMIT_WINDOW_SECONDS", "60")

    client = TestClient(create_app())

    first = client.get("/healthz")
    second = client.get("/healthz")

    assert first.status_code == 200
    assert second.status_code == 200
