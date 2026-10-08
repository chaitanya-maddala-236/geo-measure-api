"""FastAPI application factory and startup configuration."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.files import router as files_router
from app.core.config import Settings
from app.core.exceptions import APIError
from app.core.logging_config import configure_logging
from app.db import models  # noqa: F401 - register models before create_all
from app.db.database import Base, create_database

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an independently configurable GeoMeasure API instance."""
    runtime_settings = settings or Settings()
    configure_logging(runtime_settings.log_level)
    engine, session_factory = create_database(runtime_settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(bind=engine)
        logger.info("GeoMeasure database initialized")
        yield
        engine.dispose()

    application = FastAPI(
        title="GeoMeasure API",
        description=(
            "Upload KML and Shapefile ZIP files and retrieve safe measurements."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    application.state.settings = runtime_settings
    application.state.engine = engine
    application.state.session_factory = session_factory
    application.include_router(files_router)

    @application.exception_handler(APIError)
    async def handle_api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    @application.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Return a simple liveness response."""
        return {"status": "ok"}

    return application


app = create_app()
