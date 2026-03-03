"""Storage abstraction package."""

from app.storage.factory import build_storage_registry
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.interfaces import MessageContentStore, MetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore

__all__ = [
    "FileMessageContentStore",
    "FileMetadataStore",
    "MessageContentStore",
    "MetadataStore",
    "InMemoryMessageContentStore",
    "InMemoryMetadataStore",
    "MySQLMetadataStore",
    "RedisMessageContentStore",
    "build_storage_registry",
]
