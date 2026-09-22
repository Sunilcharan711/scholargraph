"""Small-corpus BM25 with positive IDF and fresh selected-corpus statistics."""

import math
import re
import unicodedata
from collections import Counter
from collections.abc import Sequence
from time import perf_counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Paper, PaperChunk
from app.retrieval.base import RetrievalBatch, RetrievalHit
from app.schemas.search import RetrievalDiagnostics, SearchRequest


def tokenize(text: str) -> list[str]:
    """Normalize Unicode and case; punctuation separates technical terms."""
    return re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold())


def bm25_scores(
    query: str, documents: Sequence[str], k1: float = 1.5, b: float = 0.75
) -> list[float]:
    """Okapi BM25 with log(1+(N-df+0.5)/(df+0.5)) and binary query-term weights."""
    if not math.isfinite(k1) or k1 <= 0 or not math.isfinite(b) or not 0 <= b <= 1:
        raise ValueError("BM25 requires finite k1 > 0 and b in [0, 1].")
    terms = set(tokenize(query))
    counts = [Counter(tokenize(document)) for document in documents]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / len(lengths) if lengths else 0
    if not terms or average == 0:
        return [0.0] * len(documents)
    frequencies = Counter(term for count in counts for term in terms if term in count)
    inverse = {
        term: math.log1p((len(documents) - df + 0.5) / (df + 0.5))
        for term, df in frequencies.items()
    }
    scores = []
    for count, length in zip(counts, lengths, strict=True):
        normalization = k1 * (1 - b + b * length / average)
        scores.append(
            math.fsum(
                inverse[term] * count[term] * (k1 + 1) / (count[term] + normalization)
                for term in sorted(inverse)
                if count[term]
            )
        )
    return scores


class BM25Retriever:
    def retrieve(self, session: Session, request: SearchRequest, limit: int) -> RetrievalBatch:
        start = perf_counter()
        statement = (
            select(
                PaperChunk.id,
                PaperChunk.paper_id,
                Paper.title,
                PaperChunk.page_number,
                PaperChunk.section_title,
                PaperChunk.text,
            )
            .join(Paper)
            .where(Paper.processing_status == "ready")
        )
        if request.paper_ids:
            statement = statement.where(PaperChunk.paper_id.in_(request.paper_ids))
        rows = session.execute(statement).all()
        scores = bm25_scores(request.query, [row.text for row in rows])
        ranked = sorted(
            ((row, score) for row, score in zip(rows, scores, strict=True) if score > 0),
            key=lambda item: (-item[1], item[0].id),
        )[:limit]
        hits = [
            RetrievalHit(
                chunk_id=row.id,
                paper_id=row.paper_id,
                title=row.title,
                page=row.page_number,
                section=row.section_title,
                snippet=row.text[:1200],
                score=score,
                diagnostics=RetrievalDiagnostics(bm25_rank=rank, bm25_score=score),
            )
            for rank, (row, score) in enumerate(ranked, start=1)
        ]
        return RetrievalBatch(
            hits=hits, indexed_count=len(rows), retrieval_ms=(perf_counter() - start) * 1000
        )
