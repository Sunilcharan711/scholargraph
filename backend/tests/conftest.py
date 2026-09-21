import json
import math
from collections.abc import Iterator
from pathlib import Path
from sqlite3 import Connection
from typing import Any

import pymupdf
import pytest
from embedding_fixtures import TestEmbedder
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.compiler import SQLCompiler
from sqlalchemy.sql.elements import BinaryExpression

from app.core.config import Settings
from app.db.base import Base
from app.main import create_app


@compiles(BinaryExpression, "sqlite")
def sqlite_cosine(expression: BinaryExpression, compiler: SQLCompiler, **kwargs: Any) -> str:
    """Run the actual retrieval statement; only pgvector's operator is substituted in tests."""
    if getattr(expression.operator, "opstring", None) == "<=>":
        return (
            f"test_cosine_distance({compiler.process(expression.left, **kwargs)}, "
            f"{compiler.process(expression.right, **kwargs)})"
        )
    return compiler.visit_binary(expression, **kwargs)


def cosine_distance(left: str | None, right: str | None) -> float | None:
    if left is None or right is None:
        return None
    a, b = json.loads(left), json.loads(right)
    numerator = sum(x * y for x, y in zip(a, b, strict=True))
    return 1 - numerator / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


@pytest.fixture
def pdf_bytes() -> bytes:
    """Generate original text in memory; no copyrighted paper fixtures."""
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 60), "A Small Research Study", fontsize=20)
        page.insert_text((72, 100), "Abstract", fontsize=14)
        page.insert_text(
            (72, 125), "We investigate reliable research retrieval with small datasets."
        )
        page.insert_text((72, 170), "1 Introduction", fontsize=14)
        page.insert_text(
            (72, 195), "Retrieval combines lexical evidence with semantic representations."
        )
        page = document.new_page()
        page.insert_text((72, 60), "2 Methods", fontsize=14)
        page.insert_text(
            (72, 90), "We compare two methods. The experiment uses a tiny synthetic dataset."
        )
        document.set_metadata(
            {"title": "A Small Research Study", "author": "Ada Example; Lee Example"}
        )
        return document.tobytes()


@pytest.fixture
def config(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, database_url="", upload_dir=tmp_path / "uploads")


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection: Connection, record: object) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.create_function("test_cosine_distance", 2, cosine_distance)

    Base.metadata.create_all(engine)
    yield sessionmaker(engine, expire_on_commit=False)
    engine.dispose()


@pytest.fixture
def embedder() -> TestEmbedder:
    return TestEmbedder()


@pytest.fixture
def client(
    config: Settings, session_factory: sessionmaker[Session], embedder: TestEmbedder
) -> Iterator[TestClient]:
    with TestClient(create_app(config, session_factory, embedder)) as test_client:
        yield test_client
