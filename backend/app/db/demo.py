"""Explicit local-demo adapter, not PostgreSQL/pgvector verification or production storage."""

import json
import math
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.elements import BinaryExpression

from app.db.base import Base


@compiles(BinaryExpression, "sqlite")
def sqlite_cosine(expression, compiler, **kwargs):
    if getattr(expression.operator, "opstring", None) == "<=>":
        return (
            f"demo_cosine_distance({compiler.process(expression.left, **kwargs)}, "
            f"{compiler.process(expression.right, **kwargs)})"
        )
    return compiler.visit_binary(expression, **kwargs)


def cosine_distance(left, right):
    if left is None or right is None:
        return None
    a, b = json.loads(left), json.loads(right)
    norm = math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))
    if not norm or len(a) != len(b):
        return None
    return 1 - sum(x * y for x, y in zip(a, b, strict=True)) / norm


def demo_engine(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path.as_posix()}", connect_args={"timeout": 30})

    @event.listens_for(engine, "connect")
    def setup(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.create_function("demo_cosine_distance", 2, cosine_distance)

    Base.metadata.create_all(engine)
    return engine
