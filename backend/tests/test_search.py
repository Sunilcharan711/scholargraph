from collections.abc import Sequence
from uuid import uuid4

import pytest
from embedding_fixtures import TestEmbedder
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.main import create_app
from app.models import Paper, PaperChunk
from app.retrieval.dense import dense_statement
from app.retrieval.embeddings import EmbeddingSpec
from app.schemas.search import SearchRequest
from app.services.indexing import index_paper


def seed_chunk(
    session: Session,
    title: str,
    vector: list[float] | None,
    model: str | None = "test-fixture@v1",
    status: str = "ready",
) -> PaperChunk:
    paper = Paper(
        title=title,
        authors=[],
        filename="test.pdf",
        file_path=f"{uuid4().hex}.pdf",
        processing_status=status,
        metadata_json={},
    )
    chunk = PaperChunk(
        paper=paper,
        page_number=2,
        section_title="Methods",
        chunk_index=0,
        text=f"{title} source evidence.",
        token_count=8,
        embedding=vector,
        embedding_model=model if vector is not None else None,
        embedding_dimensions=len(vector) if vector is not None else None,
    )
    session.add(chunk)
    session.commit()
    return chunk


def test_dense_ranking_filters_and_evidence(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        relevant = seed_chunk(session, "battery", [0, 1, 0])
        other = seed_chunk(session, "retrieval", [1, 0, 0])
        seed_chunk(session, "deleting", [0, 1, 0], status="deleting")
        seed_chunk(session, "old model", [0, 1], model="other@revision")
        seed_chunk(session, "legacy", None)
        seed_chunk(session, "different dimensions only", [0, 1])
        relevant_id, other_id = str(relevant.paper_id), str(other.paper_id)
    response = client.post("/api/search", json={"query": "battery", "top_k": 2, "mode": "dense"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["paper_id"] for r in body["results"]] == [relevant_id, other_id]
    assert body["results"][0]["similarity_score"] == pytest.approx(1)
    assert body["results"][1]["similarity_score"] == pytest.approx(0)
    assert body["results"][0]["page"] == 2
    assert body["results"][0]["section"] == "Methods"
    assert body["results"][0]["snippet"] == "battery source evidence."
    assert body["indexed_chunk_count"] == 2 and body["excluded_chunk_count"] == 3
    assert body["latency_ms"] >= body["embedding_ms"] >= 0
    filtered = client.post("/api/search", json={"query": "battery", "paper_ids": [other_id]}).json()
    assert [r["paper_id"] for r in filtered["results"]] == [other_id]
    assert filtered["excluded_chunk_count"] == 0
    unknown = client.post("/api/search", json={"query": "battery", "paper_ids": [str(uuid4())]})
    assert unknown.json()["results"] == []


def test_top_k_empty_and_stable_ties(
    client: TestClient, session_factory: sessionmaker[Session]
) -> None:
    assert client.post("/api/search", json={"query": "retrieval"}).json()["results"] == []
    with session_factory() as session:
        ids = [str(seed_chunk(session, "retrieval", [1, 0, 0]).id) for _ in range(3)]
    body = client.post("/api/search", json={"query": "retrieval", "top_k": 2}).json()
    assert [r["chunk_id"] for r in body["results"]] == sorted(ids)[:2]


@pytest.mark.parametrize(
    "payload",
    [
        {"query": " "},
        {"query": "x" * 2001},
        {"query": "x", "top_k": 0},
        {"query": "x", "top_k": 51},
        {"query": "x", "mode": "bm25"},
        {"query": "x", "paper_ids": ["invalid"]},
        {"query": "x", "paper_ids": [str(uuid4())] * 101},
    ],
)
def test_invalid_search_request(client: TestClient, payload: dict) -> None:
    assert client.post("/api/search", json=payload).status_code == 422


def test_postgresql_query_uses_guarded_cosine_and_filters() -> None:
    sql = str(
        dense_statement(
            SearchRequest(query="test", paper_ids=[uuid4()]), TestEmbedder.spec, [1, 0, 0]
        ).compile(dialect=postgresql.dialect())
    )
    assert "<=>" in sql and "CASE WHEN" in sql
    assert "embedding_model" in sql and "embedding_dimensions" in sql
    assert "paper_chunks.paper_id IN" in sql and "LIMIT" in sql


def test_failed_embedding_rolls_back_upload_and_hides_upstream_error(
    config: Settings,
    session_factory: sessionmaker[Session],
    pdf_bytes: bytes,
) -> None:
    class BrokenEmbedder(TestEmbedder):
        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            raise RuntimeError("private-key-and-path")

    with TestClient(create_app(config, session_factory, BrokenEmbedder())) as client:
        response = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
        assert response.status_code == 503
        assert "private-key" not in response.text
        assert not list(config.upload_dir.glob("*.pdf"))
        assert client.get("/api/papers").json()["total"] == 0
        assert client.post("/api/search", json={"query": "test"}).status_code == 503


def test_index_legacy_paper_preserves_chunk_ids_and_is_atomic(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        chunk = seed_chunk(session, "battery", None)
        paper_id, chunk_id = chunk.paper_id, chunk.id
        assert index_paper(paper_id, session, TestEmbedder()) == 1
        saved = session.get(PaperChunk, chunk_id)
        assert saved and saved.embedding == [0, 1, 0]

        class InvalidEmbedder(TestEmbedder):
            spec = EmbeddingSpec("broken-model", 3)

            def encode(self, texts: Sequence[str]) -> list[list[float]]:
                return [[float("nan"), 1, 0] for _ in texts]

        with pytest.raises(Exception, match="Embedding generation failed"):
            index_paper(paper_id, session, InvalidEmbedder())
        session.expire_all()
        assert session.get(PaperChunk, chunk_id).embedding_model == "test-fixture@v1"
    response = client.post("/api/search", json={"query": "battery"}).json()
    assert response["results"][0]["chunk_id"] == str(chunk_id)


def test_uploaded_paper_is_immediately_searchable(client: TestClient, pdf_bytes: bytes) -> None:
    uploaded = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    paper_id = uploaded.json()["id"]
    result = client.post("/api/search", json={"query": "retrieval", "paper_ids": [paper_id]}).json()
    assert result["results"] and result["excluded_chunk_count"] == 0
    assert result["results"][0]["paper_id"] == paper_id
    client.delete(f"/api/papers/{paper_id}")
    assert client.post("/api/search", json={"query": "retrieval"}).json()["results"] == []
