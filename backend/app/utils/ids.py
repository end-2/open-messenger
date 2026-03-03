from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone

_ULID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LOOKUP = {char: index for index, char in enumerate(_ULID_ALPHABET)}
_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*$")
_MAX_ULID_TIMESTAMP_MS = (1 << 48) - 1


def generate_ulid(timestamp_ms: int | None = None) -> str:
    """Return a canonical ULID string."""

    current_timestamp_ms = (
        int(datetime.now(timezone.utc).timestamp() * 1000)
        if timestamp_ms is None
        else timestamp_ms
    )
    if current_timestamp_ms < 0 or current_timestamp_ms > _MAX_ULID_TIMESTAMP_MS:
        raise ValueError("timestamp_ms is out of ULID range")

    entropy = int.from_bytes(secrets.token_bytes(10), byteorder="big", signed=False)
    ulid_value = (current_timestamp_ms << 80) | entropy

    encoded: list[str] = []
    for _ in range(26):
        encoded.append(_ULID_ALPHABET[ulid_value & 0x1F])
        ulid_value >>= 5
    encoded.reverse()
    return "".join(encoded)


def is_valid_ulid(value: str) -> bool:
    if not _ULID_RE.fullmatch(value):
        return False

    try:
        timestamp_ms = decode_ulid_timestamp_ms(value)
    except ValueError:
        return False

    return 0 <= timestamp_ms <= _MAX_ULID_TIMESTAMP_MS


def decode_ulid_timestamp_ms(value: str) -> int:
    if not _ULID_RE.fullmatch(value):
        raise ValueError("Invalid ULID format")

    ulid_value = 0
    for char in value:
        ulid_value = (ulid_value << 5) | _ULID_LOOKUP[char]
    return ulid_value >> 80


def new_prefixed_ulid(prefix: str) -> str:
    if not _PREFIX_RE.fullmatch(prefix):
        raise ValueError("prefix must be lowercase alphanumeric and start with a letter")
    return f"{prefix}_{generate_ulid()}"


def is_valid_prefixed_ulid(value: str, prefix: str) -> bool:
    if not _PREFIX_RE.fullmatch(prefix):
        return False

    expected = f"{prefix}_"
    if not value.startswith(expected):
        return False

    suffix = value[len(expected) :]
    return is_valid_ulid(suffix)
