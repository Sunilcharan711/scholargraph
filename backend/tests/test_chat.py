from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from app.schemas.chat import Claim, GeneratedAnswer
from app.services.chat import OllamaProvider


def test_empty_evidence_never_calls_model(client):
    client.app.state.answer_provider = Mock()
    response = client.post("/api/chat/query", json={"question": "Unanswered?", "mode": "bm25"})
    assert response.status_code == 200
    assert response.json()["insufficient_evidence"]
    assert response.json()["citations"] == []
    client.app.state.answer_provider.generate.assert_not_called()


def test_sources_map_to_stored_chunks(client, pdf_bytes):
    paper = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()
    chunks = client.get(f"/api/papers/{paper['id']}").json()["chunks"]
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False,
        claims=[Claim(text="The study uses a tiny synthetic dataset.", sources=[1, 1])],
    )
    client.app.state.answer_provider = provider
    result = client.post("/api/chat/query", json={"question": "synthetic dataset", "mode": "bm25"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["answer"].endswith("[1]") and body["answer"].count("[1]") == 1
    assert len(body["citations"]) == 1
    source = body["citations"][0]
    chunk = next(c for c in chunks if c["id"] == source["chunk_id"])
    assert source["paper_id"] == paper["id"]
    assert source["page"] == chunk["page_number"] == 2
    assert source["snippet"] in chunk["text"]
    evidence = provider.generate.call_args.args[1]
    assert evidence[0]["text"] == source["snippet"]


@pytest.mark.parametrize(
    "sources,text", [([99], "Invented source"), ([0], "Zero source"), ([1], "Extra citation [99]")]
)
def test_invalid_citation_rejected(client, pdf_bytes, sources, text):
    client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text=text, sources=sources)]
    )
    client.app.state.answer_provider = provider
    result = client.post("/api/chat/query", json={"question": "retrieval", "mode": "bm25"})
    assert result.status_code == 502


def test_model_abstention_discards_claims(client, pdf_bytes):
    client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=True, claims=[Claim(text="This must not be returned", sources=[1])]
    )
    client.app.state.answer_provider = provider
    result = client.post("/api/chat/query", json={"question": "retrieval", "mode": "bm25"}).json()
    assert result["insufficient_evidence"] and not result["citations"]
    assert "must not" not in result["answer"]


def test_filtered_empty_does_not_leak_evidence(client, pdf_bytes):
    client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    client.app.state.answer_provider = Mock()
    result = client.post(
        "/api/chat/query",
        json={"question": "retrieval", "mode": "bm25", "paper_ids": [str(uuid4())]},
    )
    assert result.json()["insufficient_evidence"]
    client.app.state.answer_provider.generate.assert_not_called()


def test_unconfigured_model_returns_actionable_error(client, pdf_bytes):
    client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    response = client.post("/api/chat/query", json={"question": "retrieval", "mode": "bm25"})
    assert response.status_code == 503 and "CHAT_MODEL" in response.json()["detail"]


def test_pdf_route_uses_owned_storage(client, pdf_bytes):
    paper = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()
    result = client.get(f"/api/papers/{paper['id']}/pdf")
    assert result.content == pdf_bytes
    assert result.headers["content-type"] == "application/pdf"
    assert client.get(f"/api/papers/{uuid4()}/pdf").status_code == 404
    client.delete(f"/api/papers/{paper['id']}")
    assert client.get(f"/api/papers/{paper['id']}/pdf").status_code == 404


@pytest.mark.parametrize(
    "payload", [{"question": " "}, {"question": "x", "top_k": 13}, {"question": "x", "mode": "bad"}]
)
def test_invalid_question(client, payload):
    assert client.post("/api/chat/query", json=payload).status_code == 422


def test_ollama_transport_and_invalid_output(config, monkeypatch):
    config.llm_provider = "ollama"
    config.chat_model = "test-model"
    real_client = httpx.Client
    seen = []

    def handler(request):
        import json

        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(
            200, json={"message": {"content": '{"insufficient_evidence":true,"claims":[]}'}}
        )

    monkeypatch.setattr(
        "app.services.chat.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handler)),
    )
    assert (
        OllamaProvider(config)
        .generate("Question", [{"source": 1, "text": "untrusted"}])
        .insufficient_evidence
    )
    assert seen[0]["stream"] is False and seen[0]["format"]["type"] == "object"
    assert "untrusted" in seen[0]["messages"][0]["content"]


def test_demo_persists_real_pipeline(tmp_path, config, embedder, pdf_bytes):
    # Run in a subprocess: avoid replacing the test suite's SQLite SQL compiler.
    import subprocess
    import sys

    script = """
import sys
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.db.demo import demo_engine
from app.main import create_app
from app.core.config import Settings
from embedding_fixtures import TestEmbedder
root = Path(sys.argv[1])
for cycle in range(2):
    engine = demo_engine(root / 'demo.db')
    config = Settings(_env_file=None, upload_dir=root / 'uploads')
    app = create_app(config, sessionmaker(engine), TestEmbedder())
    with TestClient(app) as client:
        if cycle == 0:
            files = {'file': ('paper.pdf', (root / 'fixture.pdf').read_bytes())}
            assert client.post('/api/papers/upload', files=files).status_code == 201
        assert client.get('/api/papers').json()['total'] == 1
        for mode in ('dense', 'bm25', 'hybrid'):
            response = client.post('/api/search', json={'query': 'retrieval', 'mode': mode})
            assert response.status_code == 200, response.text
            assert response.json()['results']
    engine.dispose()
"""
    (tmp_path / "fixture.pdf").write_bytes(pdf_bytes)
    import os
    from pathlib import Path

    env = dict(os.environ, PYTHONPATH=str(Path(__file__).parent.resolve()))
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)], env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
