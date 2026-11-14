"""Search orchestration shared by the API and future RAG evidence retrieval."""

from time import perf_counter

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.retrieval.base import RetrievalBatch, Retriever
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.dense import DenseRetriever
from app.retrieval.embeddings import EmbeddingProvider
from app.retrieval.fusion import reciprocal_rank_fusion
from app.retrieval.reranker import Reranker, rerank_hits
from app.schemas.search import SearchRequest, SearchResponse, SearchResult


def search_papers(
    session: Session,
    provider: EmbeddingProvider,
    request: SearchRequest,
    settings: Settings,
    reranker: Reranker | None = None,
) -> SearchResponse:
    start = perf_counter()
    if request.rerank and reranker is None:
        raise HTTPException(503, "Reranker is not configured.")
    dense: Retriever = DenseRetriever(provider)
    lexical: Retriever = BM25Retriever()
    limit = (
        max(request.top_k, settings.search_candidate_limit)
        if request.mode == "hybrid"
        else request.top_k
    )
    rerank_limit = max(request.top_k, settings.reranker_candidate_limit)
    if request.rerank:
        limit = max(limit, rerank_limit)
    dense_batch = RetrievalBatch([], 0)
    lexical_batch = RetrievalBatch([], 0)
    fusion_ms = 0.0
    if request.mode in {"dense", "hybrid"}:
        dense_batch = dense.retrieve(session, request, limit)
    if request.mode in {"bm25", "hybrid"}:
        lexical_batch = lexical.retrieve(session, request, limit)
    if request.mode == "hybrid":
        fusion_start = perf_counter()
        hits = reciprocal_rank_fusion(dense_batch.hits, lexical_batch.hits, settings.rrf_k)
        fusion_ms = (perf_counter() - fusion_start) * 1000
    else:
        hits = dense_batch.hits if request.mode == "dense" else lexical_batch.hits
    rerank_ms, reranked_count, reranker_model = 0.0, 0, None
    if request.rerank:
        assert reranker is not None
        rerank_start = perf_counter()
        hits = rerank_hits(session, request.query, hits[:rerank_limit], reranker)
        reranked_count = len(hits)
        reranker_model = reranker.identity if hits else None
        rerank_ms = (perf_counter() - rerank_start) * 1000
    batch = lexical_batch if request.mode == "bm25" else dense_batch
    results = [
        SearchResult(
            paper_id=hit.paper_id,
            title=hit.title,
            chunk_id=hit.chunk_id,
            page=hit.page,
            section=hit.section,
            snippet=hit.snippet,
            score=hit.score,
            score_type="cross_encoder"
            if request.rerank
            else {"dense": "cosine", "bm25": "bm25", "hybrid": "rrf"}[request.mode],
            similarity_score=hit.diagnostics.dense_score if request.mode == "dense" else None,
            diagnostics=hit.diagnostics if request.diagnostics else None,
        )
        for hit in hits[: request.top_k]
    ]
    return SearchResponse(
        query=request.query,
        mode=request.mode,
        results=results,
        embedding_model=batch.embedding_model,
        embedding_dimensions=batch.embedding_dimensions,
        indexed_chunk_count=batch.indexed_count,
        excluded_chunk_count=batch.excluded_count,
        embedding_ms=round(dense_batch.embedding_ms, 3),
        retrieval_ms=round(dense_batch.retrieval_ms + lexical_batch.retrieval_ms + fusion_ms, 3),
        latency_ms=round((perf_counter() - start) * 1000, 3),
        dense_ms=round(dense_batch.retrieval_ms, 3),
        bm25_ms=round(lexical_batch.retrieval_ms, 3),
        fusion_ms=round(fusion_ms, 3),
        candidate_limit=limit,
        rerank_ms=round(rerank_ms, 3),
        reranked_count=reranked_count,
        reranker_model=reranker_model,
        rrf_k=settings.rrf_k if request.mode == "hybrid" else None,
    )
