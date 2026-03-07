from __future__ import annotations

import asyncio
from asyncio import Queue, TimeoutError, wait_for
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, WebSocket, status
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.websockets import WebSocketDisconnect

from app.auth import AuthContext, require_scopes
from app.config import Settings, get_settings
from app.domain import Channel, Thread
from app.errors import api_error
from app.observability import check_readiness

from .helpers import (
    authenticate_websocket_token,
    build_file_response,
    format_sse_event,
    get_channel_or_404,
    hydrate_message_response,
    increment_thread_reply,
    new_id,
    publish_event,
    store_message,
    store_uploaded_file,
    utc_now_iso,
)
from .schemas import (
    ChannelResponse,
    BatchCreateMessagesRequest,
    BatchCreateMessagesResponse,
    BatchGetMessagesRequest,
    BatchGetMessagesResponse,
    CreateChannelRequest,
    CreateMessageRequest,
    CreateThreadRequest,
    FileObjectResponse,
    ListChannelsResponse,
    ListMessagesResponse,
    MessageResponse,
    NativeCreateMessageRequest,
    ThreadContextResponse,
    ThreadResponse,
)


router = APIRouter()


async def _cancel_pending_tasks(tasks: set[asyncio.Task[Any]]) -> None:
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _receive_websocket_messages(
    websocket: WebSocket,
    control_queue: "asyncio.Queue[str | None]",
) -> None:
    try:
        while True:
            await control_queue.put(await websocket.receive_text())
    except WebSocketDisconnect:
        await control_queue.put(None)


@router.get("/v1/events/stream")
async def stream_events(
    request: Request,
    _: AuthContext = Depends(require_scopes(["messages:read"])),
) -> StreamingResponse:
    event_bus = request.app.state.event_bus
    queue: Queue[dict[str, Any]] = await event_bus.subscribe()
    request.app.state.metrics.set_subscriber_count("sse", event_bus.subscriber_count())

    async def event_stream():
        yield ": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                request.app.state.metrics.observe_event_delivery(
                    "sse",
                    str(event["type"]),
                    str(event["occurred_at"]),
                )
                yield format_sse_event(event)
        finally:
            await event_bus.unsubscribe(queue)
            request.app.state.metrics.set_subscriber_count("sse", event_bus.subscriber_count())

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.websocket("/v1/events/ws")
async def websocket_events(websocket: WebSocket) -> None:
    try:
        await authenticate_websocket_token(websocket, ["messages:read"])
    except HTTPException as exc:
        detail = exc.detail
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=str(detail))
        return

    await websocket.accept()
    event_bus = websocket.app.state.event_bus
    queue: Queue[dict[str, Any]] = await event_bus.subscribe()
    websocket.app.state.metrics.set_subscriber_count("ws", event_bus.subscriber_count())
    control_queue: asyncio.Queue[str | None] = asyncio.Queue()
    receiver_task = asyncio.create_task(_receive_websocket_messages(websocket, control_queue))

    try:
        while True:
            queue_task = asyncio.create_task(queue.get())
            control_task = asyncio.create_task(control_queue.get())
            done, pending = await asyncio.wait(
                {queue_task, control_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            try:
                if queue_task in done:
                    event = queue_task.result()
                    websocket.app.state.metrics.observe_event_delivery(
                        "ws",
                        str(event["type"]),
                        str(event["occurred_at"]),
                    )
                    await websocket.send_json(event)
                    continue

                message = control_task.result()
                if message is None:
                    return
                if message.strip().lower() == "ping":
                    await websocket.send_json({"type": "pong"})
            finally:
                await _cancel_pending_tasks(pending)
    except WebSocketDisconnect:
        return
    finally:
        receiver_task.cancel()
        await asyncio.gather(receiver_task, return_exceptions=True)
        await event_bus.unsubscribe(queue)
        websocket.app.state.metrics.set_subscriber_count("ws", event_bus.subscriber_count())


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(request: Request) -> JSONResponse:
    ready, details = await check_readiness(request.app)
    return JSONResponse(
        status_code=status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ok" if ready else "error", "checks": details},
    )


@router.get("/metrics")
def metrics(request: Request) -> Response:
    return Response(
        content=generate_latest(request.app.state.metrics.registry),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/v1/info")
def service_info(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    content_store = request.app.state.content_store
    metadata_store = request.app.state.metadata_store
    file_store = request.app.state.file_store

    return {
        "service": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "content_backend": settings.content_backend,
        "metadata_backend": settings.metadata_backend,
        "file_storage_backend": settings.file_storage_backend,
        "content_store_impl": content_store.__class__.__name__,
        "metadata_store_impl": metadata_store.__class__.__name__,
        "file_store_impl": file_store.__class__.__name__,
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
        channel_id=new_id("ch"),
        name=payload.name,
    ).to_dict()
    return await metadata_store.create_channel(channel)


@router.get("/v1/channels", response_model=ListChannelsResponse)
async def list_channels(
    request: Request,
    _: AuthContext = Depends(require_scopes(["channels:read"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    channels = await metadata_store.list_channels()
    return {"items": channels}


@router.get("/v1/channels/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: str,
    request: Request,
    _: AuthContext = Depends(require_scopes(["channels:read"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    return await get_channel_or_404(metadata_store, channel_id)


@router.post(
    "/v1/channels/{channel_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_message(
    channel_id: str,
    payload: NativeCreateMessageRequest,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    await get_channel_or_404(metadata_store, channel_id)

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

    internal_payload = CreateMessageRequest(
        **payload.model_dump(),
        sender_user_id=context.user_id,
    )

    message_response, occurred_at, created = await store_message(
        channel_id=channel_id,
        payload=internal_payload,
        metadata_store=metadata_store,
        content_store=content_store,
    )
    if internal_payload.thread_id is not None and created:
        await increment_thread_reply(metadata_store, internal_payload.thread_id, occurred_at)
    if created:
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": channel_id,
                "thread_id": message_response["thread_id"],
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )
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

    await get_channel_or_404(metadata_store, channel_id)
    stored_messages = await metadata_store.list_channel_messages(channel_id, cursor, limit)

    items: list[dict[str, Any]] = []
    for stored in stored_messages:
        items.append(await hydrate_message_response(stored, metadata_store, content_store))

    next_cursor = None
    if len(stored_messages) == limit:
        next_cursor = str(stored_messages[-1]["message_id"])

    return {
        "items": items,
        "next_cursor": next_cursor,
    }


@router.post("/v1/messages:batchGet", response_model=BatchGetMessagesResponse)
async def batch_get_messages(
    payload: BatchGetMessagesRequest,
    request: Request,
    _: AuthContext = Depends(require_scopes(["messages:read"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    items: list[dict[str, Any]] = []
    not_found_ids: list[str] = []
    for message_id in payload.message_ids:
        stored = await metadata_store.get_message(message_id)
        if stored is None:
            not_found_ids.append(message_id)
            continue
        items.append(await hydrate_message_response(stored, metadata_store, content_store))

    return {
        "items": items,
        "not_found_ids": not_found_ids,
    }


@router.post(
    "/v1/messages:batchCreate",
    response_model=BatchCreateMessagesResponse,
    status_code=status.HTTP_201_CREATED,
)
async def batch_create_messages(
    payload: BatchCreateMessagesRequest,
    request: Request,
    context: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    items: list[dict[str, Any]] = []
    for message in payload.items:
        await get_channel_or_404(metadata_store, message.channel_id)

        if message.thread_id is not None:
            thread = await metadata_store.get_thread(message.thread_id)
            if thread is None:
                raise api_error(
                    status_code=status.HTTP_404_NOT_FOUND,
                    code="thread_not_found",
                    message="Thread not found",
                    retryable=False,
                )
            if str(thread.get("channel_id")) != message.channel_id:
                raise api_error(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    code="thread_channel_mismatch",
                    message="Thread does not belong to the channel",
                    retryable=False,
                )

        internal_payload = CreateMessageRequest(
            **message.model_dump(exclude={"channel_id"}),
            sender_user_id=context.user_id,
        )

        message_response, occurred_at, created = await store_message(
            channel_id=message.channel_id,
            payload=internal_payload,
            metadata_store=metadata_store,
            content_store=content_store,
        )
        if internal_payload.thread_id is not None and created:
            await increment_thread_reply(metadata_store, internal_payload.thread_id, occurred_at)
        if created:
            await publish_event(
                request,
                event_type="message.created",
                occurred_at=occurred_at,
                data={
                    "channel_id": message.channel_id,
                    "thread_id": message_response["thread_id"],
                    "message_id": message_response["message_id"],
                    "sender_user_id": message_response["sender_user_id"],
                    "compat_origin": message_response["compat_origin"],
                    "attachments": message_response["attachments"],
                },
            )
        items.append(message_response)

    return {"items": items}


@router.post(
    "/v1/channels/{channel_id}/threads",
    response_model=ThreadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_thread(
    channel_id: str,
    payload: CreateThreadRequest,
    request: Request,
    response: Response,
    _: AuthContext = Depends(require_scopes(["messages:write"])),
) -> dict[str, Any]:
    metadata_store = request.app.state.metadata_store

    await get_channel_or_404(metadata_store, channel_id)
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

    existing_thread = await metadata_store.get_thread_by_root_message(payload.root_message_id)
    if existing_thread is not None:
        response.status_code = status.HTTP_200_OK
        return existing_thread

    now = utc_now_iso()
    thread = Thread(
        thread_id=new_id("th"),
        channel_id=channel_id,
        root_message_id=payload.root_message_id,
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


@router.get("/v1/threads/{thread_id}/context", response_model=ThreadContextResponse)
async def get_thread_context(
    thread_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    _: AuthContext = Depends(require_scopes(["messages:read"])),
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

    root_message = await metadata_store.get_message(str(thread["root_message_id"]))
    if root_message is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="root_message_not_found",
            message="Root message not found",
            retryable=False,
        )

    replies = await metadata_store.list_thread_messages(
        str(thread["channel_id"]),
        thread_id,
        limit + 1,
    )
    has_more_replies = len(replies) > limit
    visible_replies = replies[:limit]

    return {
        "thread": thread,
        "root_message": await hydrate_message_response(root_message, metadata_store, content_store),
        "replies": [
            await hydrate_message_response(reply, metadata_store, content_store)
            for reply in visible_replies
        ],
        "has_more_replies": has_more_replies,
    }


@router.post(
    "/v1/threads/{thread_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_thread_message(
    thread_id: str,
    payload: NativeCreateMessageRequest,
    request: Request,
    response: Response,
    context: AuthContext = Depends(require_scopes(["messages:write"])),
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
    internal_payload = CreateMessageRequest(
        **payload.model_dump(),
        sender_user_id=context.user_id,
    )
    message_response, occurred_at, created = await store_message(
        channel_id=channel_id,
        payload=internal_payload,
        metadata_store=metadata_store,
        content_store=content_store,
        force_thread_id=thread_id,
    )
    if created:
        await increment_thread_reply(metadata_store, thread_id, occurred_at)
        await publish_event(
            request,
            event_type="message.created",
            occurred_at=occurred_at,
            data={
                "channel_id": channel_id,
                "thread_id": thread_id,
                "message_id": message_response["message_id"],
                "sender_user_id": message_response["sender_user_id"],
                "compat_origin": message_response["compat_origin"],
                "attachments": message_response["attachments"],
            },
        )
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
    file_store = request.app.state.file_store
    stored = await store_uploaded_file(settings, metadata_store, file_store, file, context.user_id)
    await publish_event(
        request,
        event_type="file.uploaded",
        occurred_at=str(stored["created_at"]),
        data={
            "file_id": str(stored["file_id"]),
            "uploader_user_id": str(stored["uploader_user_id"]),
            "filename": str(stored["filename"]),
            "mime_type": str(stored["mime_type"]),
            "size_bytes": int(stored["size_bytes"]),
        },
    )
    return build_file_response(stored)


@router.get("/v1/files/{file_id}")
async def get_file(
    file_id: str,
    request: Request,
    _: AuthContext = Depends(require_scopes(["files:read"])),
) -> FileResponse:
    metadata_store = request.app.state.metadata_store
    file_store = request.app.state.file_store
    file_object = await metadata_store.get_file(file_id)
    if file_object is None:
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message="File not found",
            retryable=False,
        )

    storage_path = str(file_object.get("storage_path", ""))
    if not await file_store.exists(storage_path):
        raise api_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="file_not_found",
            message="File not found",
            retryable=False,
        )

    return FileResponse(
        path=Path(storage_path),
        media_type=str(file_object.get("mime_type") or "application/octet-stream"),
        filename=str(file_object.get("filename") or Path(storage_path).name),
    )
