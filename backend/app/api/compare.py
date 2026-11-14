from time import perf_counter

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.db.session import AppSettings, DatabaseSession
from app.models import Paper
from app.retrieval.dependencies import Embedder
from app.schemas.chat import ChatRequest
from app.schemas.compare import QUESTIONS, CompareRequest, CompareResponse, ComparisonCell
from app.services.chat import answer_question
from app.services.comparison_evidence import ComparisonEvidence

router = APIRouter(tags=["comparison"])


@router.post("/compare", response_model=CompareResponse)
def compare(
    body: CompareRequest,
    request: Request,
    session: DatabaseSession,
    config: AppSettings,
    embedder: Embedder,
) -> CompareResponse:
    start = perf_counter()
    papers = {
        p.id: p
        for p in session.scalars(
            select(Paper).where(Paper.id.in_(body.paper_ids), Paper.processing_status == "ready")
        )
    }
    if len(papers) != len(body.paper_ids):
        raise HTTPException(404, "One or more selected papers are unavailable.")
    cells = []
    provider = request.app.state.answer_provider
    if body.dimension in ("findings", "methodology"):
        provider = ComparisonEvidence(provider, body.dimension)
    for paper_id in body.paper_ids:
        cell = ComparisonCell(paper_id=paper_id, title=papers[paper_id].title)
        try:
            cell.answer = answer_question(
                session,
                embedder,
                provider,
                ChatRequest(
                    question=QUESTIONS[body.dimension],
                    paper_ids=[paper_id],
                    top_k=4,
                    mode=body.mode,
                    rerank=body.rerank,
                ),
                config,
                request.app.state.reranker,
            )
            if body.dimension == "findings" and cell.answer.insufficient_evidence:
                cell.answer.answer = (
                    "No explicit finding could be verified in the retrieved passages."
                )
        except HTTPException as exc:
            if exc.status_code not in (502, 503, 504):
                raise
            cell.error = str(exc.detail)
        cells.append(cell)
    return CompareResponse(
        dimension=body.dimension,
        question=QUESTIONS[body.dimension],
        cells=cells,
        latency_ms=round((perf_counter() - start) * 1000, 3),
    )
