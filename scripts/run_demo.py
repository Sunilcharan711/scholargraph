"""Run the explicit, persistent SQLite demo on loopback with real local embeddings."""

from pathlib import Path

import uvicorn
from app.core.config import PROJECT_ROOT, Settings
from app.db.demo import demo_engine
from app.main import create_app
from sqlalchemy.orm import sessionmaker


def main():
    config = Settings(upload_dir=PROJECT_ROOT / "data/demo/uploads")
    engine = demo_engine(Path(PROJECT_ROOT / "data/demo/scholargraph.db"))
    app = create_app(config, sessionmaker(engine, expire_on_commit=False))
    app.state.storage_mode = "sqlite-demo"
    try:
        uvicorn.run(app, host="127.0.0.1", port=8000)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
