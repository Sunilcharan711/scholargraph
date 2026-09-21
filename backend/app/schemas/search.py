from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=2000)
    paper_ids: list[UUID] = Field(default_factory=list, max_length=100)
    top_k: int = Field(default=10, ge=1, le=50)
    mode: Literal["dense"] = "dense"

    @field_validator("paper_ids")
    @classmethod
    def unique_ids(cls, values: list[UUID]) -> list[UUID]:
        return list(dict.fromkeys(values))


class SearchResult(BaseModel):
    paper_id: UUID
    title: str
    chunk_id: UUID
    page: int
    section: str | None
    snippet: str
    similarity_score: float = Field(ge=-1, le=1)


class SearchResponse(BaseModel):
    query: str
    mode: Literal["dense"] = "dense"
    results: list[SearchResult]
    embedding_model: str
    embedding_dimensions: int
    indexed_chunk_count: int
    excluded_chunk_count: int
    embedding_ms: float
    retrieval_ms: float
    latency_ms: float
