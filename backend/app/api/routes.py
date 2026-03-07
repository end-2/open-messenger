from __future__ import annotations

import hashlib
import logging
import re
import secrets
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Query, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.auth import AuthContext, create_jwt_like_token, require_scopes, sha256_hexdigest
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
        compat_origin="native",
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

    files_root = Path(settings.files_root_dir)
    files_root.mkdir(parents=True, exist_ok=True)

    file_id = _new_id("fil")
    safe_filename = _sanitize_filename(file.filename)
    storage_path = files_root / f"{file_id}_{safe_filename}"
    max_size_bytes = int(settings.max_upload_mb * 1024 * 1024)

    digest = hashlib.sha256()
    size_bytes = 0

    try:
        with storage_path.open("wb") as fp:
            while True:
                chunk = await file.read(1024 * 1024)
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
        await file.close()

    file_object = FileObject(
        file_id=file_id,
        uploader_user_id=context.user_id,
        filename=safe_filename,
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=size_bytes,
        storage_path=str(storage_path),
        sha256=digest.hexdigest(),
    ).to_dict()
    stored = await metadata_store.create_file(file_object)
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
