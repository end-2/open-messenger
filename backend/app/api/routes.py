from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field

from app.auth import AuthContext, create_jwt_like_token, require_scopes, sha256_hexdigest
from app.config import Settings, get_settings

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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access denied")


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
) -> tuple[dict[str, Any], str]:
    message_id = _new_id("msg")
    content_ref = _new_id("cnt")
    now = _utc_now_iso()

    resolved_thread_id = force_thread_id if force_thread_id is not None else payload.thread_id

    content_payload = {
        "text": payload.text,
        "blocks": payload.blocks,
        "mentions": payload.mentions,
        "raw_payload": payload.raw_payload,
    }
    await content_store.put(content_ref, content_payload)

    message_metadata = {
        "message_id": message_id,
        "channel_id": channel_id,
        "thread_id": resolved_thread_id,
        "sender_user_id": payload.sender_user_id,
        "content_ref": content_ref,
        "attachments": payload.attachments,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "compat_origin": "native",
        "idempotency_key": payload.idempotency_key,
        "metadata": payload.metadata,
    }
    stored_metadata = await metadata_store.create_message(message_metadata)
    return _build_message_response(stored_metadata, content_payload), now


async def _increment_thread_reply(
    metadata_store: Any,
    thread_id: str,
    occurred_at: str,
) -> dict[str, Any]:
    thread = await metadata_store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    patch = {
        "reply_count": int(thread.get("reply_count", 0)) + 1,
        "last_message_at": occurred_at,
    }
    updated = await metadata_store.update_thread(thread_id, patch)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
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
    channel = {
        "channel_id": _new_id("ch"),
        "name": payload.name,
        "created_at": _utc_now_iso(),
    }
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
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
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    if payload.thread_id is not None:
        thread = await metadata_store.get_thread(payload.thread_id)
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
        if str(thread.get("channel_id")) != channel_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Thread does not belong to the channel",
            )

    response, occurred_at = await _store_message(
        channel_id=channel_id,
        payload=payload,
        metadata_store=metadata_store,
        content_store=content_store,
    )
    if payload.thread_id is not None:
        await _increment_thread_reply(metadata_store, payload.thread_id, occurred_at)
    return response


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    root_message = await metadata_store.get_message(payload.root_message_id)
    if root_message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Root message not found")
    if str(root_message.get("channel_id")) != channel_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Root message does not belong to the channel",
        )

    now = _utc_now_iso()
    thread = {
        "thread_id": _new_id("th"),
        "channel_id": channel_id,
        "root_message_id": payload.root_message_id,
        "reply_count": 0,
        "last_message_at": str(root_message.get("created_at", now)),
        "created_at": now,
    }
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
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    thread = await metadata_store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")

    if payload.thread_id is not None and payload.thread_id != thread_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Thread ID in payload does not match URL",
        )

    channel_id = str(thread["channel_id"])
    response, occurred_at = await _store_message(
        channel_id=channel_id,
        payload=payload,
        metadata_store=metadata_store,
        content_store=content_store,
        force_thread_id=thread_id,
    )
    await _increment_thread_reply(metadata_store, thread_id, occurred_at)
    return response


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
    user = {
        "user_id": _new_id("usr"),
        "username": payload.username,
        "display_name": payload.display_name,
        "created_at": _utc_now_iso(),
    }
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    now = _utc_now_iso()
    token_record = {
        "token_id": _new_id("tok"),
        "user_id": payload.user_id,
        "token_type": payload.token_type,
        "scopes": payload.scopes,
        "created_at": now,
        "revoked_at": None,
    }
    token_payload = {
        "tid": token_record["token_id"],
        "sub": payload.user_id,
        "token_type": payload.token_type,
        "scopes": payload.scopes,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    if token.get("revoked_at") is None:
        await metadata_store.update_token(token_id, {"revoked_at": _utc_now_iso()})
        audit_logger.info("admin_token_revoked token_id=%s", token_id)
    else:
        audit_logger.info("admin_token_revoke_noop token_id=%s", token_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
