from fastapi.testclient import TestClient

from app.main import create_app


def test_healthz_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_ok_with_store_checks() -> None:
    client = TestClient(create_app())

    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["checks"]["content_store"]["status"] == "ok"
    assert payload["checks"]["metadata_store"]["status"] == "ok"
    assert payload["checks"]["file_store"]["status"] == "ok"


def test_metrics_endpoint_exposes_http_metrics() -> None:
    client = TestClient(create_app())

    info_response = client.get("/v1/info")
    metrics_response = client.get("/metrics")

    assert info_response.status_code == 200
    assert metrics_response.status_code == 200
    assert "open_messenger_http_requests_total" in metrics_response.text
    assert 'path="/v1/info"' in metrics_response.text


def test_request_id_is_preserved_when_provided() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz", headers={"X-Request-Id": "req-from-client"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-from-client"


def test_request_id_is_generated_when_missing() -> None:
    client = TestClient(create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.headers["x-request-id"].startswith("req-")
