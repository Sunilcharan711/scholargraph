"""Semantic relationships within a bounded window of the ready library."""

from collections import Counter, defaultdict
from uuid import UUID

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Paper, PaperChunk
from app.schemas.graph import GraphEdge, GraphNode, PaperGraph


def build_graph(
    session: Session, config: Settings, minimum: float | None = None, focus: UUID | None = None
) -> PaperGraph:
    threshold = config.graph_min_similarity if minimum is None else minimum
    query = select(Paper).where(Paper.processing_status == "ready")
    if focus is not None:
        # Include even an older focus paper outside the default library window.
        query = query.order_by((Paper.id == focus).desc())
    papers = list(
        session.scalars(
            query.order_by(Paper.uploaded_at.desc(), Paper.id).limit(config.graph_max_papers + 1)
        )
    )
    truncated = len(papers) > config.graph_max_papers
    papers = papers[: config.graph_max_papers]
    if focus is not None and (not papers or papers[0].id != focus):
        raise HTTPException(404, "Paper not found.")

    totals = {}
    spaces = {}
    invalid = set()
    ids = [p.id for p in papers]
    rows = select(
        PaperChunk.paper_id,
        PaperChunk.embedding_model,
        PaperChunk.embedding_dimensions,
        PaperChunk.token_count,
        PaperChunk.embedding,
    ).where(PaperChunk.paper_id.in_(ids))
    for pid, model, dims, weight, vector in session.execute(rows.execution_options(yield_per=128)):
        if pid in invalid:
            continue
        space = (model, dims)
        if vector is None or not model or spaces.setdefault(pid, space) != space:
            invalid.add(pid)
            continue
        v = np.asarray(vector, dtype=float)
        if v.shape != (dims,) or not np.isfinite(v).all():
            invalid.add(pid)
            continue
        if pid not in totals:
            totals[pid] = np.zeros_like(v)
        totals[pid] += weight * v
    groups = defaultdict(list)
    indexed = set()
    for pid in sorted(totals.keys() - invalid):
        norm = np.linalg.norm(totals[pid])
        if norm > 0 and np.isfinite(norm):
            groups[spaces[pid]].append((pid, totals[pid] / norm))
            indexed.add(pid)
    candidates = []
    for group in groups.values():
        members = [pid for pid, _ in group]
        if focus is not None and focus not in members:
            continue
        matrix = np.stack([vector for _, vector in group])
        scores = matrix @ (matrix.T if focus is None else matrix[members.index(focus)])
        similarities = np.clip(scores, -1, 1)
        # Unit-vector dot products can undershoot 1 through floating-point roundoff.
        similarities[np.isclose(similarities, 1.0, rtol=0, atol=1e-12)] = 1.0
        if focus is None:
            for i, j in zip(*np.where(np.triu(similarities >= threshold, k=1)), strict=True):
                candidates.append((-float(similarities[i, j]), members[i], members[j]))
        else:
            for j in np.flatnonzero(similarities >= threshold):
                if members[j] != focus:
                    a, b = sorted((focus, members[j]))
                    candidates.append((-float(similarities[j]), a, b))
    degree = Counter()
    edges = []
    visible = set(ids) if focus is None else {focus}
    for negative, a, b in sorted(candidates):
        if max(degree[a], degree[b]) >= config.graph_max_neighbors:
            continue
        degree.update((a, b))
        visible.update((a, b))
        edges.append(GraphEdge(source_paper_id=a, target_paper_id=b, similarity_score=-negative))
    nodes = [
        GraphNode(
            id=p.id,
            title=p.title,
            authors=p.authors,
            year=p.publication_year,
            keywords=p.metadata_json.get("keywords") or [],
            indexed=p.id in indexed,
        )
        for p in papers
        if p.id in visible
    ]
    return PaperGraph(
        nodes=nodes,
        edges=edges,
        min_similarity=threshold,
        max_neighbors=config.graph_max_neighbors,
        truncated=truncated,
        papers_considered=len(papers),
    )
