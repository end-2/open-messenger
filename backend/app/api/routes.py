from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/info")
def service_info(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    content_store = request.app.state.content_store
    metadata_store = request.app.state.metadata_store

    return {
        "service": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "content_backend": settings.content_backend,
        "metadata_backend": settings.metadata_backend,
        "content_store_impl": content_store.__class__.__name__,
        "metadata_store_impl": metadata_store.__class__.__name__,
    }
