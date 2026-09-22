"""Exact cosine retrieval in PostgreSQL with embedding-space and paper filters."""

from time import perf_counter

from sqlalchemy import Select, and_, case, func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import BooleanClauseList

from app.models import Paper, PaperChunk
from app.retrieval.base import RetrievalBatch, RetrievalHit
from app.retrieval.embeddings import EmbeddingProvider, EmbeddingSpec, embed_texts
from app.schemas.search import RetrievalDiagnostics, SearchRequest


def matching_space(spec: EmbeddingSpec) -> BooleanClauseList:
    return and_(
        PaperChunk.embedding.is_not(None),
        PaperChunk.embedding_model == spec.key,
        PaperChunk.embedding_dimensions == spec.dimensions,
    )


def dense_statement(
    request: SearchRequest, spec: EmbeddingSpec, vector: list[float], limit: int | None = None
) -> Select:
    compatible = matching_space(spec)
    # CASE prevents distance evaluation on a different-dimensional vector even if
    # PostgreSQL reorders evaluation. WHERE also narrows rows via the space index.
    guarded_vector = case((compatible, PaperChunk.embedding), else_=None)
    distance = guarded_vector.cosine_distance(vector).label("distance")
    statement = (
        select(
            PaperChunk.id,
            PaperChunk.paper_id,
            Paper.title,
            PaperChunk.page_number,
            PaperChunk.section_title,
            PaperChunk.text,
            distance,
        )
        .join(Paper, Paper.id == PaperChunk.paper_id)
        .where(Paper.processing_status == "ready", compatible)
        .order_by(distance, PaperChunk.id)
        .limit(limit if limit is not None else request.top_k)
    )
    if request.paper_ids:
        statement = statement.where(PaperChunk.paper_id.in_(request.paper_ids))
    return statement


def dense_retrieve(
    session: Session, provider: EmbeddingProvider, request: SearchRequest, limit: int
) -> RetrievalBatch:
    start = perf_counter()
    vector = embed_texts(provider, [request.query])[0]
    spec = provider.spec
    embedding_ms = (perf_counter() - start) * 1000
    retrieval_start = perf_counter()
    scope = (
        select(func.count(), func.count().filter(matching_space(spec)))
        .select_from(PaperChunk)
        .join(Paper)
        .where(Paper.processing_status == "ready")
    )
    if request.paper_ids:
        scope = scope.where(PaperChunk.paper_id.in_(request.paper_ids))
    total, indexed = session.execute(scope).one()
    rows = session.execute(dense_statement(request, spec, vector, limit)).all()
    hits = [
        RetrievalHit(
            paper_id=row.paper_id,
            title=row.title,
            chunk_id=row.id,
            page=row.page_number,
            section=row.section_title,
            snippet=row.text[:1200],
            score=max(-1.0, min(1.0, 1.0 - row.distance)),
            diagnostics=RetrievalDiagnostics(
                dense_rank=rank, dense_score=max(-1.0, min(1.0, 1.0 - row.distance))
            ),
        )
        for rank, row in enumerate(rows, start=1)
    ]
    return RetrievalBatch(
        hits=hits,
        embedding_model=spec.key,
        embedding_dimensions=spec.dimensions,
        indexed_count=indexed,
        excluded_count=total - indexed,
        embedding_ms=embedding_ms,
        retrieval_ms=(perf_counter() - retrieval_start) * 1000,
    )


class DenseRetriever:
    def __init__(self, provider: EmbeddingProvider) -> None:
        self.provider = provider

    def retrieve(self, session: Session, request: SearchRequest, limit: int) -> RetrievalBatch:
        return dense_retrieve(session, self.provider, request, limit)
