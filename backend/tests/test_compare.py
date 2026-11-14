from unittest.mock import Mock
from uuid import uuid4

import pymupdf
from fastapi import HTTPException

from app.schemas.chat import Claim, GeneratedAnswer


def upload(client, name, text=None):
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        pdf.set_metadata({"title": name})
        page.insert_textbox(
            (60, 60, 540, 700), text or f"The {name} study uses controlled methods and procedures."
        )
        payload = pdf.tobytes()
    response = client.post("/api/papers/upload", files={"file": (name + ".pdf", payload)})
    assert response.status_code == 201
    return response.json()["id"]


def test_each_column_uses_only_its_own_evidence(client):
    ids = [upload(client, name) for name in ("Alpha", "Beta")]
    provider = Mock()
    provider.generate.side_effect = lambda question, evidence: GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text=evidence[0]["text"], sources=[1])]
    )
    client.app.state.answer_provider = provider
    result = client.post("/api/compare", json={"paper_ids": ids, "mode": "bm25"})
    assert result.status_code == 200, result.text
    cells = result.json()["cells"]
    assert [cell["paper_id"] for cell in cells] == ids
    for index, cell in enumerate(cells):
        passages = provider.generate.call_args_list[index].args[1]
        assert {p["paper_title"] for p in passages} == {cell["title"]}
        assert {c["paper_id"] for c in cell["answer"]["citations"]} == {ids[index]}

    provider.generate.side_effect = [
        HTTPException(503, "Model unavailable"),
        GeneratedAnswer(insufficient_evidence=True, claims=[]),
    ]
    cells = client.post("/api/compare", json={"paper_ids": ids, "mode": "bm25"}).json()["cells"]
    assert cells[0]["error"] == "Model unavailable" and cells[0]["answer"] is None
    assert cells[1]["answer"]["insufficient_evidence"] and cells[1]["error"] is None


def test_invalid_comparison_is_rejected_before_generation(client):
    a, b = str(uuid4()), str(uuid4())
    client.app.state.answer_provider = Mock()
    for ids, code in (([a], 422), ([a, a], 422), ([a, b], 404)):
        assert client.post("/api/compare", json={"paper_ids": ids}).status_code == code
    client.app.state.answer_provider.generate.assert_not_called()


def test_findings_distinguish_paper_references_from_app_citations(client):
    text = "Our measured accuracy increased to 92% using the procedure in [14]."
    ids = [
        upload(client, "Measurement", text),
        upload(client, "Proposal", "We plan to test whether accuracy improved after training."),
    ]
    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text="selection", sources=[1])]
    )
    client.app.state.answer_provider = provider
    response = client.post("/api/compare", json={"paper_ids": ids, "dimension": "findings"})
    assert response.status_code == 200
    measured, plan = response.json()["cells"]
    assert measured["error"] is None
    answer = measured["answer"]
    (citation,) = answer["citations"]
    assert "〔14〕" in answer["answer"] and f"[{citation['source']}]" in answer["answer"]
    assert citation["paper_id"] == ids[0] and "[14]" in citation["snippet"]
    assert plan["answer"]["insufficient_evidence"] and not plan["answer"]["citations"]
    provider.generate.assert_called_once()
