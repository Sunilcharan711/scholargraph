from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class GraphNode(BaseModel):
    id: UUID
    title: str
    authors: list[str]
    year: int | None
    keywords: list[str]
    indexed: bool


class GraphEdge(BaseModel):
    source_paper_id: UUID
    target_paper_id: UUID
    relationship_type: Literal["semantic_similarity"] = "semantic_similarity"
    similarity_score: float


class PaperGraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    min_similarity: float
    max_neighbors: int
    papers_considered: int
    truncated: bool
