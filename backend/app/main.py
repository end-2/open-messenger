from fastapi import FastAPI

from app.api.routes import router as api_router
from app.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Open Messenger API",
        version=settings.api_version,
    )
    app.state.settings = settings
    app.include_router(api_router)
    return app


app = create_app()
