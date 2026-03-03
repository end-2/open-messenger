from datetime import timezone

import pytest

from app.utils.time import normalize_iso8601_utc, parse_iso8601_utc, utc_now_iso8601


def test_utc_now_iso8601_returns_z_suffix() -> None:
    value = utc_now_iso8601()

    assert value.endswith("Z")
    parsed = parse_iso8601_utc(value)
    assert parsed.tzinfo == timezone.utc


def test_parse_iso8601_utc_normalizes_offset() -> None:
    parsed = parse_iso8601_utc("2026-03-03T12:34:56+09:00")

    assert parsed.isoformat() == "2026-03-03T03:34:56+00:00"


def test_parse_iso8601_utc_requires_timezone() -> None:
    with pytest.raises(ValueError):
        parse_iso8601_utc("2026-03-03T12:34:56")


def test_normalize_iso8601_utc_returns_canonical_z_string() -> None:
    normalized = normalize_iso8601_utc("2026-03-03T12:34:56+09:00", timespec="seconds")

    assert normalized == "2026-03-03T03:34:56Z"
