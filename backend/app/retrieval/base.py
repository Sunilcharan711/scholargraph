"""Shared retrieval contract independent of HTTP response assembly."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from app.schemas.search import RetrievalDiagnostics, SearchRequest


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: UUID
    paper_id: UUID
    title: str
    page: int
    section: str | None
    snippet: str
    score: float
    diagnostics: RetrievalDiagnostics


@dataclass(frozen=True)
class RetrievalBatch:
    hits: list[RetrievalHit]
    indexed_count: int
    excluded_count: int = 0
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    embedding_ms: float = 0
    retrieval_ms: float = 0


class Retriever(Protocol):
    def retrieve(self, session: Session, request: SearchRequest, limit: int) -> RetrievalBatch: ...
