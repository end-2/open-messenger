from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/v1/info")
def service_info(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.api_version,
        "environment": settings.environment,
        "content_backend": settings.content_backend,
        "metadata_backend": settings.metadata_backend,
    }
