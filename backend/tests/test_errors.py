from fastapi.testclient import TestClient

from app.main import create_app


def _admin_headers() -> dict[str, str]:
    return {"X-Admin-Token": "dev-admin-token"}


def _issue_bearer_headers(client: TestClient) -> dict[str, str]:
    user = client.post(
        "/admin/v1/users",
        json={"username": "err-user", "display_name": "Error User"},
        headers=_admin_headers(),
    )
    assert user.status_code == 201

    token = client.post(
        "/admin/v1/tokens",
        json={
            "user_id": user.json()["user_id"],
            "token_type": "user_token",
            "scopes": ["channels:write", "messages:write", "messages:read"],
        },
        headers=_admin_headers(),
    )
    assert token.status_code == 201
    return {"Authorization": f"Bearer {token.json()['token']}"}


def test_errors_are_structured_for_auth_failures() -> None:
    client = TestClient(create_app())

    response = client.post("/v1/channels", json={"name": "general"})

    assert response.status_code == 401
    payload = response.json()
    assert payload["code"] == "unauthorized"
    assert payload["message"] == "Missing bearer token"
    assert payload["retryable"] is False


def test_errors_are_structured_for_validation_failures() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    response = client.post("/v1/channels", json={"name": ""}, headers=headers)

    assert response.status_code == 422
    payload = response.json()
    assert payload["code"] == "validation_error"
    assert isinstance(payload["message"], str)
    assert payload["retryable"] is False


def test_errors_are_structured_for_domain_not_found() -> None:
    client = TestClient(create_app())
    headers = _issue_bearer_headers(client)

    response = client.post(
        "/v1/channels/ch_missing/messages",
        json={"text": "hello"},
        headers=headers,
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "channel_not_found"
    assert payload["message"] == "Channel not found"
    assert payload["retryable"] is False


def test_errors_are_structured_for_unknown_routes() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/unknown")

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "not_found"
    assert payload["message"] == "Not Found"
    assert payload["retryable"] is False
