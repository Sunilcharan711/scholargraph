from fastapi import APIRouter

from app.db.session import DatabaseSession
from app.retrieval.dense import dense_search
from app.retrieval.dependencies import Embedder
from app.schemas.search import SearchRequest, SearchResponse

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(request: SearchRequest, session: DatabaseSession, embedder: Embedder) -> SearchResponse:
    """Search compatible vectors in ready papers using exact cosine similarity."""
    return dense_search(session, embedder, request)
