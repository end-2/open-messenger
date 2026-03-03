from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from app.utils.time import utc_now_iso8601


CompatOrigin = Literal["native", "slack", "telegram", "discord"]
TokenType = Literal["user_token", "bot_token", "service_token"]


@dataclass(frozen=True)
class User:
    user_id: str
    username: str
    display_name: str | None = None
    created_at: str = field(default_factory=utc_now_iso8601)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Token:
    token_id: str
    user_id: str
    token_type: TokenType
    scopes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso8601)
    revoked_at: str | None = None
    token_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Channel:
    channel_id: str
    name: str
    created_at: str = field(default_factory=utc_now_iso8601)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ChannelMember:
    channel_member_id: str
    channel_id: str
    user_id: str
    role: str
    joined_at: str = field(default_factory=utc_now_iso8601)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Message:
    message_id: str
    channel_id: str
    thread_id: str | None
    sender_user_id: str
    content_ref: str
    attachments: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso8601)
    updated_at: str = field(default_factory=utc_now_iso8601)
    deleted_at: str | None = None
    compat_origin: CompatOrigin = "native"
    idempotency_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Thread:
    thread_id: str
    channel_id: str
    root_message_id: str
    reply_count: int = 0
    last_message_at: str = field(default_factory=utc_now_iso8601)
    created_at: str = field(default_factory=utc_now_iso8601)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FileObject:
    file_id: str
    uploader_user_id: str
    filename: str
    mime_type: str
    size_bytes: int
    storage_path: str
    sha256: str
    created_at: str = field(default_factory=utc_now_iso8601)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventLog:
    event_id: str
    type: str
    occurred_at: str = field(default_factory=utc_now_iso8601)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MessageContent:
    text: str
    blocks: list[dict[str, Any]] = field(default_factory=list)
    mentions: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
