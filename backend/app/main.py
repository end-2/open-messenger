from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import get_settings
from app.storage import build_storage_registry


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
    app.include_router(api_router)
    return app


app = create_app()
