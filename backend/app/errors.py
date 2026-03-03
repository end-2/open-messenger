from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import HTTPException

_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_STATUS_CODE_MAP = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    413: "payload_too_large",
    422: "validation_error",
    429: "rate_limited",
}


def status_to_error_code(status_code: int) -> str:
    if status_code in _STATUS_CODE_MAP:
        return _STATUS_CODE_MAP[status_code]
    if status_code >= 500:
        return "internal_error"
    return "http_error"


def default_retryable(status_code: int) -> bool:
    return status_code in _RETRYABLE_STATUSES


def build_error_payload(status_code: int, detail: Any) -> dict[str, Any]:
    default_message = HTTPStatus(status_code).phrase if status_code in HTTPStatus._value2member_map_ else "Error"

    if isinstance(detail, dict):
        code = str(detail.get("code") or status_to_error_code(status_code))
        message = str(detail.get("message") or detail.get("detail") or default_message)
        retryable = bool(detail.get("retryable")) if "retryable" in detail else default_retryable(status_code)
        return {
            "code": code,
            "message": message,
            "retryable": retryable,
        }

    message = str(detail) if detail is not None else default_message
    return {
        "code": status_to_error_code(status_code),
        "message": message,
        "retryable": default_retryable(status_code),
    }


def api_error(
    status_code: int,
    code: str,
    message: str,
    retryable: bool,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    )
