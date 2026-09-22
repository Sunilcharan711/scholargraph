"""Opt-in real PostgreSQL migration, vector, and API smoke test in a unique schema."""

import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from embedding_fixtures import TestEmbedder
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import create_app
from app.services.indexing import index_paper


@pytest.mark.postgres
def test_postgres_migrations_and_ingestion(
    tmp_path: Path,
    pdf_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a disposable PostgreSQL database ending in _test.")
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql" or not (url.database or "").endswith("_test"):
        pytest.fail("TEST_DATABASE_URL must reference a PostgreSQL database ending in _test.")
    schema = f"sg_test_{uuid4().hex}"
    engine = create_engine(
        url.set(drivername="postgresql+psycopg"), connect_args={"connect_timeout": 5}
    )
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    migration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    migration.attributes["version_table_schema"] = schema
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        scoped = create_engine(
            url.set(drivername="postgresql+psycopg"),
            connect_args={"options": f"-csearch_path={schema},public", "connect_timeout": 5},
        )
        try:
            with scoped.begin() as connection:
                migration.attributes["connection"] = connection
                command.upgrade(migration, "head")
                assert (
                    connection.scalar(text("SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector")) == 0
                )
                assert not compare_metadata(MigrationContext.configure(connection), Base.metadata)
            config = Settings(_env_file=None, database_url="", upload_dir=tmp_path / "uploads")
            with TestClient(
                create_app(config, sessionmaker(scoped, expire_on_commit=False), TestEmbedder())
            ) as client:
                response = client.post(
                    "/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}
                )
                assert response.status_code == 201, response.text
                paper_id = response.json()["id"]
                assert client.get(f"/api/papers/{paper_id}").json()["chunk_count"] > 0
                search = client.post(
                    "/api/search",
                    json={
                        "query": "retrieval",
                        "paper_ids": [paper_id],
                        "mode": "dense",
                        "top_k": 2,
                    },
                )
                assert search.status_code == 200, search.text
                assert len(search.json()["results"]) == 2
                assert search.json()["results"][0]["similarity_score"] == pytest.approx(1)
                for mode in ("bm25", "hybrid"):
                    result = client.post(
                        "/api/search",
                        json={
                            "query": "retrieval",
                            "mode": mode,
                            "paper_ids": [paper_id],
                            "diagnostics": True,
                        },
                    )
                    assert result.status_code == 200, result.text
                    assert result.json()["results"]
                    assert all(r["paper_id"] == paper_id for r in result.json()["results"])
                # Exercise downgrade with populated vectors, then restore schema and reindex.
                with scoped.begin() as connection:
                    migration.attributes["connection"] = connection
                    command.downgrade(migration, "0001_papers")
                    assert (
                        connection.scalar(
                            text("SELECT count(*) FROM paper_chunks WHERE embedding IS NOT NULL")
                        )
                        == 0
                    )
                    command.upgrade(migration, "head")
                with Session(scoped, expire_on_commit=False) as session:
                    assert index_paper(UUID(paper_id), session, TestEmbedder()) > 0
                assert client.delete(f"/api/papers/{paper_id}").status_code == 204
            with scoped.begin() as connection:
                assert connection.scalar(text("SELECT count(*) FROM paper_chunks")) == 0
                migration.attributes["connection"] = connection
                command.downgrade(migration, "base")
                assert not inspect(connection).has_table("papers", schema=schema)
                command.upgrade(migration, "head")
        finally:
            scoped.dispose()
    finally:
        with engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True, if_exists=True))
        engine.dispose()
        get_settings.cache_clear()
