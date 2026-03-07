from fastapi.testclient import TestClient

from app.main import create_app


def test_info_reports_memory_store_implementations_by_default() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/info")

    assert response.status_code == 200
    assert response.json()["content_store_impl"] == "InMemoryMessageContentStore"
    assert response.json()["metadata_store_impl"] == "InMemoryMetadataStore"
    assert response.json()["file_store_impl"] == "LocalFileBinaryStore"


def test_info_uses_environment_configuration(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPEN_MESSENGER_ENVIRONMENT", "test")
    monkeypatch.setenv("OPEN_MESSENGER_CONTENT_BACKEND", "file")
    monkeypatch.setenv("OPEN_MESSENGER_METADATA_BACKEND", "mysql")
    monkeypatch.setenv("OPEN_MESSENGER_FILE_STORAGE_BACKEND", "local")
    monkeypatch.setenv("OPEN_MESSENGER_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("OPEN_MESSENGER_FILES_ROOT_DIR", str(tmp_path / "files"))

    client = TestClient(create_app())

    response = client.get("/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "service": "open-messenger",
        "version": "v0.1",
        "environment": "test",
        "content_backend": "file",
        "metadata_backend": "mysql",
        "file_storage_backend": "local",
        "content_store_impl": "FileMessageContentStore",
        "metadata_store_impl": "MySQLMetadataStore",
        "file_store_impl": "LocalFileBinaryStore",
    }
