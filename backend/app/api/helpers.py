from __future__ import annotations

import json
import logging
import re
import secrets
from collections.abc import AsyncIterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, Request, UploadFile, WebSocket, status

from app.auth import (
    AuthContext,
    authenticate_raw_token,
    create_jwt_like_token,
    sha256_hexdigest,
)
from app.config import Settings, get_settings
from app.domain import EventLog, FileObject, Message, MessageContent, Thread, Token
from app.errors import api_error
from app.utils import new_prefixed_ulid, utc_now_iso8601

from .schemas import CreateMessageRequest


audit_logger = logging.getLogger("open_messenger.audit")
EVENT_TYPES = frozenset(
    {
        "message.created",
        "message.updated",
        "message.deleted",
        "thread.created",
        "file.uploaded",
    }
)


def utc_now_iso() -> str:
    return utc_now_iso8601()


def new_id(prefix: str) -> str:
    return new_prefixed_ulid(prefix)


def sanitize_filename(raw_filename: str | None) -> str:
    candidate = Path(raw_filename or "upload.bin").name.strip()
    if not candidate:
        candidate = "upload.bin"
    return re.sub(r"[^A-Za-z0-9._-]", "_", candidate)


def build_file_response(stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "file_id": str(stored["file_id"]),
        "uploader_user_id": str(stored["uploader_user_id"]),
        "filename": str(stored["filename"]),
        "mime_type": str(stored.get("mime_type", "application/octet-stream")),
        "size_bytes": int(stored.get("size_bytes", 0)),
        "sha256": str(stored.get("sha256", "")),
        "created_at": str(stored.get("created_at", "")),
    }


def build_event(event_type: str, occurred_at: str, data: dict[str, Any]) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported event type: {event_type}")
    return EventLog(
        event_id=new_id("evt"),
        type=event_type,
        occurred_at=occurred_at,
        data=data,
    ).to_dict()


async def publish_event(
    request: Request,
    *,
    event_type: str,
    occurred_at: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    event = build_event(event_type, occurred_at, data)
    await request.app.state.event_bus.publish(event)
    return event


def format_sse_event(event: dict[str, Any]) -> str:
    return (
        f"id: {event['event_id']}\n"
        f"event: {event['type']}\n"
        f"data: {json.dumps(event, ensure_ascii=True, separators=(',', ':'))}\n\n"
    )


def unix_timestamp_seconds(iso_timestamp: str) -> int:
    normalized = iso_timestamp.replace("Z", "+00:00")
    return int(datetime.fromisoformat(normalized).replace(tzinfo=timezone.utc).timestamp())


def slack_ts_from_sequence(sequence: int, iso_timestamp: str) -> str:
    return f"{unix_timestamp_seconds(iso_timestamp)}.{sequence:06d}"


def discord_message_id_from_sequence(sequence: int, iso_timestamp: str) -> str:
    return f"{unix_timestamp_seconds(iso_timestamp)}{sequence:06d}"


def has_required_scope(granted_scopes: list[str], required_scope: str) -> bool:
    scope_namespace = required_scope.split(":", 1)[0]
    return (
        required_scope in granted_scopes
        or f"{scope_namespace}:*" in granted_scopes
        or "*" in granted_scopes
    )


def extract_raw_token_from_authorization_header(
    authorization_header: str,
    *,
    allowed_prefixes: tuple[str, ...] = ("Bearer ",),
) -> str:
    for prefix in allowed_prefixes:
        if authorization_header.startswith(prefix):
            return authorization_header[len(prefix) :].strip()
    return ""


async def authenticate_compat_bearer_token(
    request: Request,
    required_scopes: list[str],
) -> AuthContext:
    auth_header = request.headers.get("authorization", "")
    raw_token = extract_raw_token_from_authorization_header(
        auth_header,
        allowed_prefixes=("Bearer ", "Bot "),
    )

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
        if not has_required_scope(context.scopes, required_scope):
            raise api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
                message=f"Missing required scope: {required_scope}",
                retryable=False,
            )
    return context


async def authenticate_websocket_token(
    websocket: WebSocket,
    required_scopes: list[str],
) -> AuthContext:
    raw_token = extract_raw_token_from_authorization_header(
        websocket.headers.get("authorization", ""),
        allowed_prefixes=("Bearer ",),
    )
    if not raw_token:
        raw_token = websocket.query_params.get("access_token", "").strip()

    if not raw_token:
        raise api_error(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="unauthorized",
            message="Missing bearer token",
            retryable=False,
        )

    settings: Settings = websocket.app.state.settings
    context = await authenticate_raw_token(raw_token, websocket, settings)
    for required_scope in required_scopes:
        if not has_required_scope(context.scopes, required_scope):
            raise api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
                message=f"Missing required scope: {required_scope}",
                retryable=False,
            )
    return context


async def authenticate_telegram_bot_token(
    request: Request,
    raw_token: str,
    required_scopes: list[str],
) -> AuthContext:
    settings: Settings = request.app.state.settings
    context = await authenticate_raw_token(raw_token, request, settings)
    for required_scope in required_scopes:
        if not has_required_scope(context.scopes, required_scope):
            raise api_error(
                status_code=status.HTTP_403_FORBIDDEN,
                code="forbidden",
                message=f"Missing required scope: {required_scope}",
                retryable=False,
            )
    return context


async def get_channel_or_404(metadata_store: Any, channel_id: str) -> dict[str, Any]:
    channel = await metadata_store.get_channel(channel_id)
    if channel is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="channel_not_found",
            message="Channel not found",
            retryable=False,
        )
    return channel


async def store_uploaded_file(
    settings: Settings,
    metadata_store: Any,
    file_store: Any,
    upload: UploadFile,
    uploader_user_id: str,
) -> dict[str, Any]:
    file_id = new_id("fil")
    safe_filename = sanitize_filename(upload.filename)
    max_size_bytes = int(settings.max_upload_mb * 1024 * 1024)

    try:
        stored_blob = await file_store.save(
            file_id,
            safe_filename,
            _upload_chunks(upload),
            max_size_bytes=max_size_bytes,
        )
    except ValueError as exc:
        if str(exc) != "file_too_large":
            raise
        raise api_error(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            code="file_too_large",
            message=f"File exceeds max upload size of {settings.max_upload_mb} MB",
            retryable=False,
        ) from exc
    finally:
        await upload.close()

    file_object = FileObject(
        file_id=file_id,
        uploader_user_id=uploader_user_id,
        filename=safe_filename,
        mime_type=upload.content_type or "application/octet-stream",
        size_bytes=int(stored_blob["size_bytes"]),
        storage_backend=str(stored_blob["storage_backend"]),
        storage_path=str(stored_blob["storage_path"]),
        sha256=str(stored_blob["sha256"]),
    ).to_dict()
    return await metadata_store.create_file(file_object)


async def _upload_chunks(upload: UploadFile) -> AsyncIterable[bytes]:
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        yield chunk


async def ensure_attachment_files_exist(
    metadata_store: Any,
    attachment_ids: list[str],
) -> None:
    for attachment_id in attachment_ids:
        file_object = await metadata_store.get_file(attachment_id)
        if file_object is None:
            raise api_error(
                status_code=status.HTTP_404_NOT_FOUND,
                code="attachment_not_found",
                message=f"Attachment not found: {attachment_id}",
                retryable=False,
            )


async def hydrate_message_response(
    stored_message: dict[str, Any],
    content_store: Any,
) -> dict[str, Any]:
    content_ref = str(stored_message["content_ref"])
    content_payload = await content_store.get(content_ref) or {}
    return build_message_response(stored_message, content_payload)


async def ensure_thread_for_root_message(
    request: Request,
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

    now = utc_now_iso()
    thread = Thread(
        thread_id=new_id("th"),
        channel_id=channel_id,
        root_message_id=root_message_id,
        reply_count=0,
        last_message_at=str(root_message.get("created_at", now)),
        created_at=now,
    ).to_dict()
    created_thread = await metadata_store.create_thread(thread)
    await publish_event(
        request,
        event_type="thread.created",
        occurred_at=str(created_thread["created_at"]),
        data={
            "channel_id": str(created_thread["channel_id"]),
            "thread_id": str(created_thread["thread_id"]),
            "root_message_id": str(created_thread["root_message_id"]),
            "reply_count": int(created_thread["reply_count"]),
        },
    )
    return created_thread


async def resolve_reply_thread_from_external_message(
    request: Request,
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

    thread = await ensure_thread_for_root_message(
        request=request,
        metadata_store=metadata_store,
        channel_id=channel_id,
        root_message_id=str(internal_message["message_id"]),
    )
    return internal_message, thread


async def register_compat_mapping(
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
            "mapping_id": new_id("map"),
            "origin": origin,
            "entity_type": entity_type,
            "channel_id": channel_id,
            "external_id": external_id,
            "internal_id": internal_id,
            "created_at": utc_now_iso(),
        }
    )


async def issue_admin_token(
    metadata_store: Any,
    settings: Settings,
    *,
    user_id: str,
    token_type: str,
    scopes: list[str],
) -> dict[str, Any]:
    now = utc_now_iso()
    token_record = Token(
        token_id=new_id("tok"),
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


def build_message_response(
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


async def store_message(
    channel_id: str,
    payload: CreateMessageRequest,
    metadata_store: Any,
    content_store: Any,
    force_thread_id: Optional[str] = None,
    compat_origin: str = "native",
) -> tuple[dict[str, Any], str, bool]:
    message_id = new_id("msg")
    content_ref = new_id("cnt")
    now = utc_now_iso()

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
            return build_message_response(existing, existing_content), occurred_at, False

    await ensure_attachment_files_exist(metadata_store, payload.attachments)

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
    return build_message_response(stored_metadata, content_payload), now, True


async def increment_thread_reply(
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
