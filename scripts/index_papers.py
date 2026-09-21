"""Explicit backfill/reindex. Run with uv run --project backend python scripts/index_papers.py."""

import argparse
from uuid import UUID

from app.core.config import get_settings
from app.db.session import create_database_engine
from app.models import Paper
from app.retrieval.sentence_transformer import SentenceTransformerEmbedder
from app.services.indexing import index_paper
from sqlalchemy import select
from sqlalchemy.orm import Session


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Index existing chunks, preserving their IDs and text."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--all", action="store_true", help="Reindex every ready paper")
    selection.add_argument(
        "--paper-id", type=UUID, action="append", help="Repeat for multiple papers"
    )
    args = parser.parse_args()
    config = get_settings()
    engine = create_database_engine(config)
    if engine is None:
        parser.error("Set DATABASE_URL and apply migrations first.")
    provider = SentenceTransformerEmbedder(config)
    try:
        with Session(engine, expire_on_commit=False) as session:
            ids = args.paper_id or list(
                session.scalars(
                    select(Paper.id).where(Paper.processing_status == "ready").order_by(Paper.id)
                )
            )
            for paper_id in ids:
                count = index_paper(paper_id, session, provider)
                print(f"Indexed {paper_id}: {count} chunks")
            print(f"Completed: {len(ids)} papers")
        return 0
    except Exception as exc:
        print(
            f"Indexing stopped ({type(exc).__name__}). "
            "Current paper rolled back; prior papers retained."
        )
        return 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
