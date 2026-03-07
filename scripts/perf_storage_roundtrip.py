from __future__ import annotations

import argparse
import statistics
import time
from collections.abc import Callable

import httpx


DEFAULT_SCOPES = [
    "channels:read",
    "channels:write",
    "messages:read",
    "messages:write",
    "files:read",
    "files:write",
]


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * ratio
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _measure(iterations: int, fn: Callable[[], None]) -> list[float]:
    samples: list[float] = []
    for _ in range(iterations):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def _print_stats(name: str, samples: list[float]) -> None:
    ordered = sorted(samples)
    average = statistics.fmean(ordered) if ordered else 0.0
    print(
        f"{name}: avg={average:.2f}ms p50={_percentile(ordered, 0.50):.2f}ms "
        f"p95={_percentile(ordered, 0.95):.2f}ms max={max(ordered, default=0.0):.2f}ms"
    )


def _admin_headers(admin_token: str) -> dict[str, str]:
    return {"X-Admin-Token": admin_token}


def _create_user_token(client: httpx.Client, admin_token: str) -> str:
    user_response = client.post(
        "/admin/v1/users",
        json={"username": "perf-user", "display_name": "Performance User"},
        headers=_admin_headers(admin_token),
    )
    user_response.raise_for_status()
    user_id = user_response.json()["user_id"]

    token_response = client.post(
        "/admin/v1/tokens",
        json={"user_id": user_id, "token_type": "user_token", "scopes": DEFAULT_SCOPES},
        headers=_admin_headers(admin_token),
    )
    token_response.raise_for_status()
    return str(token_response.json()["token"])


def _wait_for_api(client: httpx.Client, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            response = client.get("/healthz")
            if response.status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"API did not become ready within {timeout_seconds:.1f}s")


def _seed_channel(
    client: httpx.Client,
    bearer_token: str,
    *,
    messages: int,
    thread_replies: int,
) -> tuple[str, list[str], str]:
    headers = {"Authorization": f"Bearer {bearer_token}"}
    channel_response = client.post("/v1/channels", json={"name": "perf-channel"}, headers=headers)
    channel_response.raise_for_status()
    channel_id = str(channel_response.json()["channel_id"])

    message_ids: list[str] = []
    root_message_id: str | None = None
    for index in range(messages):
        response = client.post(
            f"/v1/channels/{channel_id}/messages",
            json={
                "text": f"perf-message-{index}",
                "idempotency_key": f"perf-message-{index}",
                "metadata": {"source": "perf-storage-roundtrip"},
            },
            headers=headers,
        )
        response.raise_for_status()
        message_id = str(response.json()["message_id"])
        message_ids.append(message_id)
        if root_message_id is None:
            root_message_id = message_id

    assert root_message_id is not None
    thread_response = client.post(
        f"/v1/channels/{channel_id}/threads",
        json={"root_message_id": root_message_id},
        headers=headers,
    )
    thread_response.raise_for_status()
    thread_id = str(thread_response.json()["thread_id"])

    for index in range(thread_replies):
        reply_response = client.post(
            f"/v1/threads/{thread_id}/messages",
            json={
                "text": f"perf-reply-{index}",
                "idempotency_key": f"perf-reply-{index}",
            },
            headers=headers,
        )
        reply_response.raise_for_status()

    return channel_id, message_ids, thread_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark storage-heavy API read paths.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-token", default="dev-admin-token")
    parser.add_argument("--messages", type=int, default=250)
    parser.add_argument("--thread-replies", type=int, default=100)
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--startup-timeout", type=float, default=10.0)
    args = parser.parse_args()

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        _wait_for_api(client, args.startup_timeout)
        bearer_token = _create_user_token(client, args.admin_token)
        channel_id, message_ids, thread_id = _seed_channel(
            client,
            bearer_token,
            messages=args.messages,
            thread_replies=args.thread_replies,
        )
        headers = {"Authorization": f"Bearer {bearer_token}"}

        list_params = {"limit": min(args.page_size, args.messages)}
        batch_ids = message_ids[: min(args.batch_size, len(message_ids))]
        thread_params = {"limit": min(args.page_size, args.thread_replies)}

        def list_messages() -> None:
            response = client.get(
                f"/v1/channels/{channel_id}/messages",
                params=list_params,
                headers=headers,
            )
            response.raise_for_status()

        def batch_get_messages() -> None:
            response = client.post(
                "/v1/messages:batchGet",
                json={"message_ids": batch_ids},
                headers=headers,
            )
            response.raise_for_status()

        def thread_context() -> None:
            response = client.get(
                f"/v1/threads/{thread_id}/context",
                params=thread_params,
                headers=headers,
            )
            response.raise_for_status()

        benchmarks = [
            ("list_channel_messages", list_messages),
            ("batch_get_messages", batch_get_messages),
            ("thread_context", thread_context),
        ]

        print(
            f"Seeded channel={channel_id} messages={len(message_ids)} "
            f"thread_replies={args.thread_replies}"
        )
        for name, bench_fn in benchmarks:
            _measure(args.warmup, bench_fn)
            _print_stats(name, _measure(args.iterations, bench_fn))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
