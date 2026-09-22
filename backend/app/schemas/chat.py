"""Bounded question answering and deterministic source references."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.search import SearchRequest


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1, max_length=2000)
    paper_ids: list[UUID] = Field(default_factory=list, max_length=100)
    top_k: int = Field(default=6, ge=1, le=12)
    mode: Literal["dense", "bm25", "hybrid"] = "hybrid"

    def search_request(self) -> SearchRequest:
        return SearchRequest(
            query=self.question, paper_ids=self.paper_ids, top_k=self.top_k, mode=self.mode
        )


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    sources: list[int] = Field(min_length=1, max_length=12)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    insufficient_evidence: bool
    claims: list[Claim] = Field(max_length=12)


class Citation(BaseModel):
    source: int
    paper_id: UUID
    paper_title: str
    chunk_id: UUID
    page: int
    section: str | None
    snippet: str
    relevance_score: float


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    insufficient_evidence: bool
    latency_ms: float
    model: str | None
