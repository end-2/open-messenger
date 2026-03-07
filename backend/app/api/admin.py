from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import Settings, get_settings
from app.domain import User
from app.errors import api_error

from .helpers import (
    audit_logger,
    get_channel_or_404,
    issue_admin_token,
    new_id,
    require_admin_access,
    utc_now_iso,
)
from .schemas import CreateTokenRequest, CreateTokenResponse, CreateUserRequest, UserResponse


router = APIRouter()


async def _collect_channel_content_refs(metadata_store: Any, channel_id: str) -> set[str]:
    cursor: str | None = None
    content_refs: set[str] = set()

    while True:
        page = await metadata_store.list_channel_messages(channel_id, cursor=cursor, limit=200)
        if not page:
            break
        content_refs.update(str(message["content_ref"]) for message in page)
        cursor = str(page[-1]["message_id"])
        if len(page) < 200:
            break

    return content_refs


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
        user_id=new_id("usr"),
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

    return await issue_admin_token(
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

    rotated = await issue_admin_token(
        metadata_store,
        settings,
        user_id=str(token["user_id"]),
        token_type=str(token["token_type"]),
        scopes=list(token.get("scopes", [])),
    )
    await metadata_store.update_token(token_id, {"revoked_at": utc_now_iso()})
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
        await metadata_store.update_token(token_id, {"revoked_at": utc_now_iso()})
        audit_logger.info("admin_token_revoked token_id=%s", token_id)
    else:
        audit_logger.info("admin_token_revoke_noop token_id=%s", token_id)

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/admin/v1/channels/{channel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_admin_channel(
    channel_id: str,
    request: Request,
    _: None = Depends(require_admin_access),
) -> Response:
    metadata_store = request.app.state.metadata_store
    content_store = request.app.state.content_store

    await get_channel_or_404(metadata_store, channel_id)
    content_refs = await _collect_channel_content_refs(metadata_store, channel_id)
    await metadata_store.delete_channel(channel_id)
    for content_ref in content_refs:
        await content_store.delete(content_ref)

    audit_logger.info("admin_channel_deleted channel_id=%s deleted_content_refs=%s", channel_id, len(content_refs))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
