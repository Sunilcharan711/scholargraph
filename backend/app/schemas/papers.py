from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaperResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    authors: list[str]
    abstract: str | None
    publication_year: int | None
    filename: str
    source_url: str | None
    uploaded_at: datetime
    processing_status: str
    metadata_json: dict[str, Any]


class ChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    paper_id: UUID
    page_number: int
    section_title: str | None
    chunk_index: int
    text: str
    token_count: int
    created_at: datetime


class PaperDetail(PaperResponse):
    chunk_count: int
    chunks: list[ChunkResponse]


class PaperList(BaseModel):
    items: list[PaperResponse]
    total: int
    limit: int
    offset: int
