from fastapi import APIRouter

from app.db.session import AppSettings, DatabaseSession
from app.retrieval.dependencies import Embedder
from app.schemas.search import SearchRequest, SearchResponse
from app.services.search import search_papers

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(
    request: SearchRequest, session: DatabaseSession, embedder: Embedder, config: AppSettings
) -> SearchResponse:
    """Search ready papers with dense, lexical BM25, or hybrid retrieval."""
    return search_papers(session, embedder, request, config)
