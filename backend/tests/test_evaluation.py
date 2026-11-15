from math import log2
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def scripts_path(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))


def test_ranked_metrics_use_cutoff_and_count_duplicate_once():
    from evaluation import ranking

    scores = ranking(["wrong", "a", "a", "b"], ["a", "b"], 3)
    assert scores == pytest.approx(
        {"precision": 1 / 3, "recall": 0.5, "mrr": 0.5, "ndcg": (1 / log2(3)) / (1 + 1 / log2(3))}
    )
    assert ranking([], ["a"], 5) == dict.fromkeys(scores, 0)
    assert ranking(["a"], ["a"], 5)["precision"] == 0.2


def test_review_requires_explicit_judgments_and_handles_abstention():
    from run_rag_eval import score

    row = {
        "question": "Unknown?",
        "expected_points": [],
        "relevant_chunk_ids": [],
        "context": [{"chunk": "irrelevant"}],
        "claims": [],
        "review": {
            "answer_relevance": [None],
            "expected_point_coverage": [],
            "groundedness": [],
            "citation_correctness": [],
        },
    }
    with pytest.raises(ValueError, match="answer_relevance"):
        score([row])
    row["review"]["answer_relevance"] = [True]
    metrics = score([row])
    assert metrics["unsupported_claim_rate"]["rate"] is None
    assert metrics["answer_relevance"]["rate"] == 1
    assert metrics["context_relevance"]["rate"] == 0


def test_recorder_observes_final_source_quotations():
    from unittest.mock import Mock

    from run_rag_eval import Recorder

    from app.schemas.chat import Claim, GeneratedAnswer

    provider = Mock()
    provider.generate.return_value = GeneratedAnswer(
        insufficient_evidence=False, claims=[Claim(text="Draft", sources=[1])]
    )
    recorder = Recorder(provider)
    result = recorder.generate("Question", [{"source": 1, "text": "No measurements."}])
    result.claims = [Claim(text='"No measurements."', sources=[1])]
    assert recorder.claims == [{"text": '"No measurements."', "sources": [1]}]
