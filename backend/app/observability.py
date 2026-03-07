from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pymysql
from fastapi import Request
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
from redis.exceptions import RedisError

from app.config import Settings
from app.storage.blob import LocalFileBinaryStore
from app.storage.factory import (
    UnsupportedFileBinaryStore,
    UnsupportedMessageContentStore,
    UnsupportedMetadataStore,
)
from app.storage.file import FileMessageContentStore, FileMetadataStore
from app.storage.memory import InMemoryMessageContentStore, InMemoryMetadataStore
from app.storage.mysql_store import MySQLMetadataStore
from app.storage.redis_store import RedisMessageContentStore


_request_id_context: ContextVar[str] = ContextVar("open_messenger_request_id", default="-")
_logging_configured = False


def get_request_id() -> str:
    return _request_id_context.get()


def bind_request_id(request_id: str) -> Token[str]:
    return _request_id_context.set(request_id)


def unbind_request_id(token: Token[str]) -> None:
    _request_id_context.reset(token)


class JsonLogFormatter(logging.Formatter):
    """Render logs as newline-delimited JSON for easier ingestion."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "client_ip",
            "event_type",
            "transport",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_logging() -> None:
    global _logging_configured
    if _logging_configured:
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True

    _logging_configured = True


def configure_tracing(app: Any, settings: Settings) -> None:
    if not settings.tracing_enabled:
        return

    resource = Resource.create({"service.name": settings.tracing_service_name})
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otlp_traces_endpoint),
        )
    )
    trace.set_tracer_provider(tracer_provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)
    app.state.tracer_provider = tracer_provider


def resolve_path_template(request: Request) -> str:
    route = request.scope.get("route")
    path_template = getattr(route, "path", None)
    if isinstance(path_template, str) and path_template:
        return path_template
    return request.url.path


def event_lag_seconds(occurred_at: str) -> float:
    normalized = occurred_at.replace("Z", "+00:00")
    event_time = datetime.fromisoformat(normalized)
    return max(0.0, (datetime.now(timezone.utc) - event_time).total_seconds())


@dataclass
class ObservabilityMetrics:
    registry: CollectorRegistry
    http_requests_total: Counter
    http_request_errors_total: Counter
    http_request_duration_seconds: Histogram
    realtime_active_subscribers: Gauge
    message_events_total: Counter
    events_published_total: Counter
    event_delivery_lag_seconds: Histogram

    @classmethod
    def create(cls) -> "ObservabilityMetrics":
        registry = CollectorRegistry(auto_describe=True)
        return cls(
            registry=registry,
            http_requests_total=Counter(
                "open_messenger_http_requests_total",
                "Total number of HTTP requests.",
                labelnames=("method", "path", "status_code"),
                registry=registry,
            ),
            http_request_errors_total=Counter(
                "open_messenger_http_request_errors_total",
                "Total number of HTTP requests returning 4xx or 5xx responses.",
                labelnames=("method", "path", "status_code"),
                registry=registry,
            ),
            http_request_duration_seconds=Histogram(
                "open_messenger_http_request_duration_seconds",
                "HTTP request latency in seconds.",
                labelnames=("method", "path"),
                buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
                registry=registry,
            ),
            realtime_active_subscribers=Gauge(
                "open_messenger_realtime_active_subscribers",
                "Current number of active realtime subscribers by transport.",
                labelnames=("transport",),
                registry=registry,
            ),
            message_events_total=Counter(
                "open_messenger_message_events_total",
                "Total number of message.created events published by origin.",
                labelnames=("origin",),
                registry=registry,
            ),
            events_published_total=Counter(
                "open_messenger_events_published_total",
                "Total number of published events by type.",
                labelnames=("event_type",),
                registry=registry,
            ),
            event_delivery_lag_seconds=Histogram(
                "open_messenger_event_delivery_lag_seconds",
                "Lag between event creation and delivery to realtime consumers.",
                labelnames=("transport", "event_type"),
                buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
                registry=registry,
            ),
        )

    def observe_http_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        status_code_label = str(status_code)
        self.http_requests_total.labels(method=method, path=path, status_code=status_code_label).inc()
        self.http_request_duration_seconds.labels(method=method, path=path).observe(duration_seconds)
        if status_code >= 400:
            self.http_request_errors_total.labels(
                method=method,
                path=path,
                status_code=status_code_label,
            ).inc()

    def observe_event_published(self, event_type: str, *, origin: str | None = None) -> None:
        self.events_published_total.labels(event_type=event_type).inc()
        if event_type == "message.created":
            self.message_events_total.labels(origin=origin or "unknown").inc()

    def set_subscriber_count(self, transport: str, count: int) -> None:
        self.realtime_active_subscribers.labels(transport=transport).set(count)

    def observe_event_delivery(self, transport: str, event_type: str, occurred_at: str) -> None:
        self.event_delivery_lag_seconds.labels(
            transport=transport,
            event_type=event_type,
        ).observe(event_lag_seconds(occurred_at))


async def check_readiness(app: Any) -> tuple[bool, dict[str, dict[str, str]]]:
    content_store = app.state.content_store
    metadata_store = app.state.metadata_store
    file_store = app.state.file_store

    details = {
        "content_store": await _check_content_store(content_store),
        "metadata_store": await _check_metadata_store(metadata_store),
        "file_store": await _check_file_store(file_store),
    }
    ok = all(item["status"] == "ok" for item in details.values())
    return ok, details


async def _check_content_store(store: Any) -> dict[str, str]:
    if isinstance(store, InMemoryMessageContentStore):
        return {"status": "ok", "backend": "memory"}
    if isinstance(store, FileMessageContentStore):
        base_dir = getattr(store, "_base_dir", None)
        if base_dir is not None and base_dir.exists() and base_dir.is_dir():
            return {"status": "ok", "backend": "file"}
        return {"status": "error", "backend": "file", "reason": "content directory unavailable"}
    if isinstance(store, RedisMessageContentStore):
        client = getattr(store, "_client", None)
        try:
            await asyncio.to_thread(client.ping)
        except (AttributeError, RedisError, OSError):
            return {"status": "error", "backend": "redis", "reason": "redis ping failed"}
        return {"status": "ok", "backend": "redis"}
    if isinstance(store, UnsupportedMessageContentStore):
        return {"status": "error", "backend": store.backend_name, "reason": "unsupported backend"}
    return {"status": "error", "backend": type(store).__name__, "reason": "unknown store"}


async def _check_metadata_store(store: Any) -> dict[str, str]:
    if isinstance(store, InMemoryMetadataStore):
        return {"status": "ok", "backend": "memory"}
    if isinstance(store, FileMetadataStore):
        db_path = getattr(store, "_db_path", None)
        parent_dir = db_path.parent if db_path is not None else None
        if parent_dir is not None and parent_dir.exists() and parent_dir.is_dir():
            return {"status": "ok", "backend": "file"}
        return {"status": "error", "backend": "file", "reason": "metadata path unavailable"}
    if isinstance(store, MySQLMetadataStore):
        settings = getattr(store, "_settings", None)
        try:
            await asyncio.to_thread(_ping_mysql, settings)
        except (AttributeError, OSError, pymysql.MySQLError, ValueError):
            return {"status": "error", "backend": "mysql", "reason": "mysql ping failed"}
        return {"status": "ok", "backend": "mysql"}
    if isinstance(store, UnsupportedMetadataStore):
        return {"status": "error", "backend": store.backend_name, "reason": "unsupported backend"}
    return {"status": "error", "backend": type(store).__name__, "reason": "unknown store"}


async def _check_file_store(store: Any) -> dict[str, str]:
    if isinstance(store, LocalFileBinaryStore):
        root_dir = getattr(store, "_root_dir", None)
        if root_dir is not None and root_dir.exists() and root_dir.is_dir():
            return {"status": "ok", "backend": "local"}
        return {"status": "error", "backend": "local", "reason": "file root unavailable"}
    if isinstance(store, UnsupportedFileBinaryStore):
        return {"status": "error", "backend": store.backend_name, "reason": "unsupported backend"}
    return {"status": "error", "backend": type(store).__name__, "reason": "unknown store"}


def _ping_mysql(settings: Any) -> None:
    if settings is None:
        raise ValueError("missing MySQL settings")

    connection = pymysql.connect(
        host=settings.host,
        port=settings.port,
        user=settings.user,
        password=settings.password,
        database=settings.database,
        connect_timeout=2,
        read_timeout=2,
        write_timeout=2,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    finally:
        connection.close()


def make_request_id() -> str:
    return f"req-{time.time_ns():x}-{os.getpid():x}"
