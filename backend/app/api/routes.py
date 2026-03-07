from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import (
    AuthContext,
    authenticate_raw_token,
    create_jwt_like_token,
    require_scopes,
    sha256_hexdigest,
)
from app.config import Settings, get_settings
from app.domain import Channel, FileObject, Message, MessageContent, Thread, Token, User
from app.errors import api_error
from app.utils import new_prefixed_ulid, utc_now_iso8601

router = APIRouter()
audit_logger = logging.getLogger("open_messenger.audit")


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


class CreateMessageRequest(BaseModel):
    text: str = Field(min_length=1)
    sender_user_id: str = "system"
    thread_id: Optional[str] = None
    attachments: list[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    mentions: list[str] = Field(default_factory=list)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    message_id: str
    channel_id: str
    thread_id: Optional[str]
    sender_user_id: str
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


def _utc_now_iso() -> str:
    return utc_now_iso8601()


def _new_id(prefix: str) -> str:
    return new_prefixed_ulid(prefix)


def _sanitize_filename(raw_filename: str | None) -> str:
    candidate = Path(raw_filename or "upload.bin").name.strip()
    if not candidate:
        candidate = "upload.bin"
    return re.sub(r"[^A-Za-z0-9._-]", "_", candidate)


def _build_file_response(stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": str(stored["file_id"]),
        "uploader_user_id": str(stored["uploader_user_id"]),
        "filename": str(stored["filename"]),
        "mime_type": str(stored.get("mime_type", "application/octet-stream")),
        "size_bytes": int(stored.get("size_bytes", 0)),
        "sha256": str(stored.get("sha256", "")),
        "created_at": str(stored.get("created_at", "")),
    }


def _unix_timestamp_seconds(iso_timestamp: str) -> int:
    normalized = iso_timestamp.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc).timestamp())


def _slack_ts_from_sequence(sequence: int, iso_timestamp: str) -> str:
    return f"{_unix_timestamp_seconds(iso_timestamp)}.{sequence:06d}"


def _discord_message_id_from_sequence(sequence: int, iso_timestamp: str) -> str:
    return f"{_unix_timestamp_seconds(iso_timestamp)}{sequence:06d}"


async def _authenticate_compat_bearer_token(
    request: Request,
    required_scopes: list[str],
) -> AuthContext:
    auth_header = request.headers.get("authorization", "")
    raw_token = ""
    for prefix in ("Bearer ", "Bot "):
        if auth_header.startswith(prefix):
            raw_token = auth_header[len(prefix) :].strip()
            break

    if not raw_token:
        raise api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Missing bearer token",
            retryable=False,
        )

    settings: Settings = request.app.state.settings
    context = await authenticate_raw_token(raw_token, request, settings)
    for required_scope in required_scopes:
        if required_scope not in context.scopes and f"{required_scope.split(':', 1)[0]}:*" not in context.scopes and "*" not in context.scopes:
            raise api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
                message=f"Missing required scope: {required_scope}",
                retryable=False,
            )
    return context


async def _authenticate_telegram_bot_token(
    request: Request,
    raw_token: str,
    required_scopes: list[str],
) -> AuthContext:
    settings: Settings = request.app.state.settings
    context = await authenticate_raw_token(raw_token, request, settings)
    for required_scope in required_scopes:
        if required_scope not in context.scopes and f"{required_scope.split(':', 1)[0]}:*" not in context.scopes and "*" not in context.scopes:
            raise api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
                message=f"Missing required scope: {required_scope}",
                retryable=False,
            )
    return context


async def _get_channel_or_404(metadata_store: Any, channel_id: str) -> dict[str, Any]:
    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )
    return channel


async def _store_uploaded_file(
    settings: Settings,
    metadata_store: Any,
    upload: UploadFile,
    uploader_user_id: str,
) -> dict[str, Any]:
    files_root = Path(settings.files_root_dir)
    files_root.mkdir(parents=True, exist_ok=True)

    file_id = _new_id("fil")
    safe_filename = _sanitize_filename(upload.filename)
    storage_path = files_root / f"{file_id}_{safe_filename}"
    max_size_bytes = int(settings.max_upload_mb * 1024 * 1024)

    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with storage_path.open("wb") as fp:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                size_bytes += len(chunk)
                if size_bytes > max_size_bytes:
                    fp.close()
                    storage_path.unlink(missing_ok=True)
                    raise api_error(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        code="file_too_large",
                        message=f"File exceeds max upload size of {settings.max_upload_mb} MB",
                        retryable=False,
                    )
                digest.update(chunk)
                fp.write(chunk)
    finally:
        await upload.close()

    file_object = FileObject(
        file_id=file_id,
        uploader_user_id=uploader_user_id,
        filename=safe_filename,
        mime_type=upload.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_path=str(storage_path),
        sha256=digest.hexdigest(),
    ).to_dict()
    return await metadata_store.create_file(file_object)


async def _ensure_thread_for_root_message(
    metadata_store: Any,
    channel_id: str,
    root_message_id: str,
) -> dict[str, Any]:
    existing = await metadata_store.get_thread_by_root_message(root_message_id)
    if existing is not None:
        return existing

    root_message = await metadata_store.get_message(root_message_id)
    if root_message is None or str(root_message.get("channel_id")) != channel_id:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="root_message_not_found",
            message="Root message not found",
            retryable=False,
        )

    now = _utc_now_iso()
    thread = Thread(
        thread_id=_new_id("th"),
        channel_id=channel_id,
        root_message_id=root_message_id,
        reply_count=0,
        last_message_at=str(root_message.get("created_at", now)),
        created_at=now,
    ).to_dict()
    return await metadata_store.create_thread(thread)


async def _resolve_reply_thread_from_external_message(
    metadata_store: Any,
    origin: str,
    channel_id: str,
    external_message_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    mapping = await metadata_store.get_compat_mapping(
        origin=origin,
        entity_type="message",
        external_id=external_message_id,
        channel_id=channel_id,
    )
    if mapping is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="message_not_found",
            message="Referenced message not found",
            retryable=False,
        )

    internal_message = await metadata_store.get_message(str(mapping["internal_id"]))
    if internal_message is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="message_not_found",
            message="Referenced message not found",
            retryable=False,
        )

    thread_id = internal_message.get("thread_id")
    if thread_id is not None:
        thread = await metadata_store.get_thread(str(thread_id))
        if thread is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="thread_not_found",
                message="Thread not found",
                retryable=False,
            )
        return internal_message, thread

    thread = await _ensure_thread_for_root_message(metadata_store, channel_id, str(internal_message["message_id"]))
    return internal_message, thread


async def _register_compat_mapping(
    metadata_store: Any,
    *,
    origin: str,
    entity_type: str,
    channel_id: str | None,
    external_id: str,
    internal_id: str,
) -> dict[str, Any]:
    return await metadata_store.create_compat_mapping(
        {
            "mapping_id": _new_id("map"),
            "origin": origin,
            "entity_type": entity_type,
            "channel_id": channel_id,
            "external_id": external_id,
            "internal_id": internal_id,
            "created_at": _utc_now_iso(),
        }
    )


async def _issue_admin_token(
    metadata_store: Any,
    settings: Settings,
    *,
    user_id: str,
    token_type: str,
    scopes: list[str],
) -> dict[str, Any]:
    now = _utc_now_iso()
    token_record = Token(
        token_id=_new_id("tok"),
        user_id=user_id,
        token_type=token_type,
        scopes=scopes,
        created_at=now,
        revoked_at=None,
    ).to_dict()
    token_payload = {
        "tid": token_record["token_id"],
        "sub": user_id,
        "token_type": token_type,
        "scopes": scopes,
        "iat": now,
    }
    plain_token = create_jwt_like_token(token_payload, settings.token_signing_secret)
    token_record["token_hash"] = sha256_hexdigest(plain_token)

    stored = await metadata_store.create_token(token_record)
    audit_logger.info(
        "admin_token_created token_id=%s user_id=%s token_type=%s scopes=%d",
        stored["token_id"],
        stored["user_id"],
        stored["token_type"],
        len(stored["scopes"]),
    )
    return {
        "token_id": stored["token_id"],
        "user_id": stored["user_id"],
        "token_type": stored["token_type"],
        "scopes": stored["scopes"],
        "created_at": stored["created_at"],
        "revoked_at": stored["revoked_at"],
        "token": plain_token,
    }


async def require_admin_access(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    presented_token = request.headers.get("x-admin-token")
    expected_token = settings.admin_api_token

    if not presented_token or not secrets.compare_digest(presented_token, expected_token):
        audit_logger.warning(
            "admin_access_denied path=%s method=%s",
            request.url.path,
            request.method,
        )
        raise api_error(
            status_code=status.HTTP_403_FORBIDDEN,
            code="admin_access_denied",
            message="Admin access denied",
            retryable=False,
        )


def _build_message_response(
    metadata: dict[str, Any],
    content_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "message_id": str(metadata["message_id"]),
        "channel_id": str(metadata["channel_id"]),
        "thread_id": metadata.get("thread_id"),
        "sender_user_id": str(metadata.get("sender_user_id", "system")),
        "content_ref": str(metadata["content_ref"]),
        "text": str(content_payload.get("text", "")),
        "attachments": list(metadata.get("attachments", [])),
        "created_at": str(metadata.get("created_at", "")),
        "updated_at": str(metadata.get("updated_at", "")),
        "deleted_at": metadata.get("deleted_at"),
        "compat_origin": str(metadata.get("compat_origin", "native")),
        "idempotency_key": metadata.get("idempotency_key"),
        "metadata": dict(metadata.get("metadata", {})),
    }


async def _store_message(
    channel_id: str,
    payload: CreateMessageRequest,
    metadata_store: Any,
    content_store: Any,
    force_thread_id: Optional[str] = None,
    compat_origin: str = "native",
) -> tuple[dict[str, Any], str, bool]:
    message_id = _new_id("msg")
    content_ref = _new_id("cnt")
    now = _utc_now_iso()

    resolved_thread_id = force_thread_id if force_thread_id is not None else payload.thread_id

    if payload.idempotency_key:
        existing = await metadata_store.find_message_by_idempotency(
            channel_id=channel_id,
            thread_id=resolved_thread_id,
            idempotency_key=payload.idempotency_key,
        )
        if existing is not None:
            existing_content = await content_store.get(str(existing["content_ref"])) or {}
            occurred_at = str(existing.get("updated_at") or existing.get("created_at") or now)
            return _build_message_response(existing, existing_content), occurred_at, False

    content_payload = MessageContent(
        text=payload.text,
        blocks=payload.blocks,
        mentions=payload.mentions,
        raw_payload=payload.raw_payload,
    ).to_dict()
    await content_store.put(content_ref, content_payload)

    message_metadata = Message(
        message_id=message_id,
        channel_id=channel_id,
        thread_id=resolved_thread_id,
        sender_user_id=payload.sender_user_id,
        content_ref=content_ref,
        attachments=payload.attachments,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        compat_origin=compat_origin,
        idempotency_key=payload.idempotency_key,
        metadata=payload.metadata,
    ).to_dict()
    stored_metadata = await metadata_store.create_message(message_metadata)
    return _build_message_response(stored_metadata, content_payload), now, True


async def _increment_thread_reply(
    metadata_store: Any,
    thread_id: str,
    occurred_at: str,
) -> dict[str, Any]:
    thread = await metadata_store.get_thread(thread_id)
    if thread is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="thread_not_found",
            message="Thread not found",
            retryable=False,
        )

    patch = {
        "reply_count": int(thread.get("reply_count", 0)) + 1,
        "last_message_at": occurred_at,
    }
    updated = await metadata_store.update_thread(thread_id, patch)
    if updated is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="thread_not_found",
            message="Thread not found",
            retryable=False,
        )
    return updated


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/info")
def service_info(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    content_store = request.app.state.content_store
    metadata_store = request.app.state.metadata_store

    return {
        "service": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "content_backend": settings.content_backend,
        "metadata_backend": settings.metadata_backend,
        "content_store_impl": content_store.__class__.__name__,
        "metadata_store_impl": metadata_store.__class__.__name__,
    }


@router.post(
    "/v1/channels",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel(
    payload: CreateChannelRequest,
    request: Request,
    _: AuthContext = Depends(require_scopes(["channels:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    channel = Channel(
        channel_id=_new_id("ch"),
        name=payload.name,
    ).to_dict()
    return await metadata_store.create_channel(channel)


@router.get("/v1/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str,
    request: Request,
    _: AuthContext = Depends(require_scopes(["channels:read"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )
    return channel


@router.post(
    "/v1/channels/{channel_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_message(
    channel_id: str,
    payload: CreateMessageRequest,
    request: Request,
    response: Response,
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )

    if payload.thread_id is not None:
        thread = await metadata_store.get_thread(payload.thread_id)
        if thread is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="thread_not_found",
                message="Thread not found",
                retryable=False,
            )
        if str(thread.get("channel_id")) != channel_id:
            raise api_error(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="thread_channel_mismatch",
                message="Thread does not belong to the channel",
                retryable=False,
            )

    message_response, occurred_at, created = await _store_message(
        channel_id=channel_id,
        payload=payload,
        metadata_store=metadata_store,
        content_store=content_store,
    )
    if payload.thread_id is not None and created:
        await _increment_thread_reply(metadata_store, payload.thread_id, occurred_at)
    if not created:
        response.status_code = status.HTTP_200_OK
    return message_response


@router.get("/v1/channels/{channel_id}/messages", response_model=ListMessagesResponse)
async def list_channel_messages(
    channel_id: str,
    request: Request,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthContext = Depends(require_scopes(["messages:read"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )

    stored_messages = await metadata_store.list_channel_messages(channel_id, cursor, limit)

    items: list[dict[str, Any]] = []
    for stored in stored_messages:
        content_ref = str(stored["content_ref"])
        content_payload = await content_store.get(content_ref) or {}
        items.append(_build_message_response(stored, content_payload))

    next_cursor = None
    if len(stored_messages) == limit:
        next_cursor = str(stored_messages[-1]["message_id"])

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@router.post(
    "/v1/channels/{channel_id}/threads",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_thread(
    channel_id: str,
    payload: CreateThreadRequest,
    request: Request,
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store

    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )

    root_message = await metadata_store.get_message(payload.root_message_id)
    if root_message is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="root_message_not_found",
            message="Root message not found",
            retryable=False,
        )
    if str(root_message.get("channel_id")) != channel_id:
        raise api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="root_message_channel_mismatch",
            message="Root message does not belong to the channel",
            retryable=False,
        )

    now = _utc_now_iso()
    thread = Thread(
        thread_id=_new_id("th"),
        channel_id=channel_id,
        root_message_id=payload.root_message_id,
        reply_count=0,
        last_message_at=str(root_message.get("created_at", now)),
        created_at=now,
    ).to_dict()
    return await metadata_store.create_thread(thread)


@router.post(
    "/v1/threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread_message(
    thread_id: str,
    payload: CreateMessageRequest,
    request: Request,
    response: Response,
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    thread = await metadata_store.get_thread(thread_id)
    if thread is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="thread_not_found",
            message="Thread not found",
            retryable=False,
        )

    if payload.thread_id is not None and payload.thread_id != thread_id:
        raise api_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="thread_id_mismatch",
            message="Thread ID in payload does not match URL",
            retryable=False,
        )

    channel_id = str(thread["channel_id"])
    message_response, occurred_at, created = await _store_message(
        channel_id=channel_id,
        payload=payload,
        metadata_store=metadata_store,
        content_store=content_store,
        force_thread_id=thread_id,
    )
    if created:
        await _increment_thread_reply(metadata_store, thread_id, occurred_at)
    else:
        response.status_code = status.HTTP_200_OK
    return message_response


@router.post(
    "/v1/files",
    response_model=FileObjectResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    context: AuthContext = Depends(require_scopes(["files:write"])),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    metadata_store = request.app.state.metadata_store
    stored = await _store_uploaded_file(settings, metadata_store, file, context.user_id)
    return _build_file_response(stored)


@router.get("/v1/files/{file_id}")
async def get_file(
    file_id: str,
    request: Request,
    _: AuthContext = Depends(require_scopes(["files:read"])),
) -> FileResponse:
    metadata_store = request.app.state.metadata_store
    file_object = await metadata_store.get_file(file_id)
    if file_object is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message="File not found",
            retryable=False,
        )

    storage_path = Path(str(file_object.get("storage_path", "")))
    if not storage_path.exists():
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message="File not found",
            retryable=False,
        )

    return FileResponse(
        path=storage_path,
        media_type=str(file_object.get("mime_type") or "application/octet-stream"),
        filename=str(file_object.get("filename") or storage_path.name),
    )


@router.post("/compat/slack/chat.postMessage")
async def slack_chat_post_message(
    payload: SlackPostMessageRequest,
    request: Request,
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    context = await _authenticate_compat_bearer_token(request, ["messages:write"])

    await _get_channel_or_404(metadata_store, payload.channel)

    resolved_thread_id: str | None = None
    thread_ts = payload.thread_ts
    if thread_ts is not None:
        thread_mapping = await metadata_store.get_compat_mapping(
            origin="slack",
            entity_type="thread",
            external_id=thread_ts,
            channel_id=payload.channel,
        )
        if thread_mapping is not None:
            resolved_thread_id = str(thread_mapping["internal_id"])
        else:
            _, thread = await _resolve_reply_thread_from_external_message(
                metadata_store,
                origin="slack",
                channel_id=payload.channel,
                external_message_id=thread_ts,
            )
            resolved_thread_id = str(thread["thread_id"])
            await _register_compat_mapping(
                metadata_store,
                origin="slack",
                entity_type="thread",
                channel_id=payload.channel,
                external_id=thread_ts,
                internal_id=resolved_thread_id,
            )

    message_response, occurred_at, created = await _store_message(
        channel_id=payload.channel,
        payload=CreateMessageRequest(
            text=payload.text,
            sender_user_id=context.user_id,
            thread_id=resolved_thread_id,
            metadata={"slack": {"thread_ts": thread_ts}},
            raw_payload=payload.model_dump(exclude_none=True),
        ),
        metadata_store=metadata_store,
        content_store=content_store,
        compat_origin="slack",
    )
    if resolved_thread_id is not None and created:
        await _increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)

    sequence = await metadata_store.next_compat_sequence("slack", payload.channel)
    message_ts = _slack_ts_from_sequence(sequence, occurred_at)
    await _register_compat_mapping(
        metadata_store,
        origin="slack",
        entity_type="message",
        channel_id=payload.channel,
        external_id=message_ts,
        internal_id=str(message_response["message_id"]),
    )

    effective_thread_ts = thread_ts or message_ts
    return {
        "ok": True,
        "channel": payload.channel,
        "ts": message_ts,
        "message": {
            "text": message_response["text"],
            "user": message_response["sender_user_id"],
            "ts": message_ts,
            "thread_ts": effective_thread_ts,
        },
    }


@router.post("/compat/slack/files.upload")
async def slack_files_upload(
    request: Request,
    channels: str = Form(...),
    file: UploadFile = File(...),
    thread_ts: Optional[str] = Form(default=None),
    initial_comment: Optional[str] = Form(default=None),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    context = await _authenticate_compat_bearer_token(request, ["files:write", "messages:write"])

    channel_id = channels.split(",", 1)[0].strip()
    await _get_channel_or_404(metadata_store, channel_id)

    stored_file = await _store_uploaded_file(settings, metadata_store, file, context.user_id)

    resolved_thread_id: str | None = None
    if thread_ts is not None:
        _, thread = await _resolve_reply_thread_from_external_message(
            metadata_store,
            origin="slack",
            channel_id=channel_id,
            external_message_id=thread_ts,
        )
        resolved_thread_id = str(thread["thread_id"])
        await _register_compat_mapping(
            metadata_store,
            origin="slack",
            entity_type="thread",
            channel_id=channel_id,
            external_id=thread_ts,
            internal_id=resolved_thread_id,
        )

    text = initial_comment or f"Uploaded file: {stored_file['filename']}"
    message_response, occurred_at, created = await _store_message(
        channel_id=channel_id,
        payload=CreateMessageRequest(
            text=text,
            sender_user_id=context.user_id,
            thread_id=resolved_thread_id,
            attachments=[str(stored_file["file_id"])],
            metadata={"slack": {"thread_ts": thread_ts}},
        ),
        metadata_store=metadata_store,
        content_store=content_store,
        compat_origin="slack",
    )
    if resolved_thread_id is not None and created:
        await _increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)

    sequence = await metadata_store.next_compat_sequence("slack", channel_id)
    message_ts = _slack_ts_from_sequence(sequence, occurred_at)
    await _register_compat_mapping(
        metadata_store,
        origin="slack",
        entity_type="message",
        channel_id=channel_id,
        external_id=message_ts,
        internal_id=str(message_response["message_id"]),
    )

    return {
        "ok": True,
        "file": {
            "id": stored_file["file_id"],
            "name": stored_file["filename"],
            "mimetype": stored_file["mime_type"],
            "size": stored_file["size_bytes"],
            "url_private_download": f"/v1/files/{stored_file['file_id']}",
        },
        "message": {
            "channel": channel_id,
            "ts": message_ts,
            "text": message_response["text"],
        },
    }


@router.post("/compat/telegram/bot{bot_token}/sendMessage")
async def telegram_send_message(
    bot_token: str,
    payload: TelegramSendMessageRequest,
    request: Request,
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    context = await _authenticate_telegram_bot_token(request, bot_token, ["messages:write"])

    await _get_channel_or_404(metadata_store, payload.chat_id)

    resolved_thread_id: str | None = None
    if payload.reply_to_message_id is not None:
        _, thread = await _resolve_reply_thread_from_external_message(
            metadata_store,
            origin="telegram",
            channel_id=payload.chat_id,
            external_message_id=str(payload.reply_to_message_id),
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await _store_message(
        channel_id=payload.chat_id,
        payload=CreateMessageRequest(
            text=payload.text,
            sender_user_id=context.user_id,
            thread_id=resolved_thread_id,
            metadata={"telegram": {"reply_to_message_id": payload.reply_to_message_id}},
            raw_payload=payload.model_dump(exclude_none=True),
        ),
        metadata_store=metadata_store,
        content_store=content_store,
        compat_origin="telegram",
    )
    if resolved_thread_id is not None and created:
        await _increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)

    external_message_id = str(await metadata_store.next_compat_sequence("telegram", payload.chat_id))
    await _register_compat_mapping(
        metadata_store,
        origin="telegram",
        entity_type="message",
        channel_id=payload.chat_id,
        external_id=external_message_id,
        internal_id=str(message_response["message_id"]),
    )
    return {
        "ok": True,
        "result": {
            "message_id": int(external_message_id),
            "date": _unix_timestamp_seconds(occurred_at),
            "chat": {"id": payload.chat_id, "type": "channel"},
            "text": message_response["text"],
        },
    }


@router.post("/compat/telegram/bot{bot_token}/sendDocument")
async def telegram_send_document(
    bot_token: str,
    request: Request,
    chat_id: str = Form(...),
    document: UploadFile = File(...),
    caption: Optional[str] = Form(default=None),
    reply_to_message_id: Optional[int] = Form(default=None),
) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    context = await _authenticate_telegram_bot_token(request, bot_token, ["files:write", "messages:write"])

    await _get_channel_or_404(metadata_store, chat_id)
    stored_file = await _store_uploaded_file(settings, metadata_store, document, context.user_id)

    resolved_thread_id: str | None = None
    if reply_to_message_id is not None:
        _, thread = await _resolve_reply_thread_from_external_message(
            metadata_store,
            origin="telegram",
            channel_id=chat_id,
            external_message_id=str(reply_to_message_id),
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await _store_message(
        channel_id=chat_id,
        payload=CreateMessageRequest(
            text=caption or stored_file["filename"],
            sender_user_id=context.user_id,
            thread_id=resolved_thread_id,
            attachments=[str(stored_file["file_id"])],
            metadata={"telegram": {"reply_to_message_id": reply_to_message_id}},
        ),
        metadata_store=metadata_store,
        content_store=content_store,
        compat_origin="telegram",
    )
    if resolved_thread_id is not None and created:
        await _increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)

    external_message_id = str(await metadata_store.next_compat_sequence("telegram", chat_id))
    await _register_compat_mapping(
        metadata_store,
        origin="telegram",
        entity_type="message",
        channel_id=chat_id,
        external_id=external_message_id,
        internal_id=str(message_response["message_id"]),
    )
    return {
        "ok": True,
        "result": {
            "message_id": int(external_message_id),
            "date": _unix_timestamp_seconds(occurred_at),
            "chat": {"id": chat_id, "type": "channel"},
            "caption": caption,
            "document": {
                "file_id": stored_file["file_id"],
                "file_name": stored_file["filename"],
                "mime_type": stored_file["mime_type"],
                "file_size": stored_file["size_bytes"],
            },
        },
    }


@router.post("/compat/discord/channels/{channel_id}/messages")
async def discord_create_message(
    channel_id: str,
    request: Request,
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    settings: Settings = request.app.state.settings
    context = await _authenticate_compat_bearer_token(request, ["messages:write"])

    await _get_channel_or_404(metadata_store, channel_id)

    content_type = request.headers.get("content-type", "")
    files: list[UploadFile] = []
    raw_payload: dict[str, Any]
    text: str
    external_reference_id: str | None = None

    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        text = str(form.get("content") or "")
        if not text:
            raise api_error(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                code="validation_error",
                message="Field required",
                retryable=False,
            )
        raw_reference = form.get("message_reference")
        raw_payload = {"content": text}
        if raw_reference:
            parsed_reference = json.loads(str(raw_reference))
            external_reference_id = str(parsed_reference.get("message_id", ""))
            raw_payload["message_reference"] = parsed_reference
        for _, value in form.multi_items():
            if hasattr(value, "filename") and hasattr(value, "read"):
                files.append(value)
    else:
        raw_payload = await request.json()
        payload = DiscordCreateMessageRequest.model_validate(raw_payload)
        text = payload.content
        if payload.message_reference is not None:
            external_reference_id = payload.message_reference.message_id

    attachment_ids: list[str] = []
    attachment_payloads: list[dict[str, Any]] = []
    for upload in files:
        stored_file = await _store_uploaded_file(settings, metadata_store, upload, context.user_id)
        attachment_ids.append(str(stored_file["file_id"]))
        attachment_payloads.append(
            {
                "id": stored_file["file_id"],
                "filename": stored_file["filename"],
                "size": stored_file["size_bytes"],
                "content_type": stored_file["mime_type"],
                "url": f"/v1/files/{stored_file['file_id']}",
            }
        )

    resolved_thread_id: str | None = None
    if external_reference_id is not None:
        _, thread = await _resolve_reply_thread_from_external_message(
            metadata_store,
            origin="discord",
            channel_id=channel_id,
            external_message_id=external_reference_id,
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await _store_message(
        channel_id=channel_id,
        payload=CreateMessageRequest(
            text=text,
            sender_user_id=context.user_id,
            thread_id=resolved_thread_id,
            attachments=attachment_ids,
            metadata={"discord": {"message_reference": external_reference_id}},
            raw_payload=raw_payload,
        ),
        metadata_store=metadata_store,
        content_store=content_store,
        compat_origin="discord",
    )
    if resolved_thread_id is not None and created:
        await _increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)

    external_message_id = _discord_message_id_from_sequence(
        await metadata_store.next_compat_sequence("discord", channel_id),
        occurred_at,
    )
    await _register_compat_mapping(
        metadata_store,
        origin="discord",
        entity_type="message",
        channel_id=channel_id,
        external_id=external_message_id,
        internal_id=str(message_response["message_id"]),
    )

    response_payload: dict[str, Any] = {
        "id": external_message_id,
        "channel_id": channel_id,
        "content": message_response["text"],
        "attachments": attachment_payloads,
    }
    if external_reference_id is not None:
        response_payload["message_reference"] = {"message_id": external_reference_id}
    return response_payload


@router.post(
    "/admin/v1/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_user(
    payload: CreateUserRequest,
    request: Request,
    _: None = Depends(require_admin_access),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    user = User(
        user_id=_new_id("usr"),
        username=payload.username,
        display_name=payload.display_name,
    ).to_dict()
    created = await metadata_store.create_user(user)
    audit_logger.info("admin_user_created user_id=%s username=%s", created["user_id"], created["username"])
    return created


@router.post(
    "/admin/v1/tokens",
    response_model=CreateTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_admin_token(
    payload: CreateTokenRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_admin_access),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    user = await metadata_store.get_user(payload.user_id)
    if user is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="user_not_found",
            message="User not found",
            retryable=False,
        )

    return await _issue_admin_token(
        metadata_store,
        settings,
        user_id=payload.user_id,
        token_type=payload.token_type,
        scopes=payload.scopes,
    )


@router.post(
    "/admin/v1/tokens/{token_id}/rotate",
    response_model=CreateTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rotate_admin_token(
    token_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_admin_access),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    token = await metadata_store.get_token(token_id)
    if token is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="token_not_found",
            message="Token not found",
            retryable=False,
        )

    if token.get("revoked_at") is not None:
        raise api_error(
            status_code=status.HTTP_409_CONFLICT,
            code="token_already_revoked",
            message="Token has already been revoked",
            retryable=False,
        )

    rotated = await _issue_admin_token(
        metadata_store,
        settings,
        user_id=str(token["user_id"]),
        token_type=str(token["token_type"]),
        scopes=list(token.get("scopes", [])),
    )
    revoked_at = _utc_now_iso()
    await metadata_store.update_token(token_id, {"revoked_at": revoked_at})
    audit_logger.info(
        "admin_token_rotated old_token_id=%s new_token_id=%s",
        token_id,
        rotated["token_id"],
    )
    return rotated


@router.delete(
    "/admin/v1/tokens/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_admin_token(
    token_id: str,
    request: Request,
    _: None = Depends(require_admin_access),
) -> Response:
    metadata_store = request.app.state.metadata_store
    token = await metadata_store.get_token(token_id)
    if token is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="token_not_found",
            message="Token not found",
            retryable=False,
        )

    if token.get("revoked_at") is None:
        await metadata_store.update_token(token_id, {"revoked_at": _utc_now_iso()})
        audit_logger.info("admin_token_revoked token_id=%s", token_id)
    else:
        audit_logger.info("admin_token_revoke_noop token_id=%s", token_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
