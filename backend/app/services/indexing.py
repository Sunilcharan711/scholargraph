"""Atomic vector assignment for new uploads and explicit backfill of existing chunks."""

from time import perf_counter
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk
from app.retrieval.embeddings import EmbeddingProvider, embed_texts


def assign_embeddings(paper: Paper, chunks: list[PaperChunk], provider: EmbeddingProvider) -> None:
    """Generate before assigning anything; caller owns the database transaction."""
    start = perf_counter()
    vectors = embed_texts(provider, [chunk.text for chunk in chunks])
    spec = provider.spec
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = vector
        chunk.embedding_model = spec.key
        chunk.embedding_dimensions = spec.dimensions
    paper.metadata_json = {
        **paper.metadata_json,
        "embedding_model": spec.key,
        "embedding_dimensions": spec.dimensions,
        "embedding_ms": round((perf_counter() - start) * 1000, 3),
    }


def index_paper(paper_id: UUID, session: Session, provider: EmbeddingProvider) -> int:
    """Preserve chunk IDs/text and replace one paper's vectors in one transaction."""
    try:
        paper = session.scalar(select(Paper).where(Paper.id == paper_id).with_for_update())
        if paper is None or paper.processing_status != "ready":
            raise ValueError("Paper not found or not ready for indexing")
        chunks = list(
            session.scalars(
                select(PaperChunk)
                .where(PaperChunk.paper_id == paper_id)
                .order_by(PaperChunk.chunk_index)
                .with_for_update()
            )
        )
        assign_embeddings(paper, chunks, provider)
        session.commit()
        return len(chunks)
    except Exception:
        session.rollback()
        raise
