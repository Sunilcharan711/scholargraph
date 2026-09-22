import math
from collections.abc import Sequence
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from embedding_fixtures import TestEmbedder
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from test_search import seed_chunk

from app.core.config import Settings
from app.main import create_app
from app.retrieval.base import RetrievalHit
from app.retrieval.bm25 import bm25_scores, tokenize
from app.retrieval.fusion import reciprocal_rank_fusion
from app.schemas.search import RetrievalDiagnostics


def hit(number: int, score: float = 1) -> RetrievalHit:
    return RetrievalHit(
        UUID(int=number),
        UUID(int=99),
        "Paper",
        1,
        "Methods",
        "evidence",
        score,
        RetrievalDiagnostics(),
    )


def test_bm25_known_score_and_duplicate_query_terms() -> None:
    assert bm25_scores("alpha", ["alpha"]) == pytest.approx([math.log(4 / 3)])
    assert bm25_scores("alpha alpha", ["alpha"]) == bm25_scores("alpha", ["alpha"])


def test_bm25_length_normalization_and_frequency_saturation() -> None:
    short, long = bm25_scores("alpha", ["alpha", "alpha " + "filler " * 20])
    assert short > long
    first, second = bm25_scores("alpha", ["alpha beta", "alpha alpha"], b=0)
    assert first < second < 2 * first


def test_tokenization_empty_and_nonmatching() -> None:
    assert tokenize("BERT-base V2.1 CAFÉ ＡＢＣ") == ["bert", "base", "v2", "1", "café", "abc"]
    assert bm25_scores("alpha", []) == []
    assert bm25_scores("alpha", ["", "!!!"]) == [0, 0]
    assert bm25_scores("missing", ["alpha", "beta"]) == [0, 0]
    assert bm25_scores("!!!", ["alpha"]) == [0]


@pytest.mark.parametrize("k1,b", [(0, 0.75), (1.5, -1), (1.5, 2), (float("nan"), 0.75)])
def test_bm25_invalid_parameters(k1: float, b: float) -> None:
    with pytest.raises(ValueError):
        bm25_scores("alpha", ["alpha"], k1, b)


def test_rrf_formula_duplicates_ties_and_no_mutation() -> None:
    a, b, c = hit(1), hit(2), hit(3)
    result = reciprocal_rank_fusion([a, b, b], [c, b])
    assert result[0].chunk_id == b.chunk_id
    assert result[0].score == pytest.approx(2 / 62)
    assert result[0].diagnostics.dense_rank == result[0].diagnostics.bm25_rank == 2
    assert [r.chunk_id for r in result[1:]] == [a.chunk_id, c.chunk_id]
    assert a.diagnostics.fused_score is None
    assert reciprocal_rank_fusion([], []) == []
    assert reciprocal_rank_fusion([], [a, a, b])[1].score == pytest.approx(1 / 62)
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([a], [], 0)


def test_rrf_ignores_raw_score_scale() -> None:
    a, b = hit(1), hit(2)
    original = reciprocal_rank_fusion([a, b], [b, a])
    scaled = reciprocal_rank_fusion(
        [replace(a, score=-0.9), replace(b, score=-1)],
        [replace(b, score=1000), replace(a, score=500)],
    )
    assert [(r.chunk_id, r.score) for r in original] == [(r.chunk_id, r.score) for r in scaled]


def test_bm25_without_model_and_with_legacy_chunks(
    config: Settings,
    session_factory: sessionmaker[Session],
) -> None:
    class Unavailable(TestEmbedder):
        def encode(self, texts: Sequence[str]) -> list[list[float]]:
            raise RuntimeError("model unavailable")

    with session_factory() as session:
        legacy = seed_chunk(session, "BERT-base", None)
        seed_chunk(session, "BERT-base", [1, 0], model="old@v1")
        seed_chunk(session, "BERT-base", None, status="deleting")
        paper_id = str(legacy.paper_id)
    with TestClient(create_app(config, session_factory, Unavailable())) as client:
        response = client.post(
            "/api/search", json={"query": "bert", "mode": "bm25", "diagnostics": True}
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["results"]) == 2
        assert body["embedding_model"] is None and body["embedding_ms"] == 0
        assert body["indexed_chunk_count"] == 2 and body["excluded_chunk_count"] == 0
        assert body["results"][0]["score_type"] == "bm25"
        assert body["results"][0]["similarity_score"] is None
        assert body["results"][0]["diagnostics"]["bm25_rank"] == 1
        filtered = client.post(
            "/api/search", json={"query": "bert", "mode": "bm25", "paper_ids": [paper_id]}
        ).json()
        assert [r["paper_id"] for r in filtered["results"]] == [paper_id]
        assert filtered["results"][0]["diagnostics"] is None
        assert (
            client.post("/api/search", json={"query": "bert", "mode": "hybrid"}).status_code == 503
        )


def test_hybrid_uses_candidates_before_top_k(
    client: TestClient,
    config: Settings,
    session_factory: sessionmaker[Session],
) -> None:
    config.search_candidate_limit = 3
    config.rrf_k = 10
    with session_factory() as session:
        seed_chunk(session, "irrelevant", [0, 1, 0])
        consensus = seed_chunk(session, "battery filler filler filler", [0.6, 0.8, 0])
        lexical = seed_chunk(session, "battery", None)
        consensus_id, lexical_paper = str(consensus.id), str(lexical.paper_id)
    response = client.post(
        "/api/search", json={"query": "battery", "mode": "hybrid", "top_k": 1, "diagnostics": True}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    winner = body["results"][0]
    assert winner["chunk_id"] == consensus_id
    assert winner["score_type"] == "rrf" and winner["similarity_score"] is None
    assert winner["score"] == pytest.approx(2 / 12)
    assert winner["diagnostics"]["dense_rank"] == winner["diagnostics"]["bm25_rank"] == 2
    assert body["candidate_limit"] == 3 and body["rrf_k"] == 10
    filtered = client.post(
        "/api/search", json={"query": "battery", "mode": "hybrid", "paper_ids": [lexical_paper]}
    ).json()
    assert [r["paper_id"] for r in filtered["results"]] == [lexical_paper]
    assert filtered["excluded_chunk_count"] == 1


@pytest.mark.parametrize("mode", ["bm25", "hybrid"])
def test_empty_and_unknown_filters(client: TestClient, mode: str) -> None:
    assert client.post("/api/search", json={"query": "alpha", "mode": mode}).json()["results"] == []
    assert (
        client.post(
            "/api/search", json={"query": "alpha", "mode": mode, "paper_ids": [str(uuid4())]}
        ).json()["results"]
        == []
    )


def test_fresh_upload_and_delete(client: TestClient, pdf_bytes: bytes) -> None:
    paper = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()
    for mode in ("bm25", "hybrid"):
        result = client.post("/api/search", json={"query": "retrieval", "mode": mode}).json()
        assert result["results"] and all(r["paper_id"] == paper["id"] for r in result["results"])
    assert client.delete("/api/papers/" + paper["id"]).status_code == 204
    for mode in ("bm25", "hybrid"):
        assert (
            client.post("/api/search", json={"query": "retrieval", "mode": mode}).json()["results"]
            == []
        )
