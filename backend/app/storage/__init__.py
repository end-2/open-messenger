"""Storage abstraction package."""

from app.storage.factory import build_storage_registry
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.interfaces import MessageContentStore, MetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore

__all__ = [
    "FileMessageContentStore",
    "FileMetadataStore",
    "MessageContentStore",
    "MetadataStore",
    "InMemoryMessageContentStore",
    "InMemoryMetadataStore",
    "build_storage_registry",
]
