from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes import router as api_router
from app.config import get_settings
from app.errors import build_error_payload
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
    content_store, metadata_store = build_storage_registry(settings)

    app = FastAPI(
        title="Open Messenger API",
        version=settings.api_version,
    )
    app.state.settings = settings
    app.state.content_store = content_store
    app.state.metadata_store = metadata_store
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _request_validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
    app.include_router(api_router)
    return app


app = create_app()
