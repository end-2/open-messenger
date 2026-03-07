from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.config import Settings
from app.errors import api_error

from .helpers import (
    authenticate_compat_bearer_token,
    authenticate_telegram_bot_token,
    discord_message_id_from_sequence,
    get_channel_or_404,
    increment_thread_reply,
    publish_event,
    register_compat_mapping,
    resolve_reply_thread_from_external_message,
    slack_ts_from_sequence,
    store_message,
    store_uploaded_file,
    unix_timestamp_seconds,
)
from .schemas import (
    CreateMessageRequest,
    DiscordCreateMessageRequest,
    SlackPostMessageRequest,
    TelegramSendMessageRequest,
)


router = APIRouter()


@router.post("/compat/slack/chat.postMessage")
async def slack_chat_post_message(
    payload: SlackPostMessageRequest,
    request: Request,
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store
    context = await authenticate_compat_bearer_token(request, ["messages:write"])

    await get_channel_or_404(metadata_store, payload.channel)

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
            _, thread = await resolve_reply_thread_from_external_message(
                request,
                metadata_store,
                origin="slack",
                channel_id=payload.channel,
                external_message_id=thread_ts,
            )
            resolved_thread_id = str(thread["thread_id"])
            await register_compat_mapping(
                metadata_store,
                origin="slack",
                entity_type="thread",
                channel_id=payload.channel,
                external_id=thread_ts,
                internal_id=resolved_thread_id,
            )

    message_response, occurred_at, created = await store_message(
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
        await increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": payload.channel,
                "thread_id": resolved_thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )

    sequence = await metadata_store.next_compat_sequence("slack", payload.channel)
    message_ts = slack_ts_from_sequence(sequence, occurred_at)
    await register_compat_mapping(
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
    file_store = request.app.state.file_store
    context = await authenticate_compat_bearer_token(request, ["files:write", "messages:write"])

    channel_id = channels.split(",", 1)[0].strip()
    await get_channel_or_404(metadata_store, channel_id)

    stored_file = await store_uploaded_file(
        settings,
        metadata_store,
        file_store,
        file,
        context.user_id,
    )
    await publish_event(
        request,
        event_type="file.uploaded",
        occurred_at=str(stored_file["created_at"]),
        data={
            "file_id": str(stored_file["file_id"]),
            "uploader_user_id": str(stored_file["uploader_user_id"]),
            "filename": str(stored_file["filename"]),
            "mime_type": str(stored_file["mime_type"]),
            "size_bytes": int(stored_file["size_bytes"]),
        },
    )

    resolved_thread_id: str | None = None
    if thread_ts is not None:
        _, thread = await resolve_reply_thread_from_external_message(
            request,
            metadata_store,
            origin="slack",
            channel_id=channel_id,
            external_message_id=thread_ts,
        )
        resolved_thread_id = str(thread["thread_id"])
        await register_compat_mapping(
            metadata_store,
            origin="slack",
            entity_type="thread",
            channel_id=channel_id,
            external_id=thread_ts,
            internal_id=resolved_thread_id,
        )

    text = initial_comment or f"Uploaded file: {stored_file['filename']}"
    message_response, occurred_at, created = await store_message(
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
        await increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": channel_id,
                "thread_id": resolved_thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )

    sequence = await metadata_store.next_compat_sequence("slack", channel_id)
    message_ts = slack_ts_from_sequence(sequence, occurred_at)
    await register_compat_mapping(
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
    context = await authenticate_telegram_bot_token(request, bot_token, ["messages:write"])

    await get_channel_or_404(metadata_store, payload.chat_id)

    resolved_thread_id: str | None = None
    if payload.reply_to_message_id is not None:
        _, thread = await resolve_reply_thread_from_external_message(
            request,
            metadata_store,
            origin="telegram",
            channel_id=payload.chat_id,
            external_message_id=str(payload.reply_to_message_id),
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await store_message(
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
        await increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": payload.chat_id,
                "thread_id": resolved_thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )

    external_message_id = str(await metadata_store.next_compat_sequence("telegram", payload.chat_id))
    await register_compat_mapping(
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
            "date": unix_timestamp_seconds(occurred_at),
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
    file_store = request.app.state.file_store
    context = await authenticate_telegram_bot_token(request, bot_token, ["files:write", "messages:write"])

    await get_channel_or_404(metadata_store, chat_id)
    stored_file = await store_uploaded_file(
        settings,
        metadata_store,
        file_store,
        document,
        context.user_id,
    )
    await publish_event(
        request,
        event_type="file.uploaded",
        occurred_at=str(stored_file["created_at"]),
        data={
            "file_id": str(stored_file["file_id"]),
            "uploader_user_id": str(stored_file["uploader_user_id"]),
            "filename": str(stored_file["filename"]),
            "mime_type": str(stored_file["mime_type"]),
            "size_bytes": int(stored_file["size_bytes"]),
        },
    )

    resolved_thread_id: str | None = None
    if reply_to_message_id is not None:
        _, thread = await resolve_reply_thread_from_external_message(
            request,
            metadata_store,
            origin="telegram",
            channel_id=chat_id,
            external_message_id=str(reply_to_message_id),
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await store_message(
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
        await increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": chat_id,
                "thread_id": resolved_thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )

    external_message_id = str(await metadata_store.next_compat_sequence("telegram", chat_id))
    await register_compat_mapping(
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
            "date": unix_timestamp_seconds(occurred_at),
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
    file_store = request.app.state.file_store
    context = await authenticate_compat_bearer_token(request, ["messages:write"])

    await get_channel_or_404(metadata_store, channel_id)

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
        stored_file = await store_uploaded_file(
            settings,
            metadata_store,
            file_store,
            upload,
            context.user_id,
        )
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
        await publish_event(
            request,
            event_type="file.uploaded",
            occurred_at=str(stored_file["created_at"]),
            data={
                "file_id": str(stored_file["file_id"]),
                "uploader_user_id": str(stored_file["uploader_user_id"]),
                "filename": str(stored_file["filename"]),
                "mime_type": str(stored_file["mime_type"]),
                "size_bytes": int(stored_file["size_bytes"]),
            },
        )

    resolved_thread_id: str | None = None
    if external_reference_id is not None:
        _, thread = await resolve_reply_thread_from_external_message(
            request,
            metadata_store,
            origin="discord",
            channel_id=channel_id,
            external_message_id=external_reference_id,
        )
        resolved_thread_id = str(thread["thread_id"])

    message_response, occurred_at, created = await store_message(
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
        await increment_thread_reply(metadata_store, resolved_thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": channel_id,
                "thread_id": resolved_thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )

    external_message_id = discord_message_id_from_sequence(
        await metadata_store.next_compat_sequence("discord", channel_id),
        occurred_at,
    )
    await register_compat_mapping(
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
