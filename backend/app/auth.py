from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings


@dataclass(frozen=True)
class AuthContext:
    token_id: str
    user_id: str
    token_type: str
    scopes: list[str]
    raw_token: str


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode((encoded + padding).encode("utf-8"))


def sha256_hexdigest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_jwt_like_token(payload: dict[str, Any], signing_secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT-LIKE"}
    header_part = _b64url_encode(
        json.dumps(header, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )
    payload_part = _b64url_encode(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    )
    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    signature_part = _b64url_encode(signature)
    return f"{header_part}.{payload_part}.{signature_part}"


def decode_and_verify_jwt_like_token(token: str, signing_secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header_part, payload_part, signature_part = parts

    signing_input = f"{header_part}.{payload_part}".encode("utf-8")
    expected_signature = hmac.new(
        signing_secret.encode("utf-8"),
        signing_input,
        digestmod=hashlib.sha256,
    ).digest()
    presented_signature = _b64url_decode(signature_part)

    if not hmac.compare_digest(expected_signature, presented_signature):
        raise ValueError("Invalid token signature")

    header = json.loads(_b64url_decode(header_part))
    payload = json.loads(_b64url_decode(payload_part))

    if header.get("alg") != "HS256" or header.get("typ") != "JWT-LIKE":
        raise ValueError("Unsupported token header")

    if not isinstance(payload, dict):
        raise ValueError("Invalid token payload")

    return payload


def _scope_allows(granted_scopes: list[str], required_scope: str) -> bool:
    if "*" in granted_scopes or required_scope in granted_scopes:
        return True
    if ":" in required_scope:
        namespace = required_scope.split(":", 1)[0]
        if f"{namespace}:*" in granted_scopes:
            return True
    return False


async def authenticate_bearer_token(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> AuthContext:
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    raw_token = auth_header[len("Bearer ") :].strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )

    try:
        payload = decode_and_verify_jwt_like_token(raw_token, settings.token_signing_secret)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        ) from None

    token_id = str(payload.get("tid", ""))
    user_id = str(payload.get("sub", ""))
    token_type = str(payload.get("token_type", ""))
    payload_scopes = payload.get("scopes", [])
    if not token_id or not user_id or not token_type or not isinstance(payload_scopes, list):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )

    metadata_store = request.app.state.metadata_store
    stored_token = await metadata_store.get_token(token_id)
    if stored_token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )
    if stored_token.get("revoked_at") is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
        )

    if stored_token.get("token_hash") != sha256_hexdigest(raw_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )

    stored_user_id = str(stored_token.get("user_id", ""))
    stored_token_type = str(stored_token.get("token_type", ""))
    stored_scopes = stored_token.get("scopes", [])
    if (
        stored_user_id != user_id
        or stored_token_type != token_type
        or not isinstance(stored_scopes, list)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token",
        )

    return AuthContext(
        token_id=token_id,
        user_id=user_id,
        token_type=token_type,
        scopes=[str(scope) for scope in stored_scopes],
        raw_token=raw_token,
    )


def require_scopes(required_scopes: list[str]):
    async def dependency(context: AuthContext = Depends(authenticate_bearer_token)) -> AuthContext:
        for required_scope in required_scopes:
            if not _scope_allows(context.scopes, required_scope):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Missing required scope: {required_scope}",
                )
        return context

    return dependency
