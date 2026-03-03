from __future__ import annotations

from datetime import datetime, timezone


def utc_now_iso8601(timespec: str = "milliseconds") -> str:
    """Return current UTC time in normalized ISO8601 format."""

    return datetime.now(timezone.utc).isoformat(timespec=timespec).replace("+00:00", "Z")


def parse_iso8601_utc(value: str) -> datetime:
    """Parse an ISO8601 value and normalize to timezone-aware UTC datetime."""

    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"

    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None:
        raise ValueError("ISO8601 value must include timezone offset")

    return parsed.astimezone(timezone.utc)


def normalize_iso8601_utc(value: str, timespec: str = "milliseconds") -> str:
    """Normalize an ISO8601 input to canonical UTC string ending with 'Z'."""

    return parse_iso8601_utc(value).isoformat(timespec=timespec).replace("+00:00", "Z")
