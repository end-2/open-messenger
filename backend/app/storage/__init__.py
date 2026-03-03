"""Storage abstraction package."""

from app.storage.factory import build_storage_registry
from app.storage.interfaces import MessageContentStore, MetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore

__all__ = [
    "MessageContentStore",
    "MetadataStore",
    "InMemoryMessageContentStore",
    "InMemoryMetadataStore",
    "build_storage_registry",
]
