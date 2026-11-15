from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from app.schemas.chat import Citation, Claim, GeneratedAnswer
from app.services.chat import OllamaProvider, missing_requested_metric, preserve_limitations


def test_unreported_metric_is_not_inferred_from_corpus_size():
    evidence = [{"text": "Only three synthetic documents were evaluated."}]
    assert missing_requested_metric("What accuracy did the system achieve?", evidence)
    assert not missing_requested_metric("What method measures accuracy?", evidence)
    assert not missing_requested_metric("How is accuracy measured?", evidence)
    for text in ("Accuracy was 92%.", "92% of predictions were correct."):
        assert not missing_requested_metric("What accuracy did it achieve?", [{"text": text}])


def test_limitations_keep_missing_measurements_and_separate_papers():
    citations = {
        i: Citation(
            source=i,
            paper_id=uuid4(),
            paper_title=f"Study {i}",
            chunk_id=uuid4(),
            page=3,
            section="Limitations",
            snippet=text,
            relevance_score=1,
        )
        for i, text in enumerate(
            [
                "No measured improvement or validated savings are reported [7]. Conditions vary.",
                "Only three synthetic documents were evaluated. Generalization is not established.",
            ],
            1,
        )
    }
    claims = [
        Claim(text="Conditions vary.", sources=[1]),
        Claim(text="The corpus is small.", sources=[2]),
        Claim(text="Another paraphrase.", sources=[1]),
    ]
    result = preserve_limitations("What limits the conclusions of both studies?", claims, citations)
    assert len(result) == 2
    assert "No measured improvement or validated savings" in result[0].text
    assert "〔7〕" in result[0].text and "[7]" not in result[0].text
    assert "three synthetic documents" in result[1].text
    assert [c.sources for c in result] == [[1], [2]]
    assert preserve_limitations("How does the method work?", claims, citations) == claims
    citations[1].section = "Methods"
    assert preserve_limitations("What are the limitations?", claims, citations)[0] == claims[0]
    mixed = [Claim(text="Vague conclusion.", sources=[1, 2])]
    assert preserve_limitations("What are the limitations?", mixed, citations) == [result[1]]


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
    # Reasoning models must spend the bounded output budget on the answer.
    assert seen[0]["think"] is False
    assert seen[0]["format"]["$defs"]["Claim"]["properties"]["sources"]["items"]["enum"] == [1]
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


@pytest.mark.parametrize(
    "content",
    [
        '{"insufficient_evidence":"false","claims":[]}',
        '{"insufficient_evidence":false,"claims":[{"text":"   ","sources":[1]}]}',
        '{"insufficient_evidence":false,"claims":[{"text":"claim","sources":[true]}]}',
        '{"insufficient_evidence":false,"claims":[{"text":"claim","sources":["1"]}]}',
        "not JSON",
    ],
)
def test_provider_rejects_malformed_claims(config, monkeypatch, content):
    from fastapi import HTTPException

    config.llm_provider = "ollama"
    config.chat_model = "test"
    real_client = httpx.Client
    monkeypatch.setattr(
        "app.services.chat.httpx.Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"message": {"content": content}})
            )
        ),
    )
    with pytest.raises(HTTPException) as exc:
        OllamaProvider(config).generate("question", [{"source": 1, "text": "evidence"}])
    assert exc.value.status_code == 503


@pytest.mark.parametrize("failure", ["timeout", "http", "truncated", "array"])
def test_provider_failures_are_explicit(config, monkeypatch, failure):
    from fastapi import HTTPException

    config.llm_provider = "ollama"
    config.chat_model = "test"
    real_client = httpx.Client

    def handle(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private upstream detail", request=request)
        if failure == "array":
            return httpx.Response(200, json=[])
        if failure == "http":
            return httpx.Response(500, text="private upstream detail")
        return httpx.Response(
            200,
            json={
                "done_reason": "length",
                "message": {"content": '{"insufficient_evidence":true,"claims":[]}'},
            },
        )

    monkeypatch.setattr(
        "app.services.chat.httpx.Client",
        lambda **kw: real_client(transport=httpx.MockTransport(handle)),
    )
    with pytest.raises(HTTPException) as exc:
        OllamaProvider(config).generate("question", [{"source": 1, "text": "evidence"}])
    assert exc.value.status_code == 503
    assert "private" not in exc.value.detail


def test_grouped_citation_markers_are_rejected(client, pdf_bytes):
    client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)})
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text="Invented marker [1, 99]", sources=[1])]
    )
    client.app.state.answer_provider = provider
    response = client.post("/api/chat/query", json={"question": "retrieval", "mode": "bm25"})
    assert response.status_code == 502


def test_evidence_filters_titles_and_duplicates(client, pdf_bytes, session_factory):
    from uuid import UUID

    from sqlalchemy import select

    from app.models import PaperChunk

    paper = client.post("/api/papers/upload", files={"file": ("paper.pdf", pdf_bytes)}).json()
    with session_factory() as session:
        chunks = session.scalars(
            select(PaperChunk).where(PaperChunk.paper_id == UUID(paper["id"]))
        ).all()
        chunks[0].text = paper["title"]
        for chunk in chunks[1:]:
            chunk.text = "A unique substantive passage about retrieval."
        session.commit()
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(insufficient_evidence=True, claims=[])
    client.app.state.answer_provider = provider
    response = client.post(
        "/api/chat/query", json={"question": "retrieval", "mode": "dense", "top_k": 12}
    )
    assert response.status_code == 200
    evidence = provider.generate.call_args.args[1]
    assert len(evidence) == 1
    assert evidence[0]["paper_title"] == paper["title"]
    assert evidence[0]["page"] >= 1
    body = response.json()
    assert body["evidence_count"] == 1
    assert 0 <= body["retrieval_ms"] <= body["latency_ms"]
    assert 0 <= body["generation_ms"] <= body["latency_ms"]


@pytest.mark.parametrize("second_page,legacy", [(False, False), (True, False), (True, True)])
def test_inferred_title_remains_evidence(client, session_factory, second_page, legacy):
    from uuid import UUID

    import pymupdf

    from app.models import Paper

    sentence = "Our measured accuracy increased to 92%."
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 60), sentence)
        if second_page:
            pdf.new_page().insert_text((50, 60), "Instrument maintenance logs are available.")
        upload = client.post("/api/papers/upload", files={"file": ("short.pdf", pdf.tobytes())})
    assert upload.status_code == 201 and upload.json()["title"] == sentence
    assert upload.json()["metadata_json"]["title_source"] == "first_page"
    if legacy:
        with session_factory() as session:
            paper = session.get(Paper, UUID(upload.json()["id"]))
            paper.metadata_json = {
                k: v for k, v in paper.metadata_json.items() if k != "title_source"
            }
            session.commit()
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text=sentence, sources=[1])]
    )
    client.app.state.answer_provider = provider
    response = client.post(
        "/api/chat/query",
        json={
            "question": "accuracy",
            "paper_ids": [upload.json()["id"]],
            "mode": "bm25",
        },
    )
    assert response.status_code == 200
    assert response.json()["evidence_count"] == 1
    assert response.json()["citations"][0]["snippet"] == sentence
    assert response.json()["citations"][0]["page"] == 1
