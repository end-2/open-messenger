from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.config import Settings, get_settings

router = APIRouter()


class CreateChannelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ChannelResponse(BaseModel):
    channel_id: str
    name: str
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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


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
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    channel = {
        "channel_id": _new_id("ch"),
        "name": payload.name,
        "created_at": _utc_now_iso(),
    }
    return await metadata_store.create_channel(channel)


@router.get("/v1/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(channel_id: str, request: Request) -> dict[str, Any]:
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
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    message_id = _new_id("msg")
    content_ref = _new_id("cnt")
    now = _utc_now_iso()

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
        "thread_id": payload.thread_id,
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
    return _build_message_response(stored_metadata, content_payload)


@router.get("/v1/channels/{channel_id}/messages", response_model=ListMessagesResponse)
async def list_channel_messages(
    channel_id: str,
    request: Request,
    cursor: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
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
