from app.config import Settings
from app.storage.blob import LocalFileBinaryStore
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.factory import build_storage_registry
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore


def test_build_storage_registry_selects_memory_implementations() -> None:
    settings = Settings(content_backend="memory", metadata_backend="memory")

    content_store, metadata_store, file_store = build_storage_registry(settings)

    assert isinstance(content_store, InMemoryMessageContentStore)
    assert isinstance(metadata_store, InMemoryMetadataStore)
    assert isinstance(file_store, LocalFileBinaryStore)


def test_build_storage_registry_selects_file_implementations(tmp_path) -> None:
    settings = Settings(
        content_backend="file",
        metadata_backend="file",
        file_storage_backend="local",
        storage_dir=str(tmp_path),
        files_root_dir=str(tmp_path / "files"),
    )

    content_store, metadata_store, file_store = build_storage_registry(settings)

    assert isinstance(content_store, FileMessageContentStore)
    assert isinstance(metadata_store, FileMetadataStore)
    assert isinstance(file_store, LocalFileBinaryStore)


def test_build_storage_registry_selects_redis_and_mysql_implementations() -> None:
    settings = Settings(
        content_backend="redis",
        metadata_backend="mysql",
        file_storage_backend="local",
        redis_url="redis://localhost:6379/0",
        mysql_dsn="mysql+pymysql://app:app@localhost:3306/open_messenger",
    )

    content_store, metadata_store, file_store = build_storage_registry(settings)

    assert isinstance(content_store, RedisMessageContentStore)
    assert isinstance(metadata_store, MySQLMetadataStore)
    assert isinstance(file_store, LocalFileBinaryStore)
