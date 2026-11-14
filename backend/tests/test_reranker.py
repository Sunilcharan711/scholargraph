"""Reranking contract, candidate bounds, provenance, and failure behavior."""

from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.models import PaperChunk
from app.schemas.chat import Claim, GeneratedAnswer


def upload(client, pdf_bytes):
    response = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    assert response.status_code == 201
    return response.json()["id"]


def test_disabled_does_not_call_reranker(client, pdf_bytes):
    upload(client, pdf_bytes)
    provider = Mock()
    provider.score.side_effect = AssertionError("Must remain lazy")
    client.app.state.reranker = provider
    result = client.post("/api/search", json={"query": "retrieval"})
    assert result.status_code == 200
    assert result.json()["reranked_count"] == 0
    assert result.json()["reranker_model"] is None
    provider.score.assert_not_called()


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_rerank_before_top_k_and_full_text(client, pdf_bytes, session_factory, mode):
    paper_id = upload(client, pdf_bytes)
    baseline = client.post(
        "/api/search", json={"query": "retrieval", "mode": mode, "top_k": 50}
    ).json()["results"]
    target = baseline[-1]["chunk_id"]
    with session_factory() as session:
        chunk = session.get(PaperChunk, UUID(target))
        chunk.text += " " + "retrieval " * 150 + "TAIL_EVIDENCE"
        session.commit()
    provider = Mock(identity="test@fixed")
    provider.score.side_effect = lambda query, texts: [
        10.0 if "TAIL_EVIDENCE" in t else -2.0 for t in texts
    ]
    client.app.state.reranker = provider
    response = client.post(
        "/api/search",
        json={"query": "retrieval", "mode": mode, "top_k": 1, "rerank": True, "diagnostics": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    hit = body["results"][0]
    assert hit["chunk_id"] == target and hit["paper_id"] == paper_id
    assert hit["score"] == 10 and hit["score_type"] == "cross_encoder"
    assert hit["diagnostics"]["reranker_score"] == 10
    assert hit["diagnostics"]["retrieval_score"] is not None
    assert body["reranked_count"] > 1 and body["rerank_ms"] >= 0
    assert body["reranker_model"] == "test@fixed"


@pytest.mark.parametrize("scores", [[], [float("nan")], [float("inf")]])
def test_invalid_scores_fail_explicitly(client, pdf_bytes, scores):
    upload(client, pdf_bytes)
    provider = Mock(identity="test")
    provider.score.side_effect = lambda q, texts: scores if not scores else scores * len(texts)
    client.app.state.reranker = provider
    response = client.post(
        "/api/search", json={"query": "retrieval", "mode": "bm25", "rerank": True}
    )
    assert response.status_code == 503


def test_filter_and_empty_skip_inference(client, pdf_bytes):
    upload(client, pdf_bytes)
    provider = Mock()
    client.app.state.reranker = provider
    result = client.post(
        "/api/search",
        json={"query": "retrieval", "rerank": True, "mode": "bm25", "paper_ids": [str(uuid4())]},
    )
    assert result.status_code == 200 and not result.json()["results"]
    provider.score.assert_not_called()


def test_bounds_and_tie_order(client, pdf_bytes, config):
    upload(client, pdf_bytes)
    config.reranker_candidate_limit = 2
    provider = Mock(identity="test")
    provider.score.side_effect = lambda q, texts: [1.0] * len(texts)
    client.app.state.reranker = provider
    result = client.post(
        "/api/search", json={"query": "retrieval", "mode": "dense", "top_k": 1, "rerank": True}
    ).json()
    assert result["reranked_count"] == 2
    assert len(provider.score.call_args.args[1]) == 2
    first = result["results"][0]["chunk_id"]
    other = client.post(
        "/api/search", json={"query": "retrieval", "top_k": 2, "rerank": True}
    ).json()["results"]
    assert first == min(r["chunk_id"] for r in other)


def test_unconfigured_reranker_is_actionable(client, pdf_bytes):
    upload(client, pdf_bytes)
    result = client.post("/api/search", json={"query": "retrieval", "mode": "bm25", "rerank": True})
    assert result.status_code == 503 and "RERANKER_MODEL" in result.json()["detail"]


def test_chat_receives_reranked_sources(client, pdf_bytes):
    upload(client, pdf_bytes)
    provider = Mock(identity="test")
    provider.score.side_effect = lambda q, texts: [9.0 if "synthetic" in t else -1.0 for t in texts]
    client.app.state.reranker = provider
    answer = Mock()
    answer.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text="Tiny synthetic dataset.", sources=[1])]
    )
    client.app.state.answer_provider = answer
    result = client.post(
        "/api/chat/query",
        json={"question": "retrieval", "mode": "dense", "top_k": 1, "rerank": True},
    )
    assert result.status_code == 200, result.text
    assert "synthetic" in answer.generate.call_args.args[1][0]["text"]
    assert result.json()["citations"][0]["page"] == 2
    assert result.json()["reranker_model"] == "test"


@pytest.mark.model
def test_real_cross_encoder(config):
    import os

    from app.retrieval.reranker import CrossEncoderReranker

    if os.environ.get("RUN_RERANKER_TESTS") != "1":
        pytest.skip("Set RUN_RERANKER_TESTS=1 to test the downloaded cross-encoder.")
    config.reranker_model = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    config.reranker_local_files_only = True
    model = CrossEncoderReranker(config)
    scores = model.score(
        "How is water supplied to tomato roots?",
        [
            "RRF merges ranked search lists.",
            "Drip irrigation supplies water directly to tomato roots.",
        ],
    )
    assert len(scores) == 2 and scores[1] > scores[0]
    assert "@" in model.identity
