"""FastAPI application factory and ASGI entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.api.papers import router as papers_router
from app.api.search import router as search_router
from app.core.config import Settings, get_settings
from app.core.errors import IngestionError
from app.core.logging import configure_logging
from app.core.upload_limit import UploadLimitMiddleware
from app.db.session import create_database_engine
from app.retrieval.embeddings import EmbeddingError, EmbeddingProvider
from app.retrieval.sentence_transformer import SentenceTransformerEmbedder
from app.services.chat import AnswerProvider, OllamaProvider

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    embedder: EmbeddingProvider | None = None,
    answer_provider: AnswerProvider | None = None,
) -> FastAPI:
    """Create an app with injectable settings for tests and alternate runtimes."""
    config = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.log_level)
        engine = None
        if session_factory is None:
            engine = create_database_engine(config)
            application.state.session_factory = (
                sessionmaker(engine, expire_on_commit=False) if engine is not None else None
            )
        logger.info("Starting ScholarGraph API")
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()
            logger.info("Stopping ScholarGraph API")

    application = FastAPI(title=config.app_name, version="0.1.0", lifespan=lifespan)
    application.state.settings = config
    application.state.answer_provider = answer_provider or OllamaProvider(config)
    application.state.storage_mode = (
        "postgresql" if config.database_url.get_secret_value() else "unconfigured"
    )
    application.state.session_factory = session_factory
    application.state.embedder = (
        embedder if embedder is not None else SentenceTransformerEmbedder(config)
    )
    application.add_middleware(UploadLimitMiddleware, settings=config)
    application.include_router(health_router, prefix="/api")
    application.include_router(papers_router, prefix="/api")
    application.include_router(search_router, prefix="/api")
    application.include_router(chat_router, prefix="/api")

    @application.exception_handler(EmbeddingError)
    async def embedding_error(request: Request, exc: EmbeddingError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @application.exception_handler(IngestionError)
    async def ingestion_error(request: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.error("Database operation failed (%s)", type(exc).__name__)
        return JSONResponse(
            status_code=503,
            content={"detail": "Database unavailable. Check connection and migrations."},
        )

    @application.exception_handler(OSError)
    async def storage_error(request: Request, exc: OSError) -> JSONResponse:
        logger.error("Storage operation failed (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Upload storage is unavailable."})

    return application


app = create_app()
