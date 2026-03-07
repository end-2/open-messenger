from __future__ import annotations

import asyncio
from copy import deepcopy
from threading import Lock
from typing import Any


class EventBus:
    """Simple in-process pub/sub bus for real-time API events."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = Lock()

    async def publish(self, event: dict[str, Any]) -> None:
        payload = deepcopy(event)
        with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            await queue.put(deepcopy(payload))

    async def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(queue)

    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)
