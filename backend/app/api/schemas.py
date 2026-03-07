from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ChannelResponse(BaseModel):
    channel_id: str
    name: str
    created_at: str


class CreateThreadRequest(BaseModel):
    root_message_id: str = Field(min_length=1)


class ThreadResponse(BaseModel):
    thread_id: str
    channel_id: str
    root_message_id: str
    reply_count: int
    last_message_at: str
    created_at: str


class MessageWriteFields(BaseModel):
    text: str = Field(min_length=1)
    thread_id: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class NativeCreateMessageRequest(MessageWriteFields):
    pass


class CreateMessageRequest(MessageWriteFields):
    sender_user_id: str = "system"


class MessageResponse(BaseModel):
    message_id: str
    channel_id: str
    thread_id: Optional[str]
    sender_user_id: str
    sender_username: Optional[str]
    sender_display_name: Optional[str]
    content_ref: str
    text: str
    attachments: list[str]
    created_at: str
    updated_at: str
    deleted_at: Optional[str]
    compat_origin: str
    idempotency_key: Optional[str]
    metadata: dict[str, Any]


class ListMessagesResponse(BaseModel):
    items: list[MessageResponse]
    next_cursor: Optional[str]


class BatchGetMessagesRequest(BaseModel):
    message_ids: list[str] = Field(min_length=1, max_length=200)


class BatchGetMessagesResponse(BaseModel):
    items: list[MessageResponse]
    not_found_ids: list[str]


class BatchCreateMessageItem(MessageWriteFields):
    channel_id: str = Field(min_length=1)


class BatchCreateMessagesRequest(BaseModel):
    items: list[BatchCreateMessageItem] = Field(min_length=1, max_length=100)


class BatchCreateMessagesResponse(BaseModel):
    items: list[MessageResponse]


class ThreadContextResponse(BaseModel):
    thread: ThreadResponse
    root_message: MessageResponse
    replies: list[MessageResponse]
    has_more_replies: bool


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: Optional[str] = Field(default=None, max_length=100)


class UserResponse(BaseModel):
    user_id: str
    username: str
    display_name: Optional[str]
    created_at: str


class CreateTokenRequest(BaseModel):
    user_id: str = Field(min_length=1)
    token_type: Literal["user_token", "bot_token", "service_token"] = "user_token"
    scopes: list[str] = Field(default_factory=list)


class TokenResponse(BaseModel):
    token_id: str
    user_id: str
    token_type: str
    scopes: list[str]
    created_at: str
    revoked_at: Optional[str]


class CreateTokenResponse(TokenResponse):
    token: str


class FileObjectResponse(BaseModel):
    file_id: str
    uploader_user_id: str
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: str


class EventResponse(BaseModel):
    event_id: str
    type: str
    occurred_at: str
    data: dict[str, Any]


class SlackPostMessageRequest(BaseModel):
    channel: str = Field(min_length=1)
    text: str = Field(min_length=1)
    thread_ts: Optional[str] = None


class TelegramSendMessageRequest(BaseModel):
    chat_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    reply_to_message_id: Optional[int] = None


class DiscordMessageReferenceRequest(BaseModel):
    message_id: str = Field(min_length=1)


class DiscordCreateMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    message_reference: Optional[DiscordMessageReferenceRequest] = None
