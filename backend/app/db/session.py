"""One SQLAlchemy session per request; schema changes belong to Alembic."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine | None:
    url = settings.database_url.get_secret_value()
    if not url:
        return None
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise ValueError("DATABASE_URL must use PostgreSQL")
    return create_engine(
        parsed.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] | None = request.app.state.session_factory
    if factory is None:
        raise HTTPException(503, "Database is not configured. Set DATABASE_URL and run migrations.")
    with factory() as session:
        yield session


def get_config(request: Request) -> Settings:
    return request.app.state.settings


DatabaseSession = Annotated[Session, Depends(get_session)]
AppSettings = Annotated[Settings, Depends(get_config)]
