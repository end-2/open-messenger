import logging
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router as api_router
from app.config import get_settings
from app.errors import build_error_payload
from app.events import EventBus
from app.observability import (
    ObservabilityMetrics,
    bind_request_id,
    configure_logging,
    configure_tracing,
    make_request_id,
    resolve_path_template,
    unbind_request_id,
)
from app.rate_limit import SlidingWindowRateLimiter
from app.storage import build_storage_registry

logger = logging.getLogger("open_messenger.http")


async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    del request
    return JSONResponse(
        status_code=exc.status_code,
        content=build_error_payload(exc.status_code, exc.detail),
    )


async def _request_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    del request
    first_error = exc.errors()[0] if exc.errors() else {}
    message = str(first_error.get("msg") or "Invalid request")
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": message,
            "retryable": False,
        },
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "unhandled_exception",
        exc_info=exc,
        extra={
            "method": request.method,
            "path": request.url.path,
            "status_code": 500,
        },
    )
    return JSONResponse(
        status_code=500,
        content={
            "code": "internal_error",
            "message": "Internal server error",
            "retryable": True,
        },
    )


def create_app() -> FastAPI:
    settings = get_settings()
    content_store, metadata_store, file_store = build_storage_registry(settings)
    configure_logging()

    app = FastAPI(
        title="Open Messenger API",
        version=settings.api_version,
    )
    app.state.settings = settings
    app.state.content_store = content_store
    app.state.metadata_store = metadata_store
    app.state.file_store = file_store
    app.state.event_bus = EventBus()
    app.state.metrics = ObservabilityMetrics.create()
    app.state.rate_limiter = SlidingWindowRateLimiter(
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    configure_tracing(app, settings)

    @app.middleware("http")
    async def observability_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id", "").strip() or make_request_id()
        request.state.request_id = request_id
        token = bind_request_id(request_id)
        started_at = perf_counter()
        response = None
        status_code = 500
        client_ip = request.client.host if request.client is not None else "unknown"

        try:
            if (
                request.url.path not in {"/healthz", "/readyz", "/metrics"}
                and request.url.path.startswith(("/v1", "/admin/v1"))
            ):
                limiter = request.app.state.rate_limiter
                if limiter.is_enabled():
                    if request.url.path.startswith("/admin/v1"):
                        key_value = request.headers.get("x-admin-token", "")
                        key_prefix = "admin"
                    else:
                        auth_header = request.headers.get("authorization", "")
                        key_value = auth_header if auth_header.startswith("Bearer ") else ""
                        key_prefix = "native"

                    if not key_value:
                        key_value = client_ip
                        key_prefix = f"{key_prefix}:ip"

                    allowed, retry_after = limiter.check(f"{key_prefix}:{key_value}")
                    if not allowed:
                        response = JSONResponse(
                            status_code=429,
                            content={
                                "code": "rate_limited",
                                "message": "Rate limit exceeded",
                                "retryable": True,
                            },
                            headers={
                                "Retry-After": str(
                                    retry_after or settings.rate_limit_window_seconds
                                )
                            },
                        )
                        status_code = response.status_code
                        return response

            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_seconds = perf_counter() - started_at
            path_template = resolve_path_template(request)
            request.app.state.metrics.observe_http_request(
                method=request.method,
                path=path_template,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )
            logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": path_template,
                    "status_code": status_code,
                    "duration_ms": round(duration_seconds * 1000, 3),
                    "client_ip": client_ip,
                },
            )
            if response is not None:
                response.headers["x-request-id"] = request_id
            unbind_request_id(token)

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.include_router(api_router)
    return app


app = create_app()
