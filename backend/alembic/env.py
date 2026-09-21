"""Migration environment. Never print or embed credentials in migration files."""

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.models import Paper, PaperChunk  # noqa: F401

target_metadata = Base.metadata
url = get_settings().database_url.get_secret_value()
if not url:
    raise ValueError("Set DATABASE_URL before running migrations.")


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy.engine import make_url

    supplied_connection = context.config.attributes.get("connection")
    if supplied_connection is not None:
        context.configure(
            connection=supplied_connection,
            target_metadata=target_metadata,
            version_table_schema=context.config.attributes.get("version_table_schema"),
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = engine_from_config(
        {"sqlalchemy.url": make_url(url).set(drivername="postgresql+psycopg")},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
