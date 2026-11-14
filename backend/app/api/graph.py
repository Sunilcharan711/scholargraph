from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import delete

from app.db.session import AppSettings, DatabaseSession
from app.models import PaperRelationship
from app.schemas.graph import PaperGraph
from app.services.graph import build_graph

router = APIRouter(prefix="/graph", tags=["graph"])
Threshold = Annotated[float | None, Query(ge=0, le=1)]


@router.get("", response_model=PaperGraph)
def library_graph(session: DatabaseSession, config: AppSettings, min_similarity: Threshold = None):
    return build_graph(session, config, min_similarity)


@router.post("/rebuild", response_model=PaperGraph)
def rebuild(session: DatabaseSession, config: AppSettings):
    """Replace the semantic snapshot atomically; preserve other relationship types."""
    graph = build_graph(session, config)
    session.execute(
        delete(PaperRelationship).where(
            PaperRelationship.relationship_type == "semantic_similarity"
        )
    )
    session.add_all(PaperRelationship(**edge.model_dump()) for edge in graph.edges)
    session.commit()
    return graph


@router.get("/{paper_id}", response_model=PaperGraph)
def related(
    paper_id: UUID, session: DatabaseSession, config: AppSettings, min_similarity: Threshold = None
):
    return build_graph(session, config, min_similarity, paper_id)
