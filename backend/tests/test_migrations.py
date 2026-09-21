import os
import subprocess
import sys
from pathlib import Path


def test_postgresql_migration_compiles_offline() -> None:
    backend = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "DATABASE_URL": "postgresql+psycopg://localhost/scholargraph_test"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(backend / "alembic.ini"),
            "upgrade",
            "head",
            "--sql",
        ],
        capture_output=True,
        text=True,
        env=environment,
        check=True,
    )
    assert "CREATE EXTENSION IF NOT EXISTS vector" in result.stdout
    assert "embedding VECTOR" in result.stdout
    assert "ON DELETE CASCADE" in result.stdout
    assert "CREATE TABLE papers" in result.stdout
