"""Paper ingestion and paginated collection/detail endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select

from app.db.session import AppSettings, DatabaseSession
from app.models import Paper, PaperChunk
from app.retrieval.dependencies import Embedder
from app.schemas.papers import ChunkResponse, PaperDetail, PaperList, PaperResponse
from app.services.papers import delete_paper, ingest_paper

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post("/upload", response_model=PaperResponse, status_code=201)
def upload_paper(
    file: UploadFile, session: DatabaseSession, config: AppSettings, embedder: Embedder
) -> Paper:
    """Upload one PDF per request; send multiple requests for a collection."""
    return ingest_paper(file, session, config, embedder)


@router.get("", response_model=PaperList)
def list_papers(
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PaperList:
    papers = session.scalars(
        select(Paper)
        .order_by(Paper.uploaded_at.desc(), Paper.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return PaperList(
        items=[PaperResponse.model_validate(paper) for paper in papers],
        total=session.scalar(select(func.count()).select_from(Paper)) or 0,
        limit=limit,
        offset=offset,
    )


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(
    paper_id: UUID,
    session: DatabaseSession,
    chunk_limit: Annotated[int, Query(ge=1, le=100)] = 20,
    chunk_offset: Annotated[int, Query(ge=0)] = 0,
) -> PaperDetail:
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise HTTPException(404, "Paper not found.")
    chunks = session.scalars(
        select(PaperChunk)
        .where(PaperChunk.paper_id == paper_id)
        .order_by(PaperChunk.chunk_index)
        .limit(chunk_limit)
        .offset(chunk_offset)
    ).all()
    count = (
        session.scalar(
            select(func.count()).select_from(PaperChunk).where(PaperChunk.paper_id == paper_id)
        )
        or 0
    )
    return PaperDetail(
        **PaperResponse.model_validate(paper).model_dump(),
        chunk_count=count,
        chunks=[ChunkResponse.model_validate(chunk) for chunk in chunks],
    )


@router.delete("/{paper_id}", status_code=204)
def remove_paper(paper_id: UUID, session: DatabaseSession, config: AppSettings) -> Response:
    if not delete_paper(paper_id, session, config):
        raise HTTPException(404, "Paper not found.")
    return Response(status_code=204)
