from app.config import Settings
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.factory import build_storage_registry
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore


def test_build_storage_registry_selects_memory_implementations() -> None:
    settings = Settings(content_backend="memory", metadata_backend="memory")

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, InMemoryMessageContentStore)
    assert isinstance(metadata_store, InMemoryMetadataStore)


def test_build_storage_registry_selects_file_implementations(tmp_path) -> None:
    settings = Settings(
        content_backend="file",
        metadata_backend="file",
        storage_dir=str(tmp_path),
    )

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, FileMessageContentStore)
    assert isinstance(metadata_store, FileMetadataStore)


def test_build_storage_registry_selects_redis_and_mysql_implementations() -> None:
    settings = Settings(
        content_backend="redis",
        metadata_backend="mysql",
        redis_url="redis://localhost:6379/0",
        mysql_dsn="mysql+pymysql://app:app@localhost:3306/open_messenger",
    )

    content_store, metadata_store = build_storage_registry(settings)

    assert isinstance(content_store, RedisMessageContentStore)
    assert isinstance(metadata_store, MySQLMetadataStore)
