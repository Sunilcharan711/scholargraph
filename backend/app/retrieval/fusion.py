"""Rank-only fusion keeps unlike raw score scales separate."""

from dataclasses import replace
from uuid import UUID

from app.retrieval.base import RetrievalHit
from app.schemas.search import RetrievalDiagnostics


def reciprocal_rank_fusion(
    dense: list[RetrievalHit], lexical: list[RetrievalHit], k: int = 60
) -> list[RetrievalHit]:
    """Equal-weight RRF; one contribution per chunk per list, one-based ranks."""
    if k < 1:
        raise ValueError("RRF k must be positive.")
    sources: dict[UUID, RetrievalHit] = {}
    diagnostics: dict[UUID, RetrievalDiagnostics] = {}
    for method, hits in (("dense", dense), ("bm25", lexical)):
        seen: set[UUID] = set()
        for hit in hits:
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            rank = len(seen)
            sources.setdefault(hit.chunk_id, hit)
            detail = diagnostics.setdefault(hit.chunk_id, RetrievalDiagnostics(fused_score=0))
            if method == "dense":
                detail.dense_rank, detail.dense_score = rank, hit.score
            else:
                detail.bm25_rank, detail.bm25_score = rank, hit.score
            detail.fused_score = (detail.fused_score or 0) + 1 / (k + rank)
    fused = [
        replace(hit, score=diagnostics[key].fused_score or 0, diagnostics=diagnostics[key])
        for key, hit in sources.items()
    ]
    return sorted(fused, key=lambda hit: (-hit.score, hit.chunk_id))
