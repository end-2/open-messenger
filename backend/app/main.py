from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router as api_router
from app.config import get_settings
from app.errors import build_error_payload
from app.events import EventBus
from app.rate_limit import SlidingWindowRateLimiter
from app.storage import build_storage_registry


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
    del request, exc
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

    app = FastAPI(
        title="Open Messenger API",
        version=settings.api_version,
    )
    app.state.settings = settings
    app.state.content_store = content_store
    app.state.metadata_store = metadata_store
    app.state.file_store = file_store
    app.state.event_bus = EventBus()
    app.state.rate_limiter = SlidingWindowRateLimiter(
        max_requests=settings.rate_limit_max_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )

    @app.middleware("http")
    async def rate_limit_middleware(request: Request, call_next):
        if request.url.path == "/healthz":
            return await call_next(request)

        if not request.url.path.startswith(("/v1", "/admin/v1")):
            return await call_next(request)

        limiter = request.app.state.rate_limiter
        if not limiter.is_enabled():
            return await call_next(request)

        if request.url.path.startswith("/admin/v1"):
            key_value = request.headers.get("x-admin-token", "")
            key_prefix = "admin"
        else:
            auth_header = request.headers.get("authorization", "")
            key_value = auth_header if auth_header.startswith("Bearer ") else ""
            key_prefix = "native"

        if not key_value:
            client_host = request.client.host if request.client is not None else "unknown"
            key_value = client_host
            key_prefix = f"{key_prefix}:ip"

        allowed, retry_after = limiter.check(f"{key_prefix}:{key_value}")
        if allowed:
            return await call_next(request)

        headers = {"Retry-After": str(retry_after or settings.rate_limit_window_seconds)}
        return JSONResponse(
            status_code=429,
            content={
                "code": "rate_limited",
                "message": "Rate limit exceeded",
                "retryable": True,
            },
            headers=headers,
        )

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.include_router(api_router)
    return app


app = create_app()
