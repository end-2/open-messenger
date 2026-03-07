from __future__ import annotations

from collections import deque
from time import monotonic


class SlidingWindowRateLimiter:
    """Simple in-memory sliding window limiter keyed by caller identity."""

    def __init__(
        self,
        *,
        max_requests: int,
        window_seconds: int,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = {}

    def is_enabled(self) -> bool:
        return self.max_requests > 0 and self.window_seconds > 0

    def check(self, key: str) -> tuple[bool, int | None]:
        if not self.is_enabled():
            return True, None

        now = monotonic()
        window_start = now - float(self.window_seconds)
        bucket = self._buckets.setdefault(key, deque())

        while bucket and bucket[0] <= window_start:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            retry_after = max(1, int(bucket[0] + float(self.window_seconds) - now))
            return False, retry_after

        bucket.append(now)
        return True, None
