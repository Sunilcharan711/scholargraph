from fastapi import APIRouter, Request

from app.db.session import AppSettings, DatabaseSession
from app.retrieval.dependencies import Embedder
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat import answer_question

router = APIRouter(tags=["chat"])


@router.post("/chat/query", response_model=ChatResponse)
def query(
    body: ChatRequest,
    request: Request,
    session: DatabaseSession,
    config: AppSettings,
    embedder: Embedder,
) -> ChatResponse:
    return answer_question(session, embedder, request.app.state.answer_provider, body, config)
