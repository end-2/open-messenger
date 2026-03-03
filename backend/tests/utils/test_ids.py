import pytest

from app.utils.ids import (
    decode_ulid_timestamp_ms,
    generate_ulid,
    is_valid_prefixed_ulid,
    is_valid_ulid,
    new_prefixed_ulid,
)


def test_generate_ulid_is_canonical_and_decodes_timestamp(monkeypatch) -> None:
    monkeypatch.setattr("app.utils.ids.secrets.token_bytes", lambda _: b"\x00" * 10)

    ulid = generate_ulid(timestamp_ms=1_700_000_000_000)

    assert len(ulid) == 26
    assert ulid.isupper()
    assert is_valid_ulid(ulid)
    assert decode_ulid_timestamp_ms(ulid) == 1_700_000_000_000


def test_generate_ulid_rejects_out_of_range_timestamp() -> None:
    with pytest.raises(ValueError):
        generate_ulid(timestamp_ms=-1)

    with pytest.raises(ValueError):
        generate_ulid(timestamp_ms=1 << 48)


def test_prefixed_ulid_helpers() -> None:
    value = new_prefixed_ulid("msg")

    assert value.startswith("msg_")
    assert is_valid_prefixed_ulid(value, "msg")
    assert not is_valid_prefixed_ulid(value, "th")


def test_ulid_validation_rejects_invalid_values() -> None:
    assert not is_valid_ulid("")
    assert not is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FAI")
    assert not is_valid_ulid("01ARZ3NDEKTSV4RRFFQ69G5FA")


def test_new_prefixed_ulid_requires_lowercase_prefix() -> None:
    with pytest.raises(ValueError):
        new_prefixed_ulid("MSG")
