"""Shared fixture, dataset validation and binary relevance metrics for Milestone 9."""

import json
from contextlib import contextmanager
from math import log2
from pathlib import Path
from tempfile import TemporaryDirectory

from app.core.config import PROJECT_ROOT, Settings
from app.main import create_app
from fastapi.testclient import TestClient
from make_demo_papers import generate
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import sessionmaker


class Case(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=1)
    relevant_paper_ids: list[str]
    relevant_chunk_ids: list[str]
    expected_points: list[str]


def ranking(ranked, relevant, k):
    """Binary judgments at cutoff k. A repeated result consumes a rank without credit."""
    if k < 1 or not relevant:
        raise ValueError("Positive cutoff and at least one relevant item required")
    gold = set(relevant)
    seen = set()
    hits = []
    for rank, item in enumerate(ranked[:k], 1):
        if item in gold and item not in seen:
            hits.append(rank)
            seen.add(item)
    ideal = sum(1 / log2(i + 1) for i in range(1, min(k, len(gold)) + 1))
    return {
        "precision": len(hits) / k,
        "recall": len(hits) / len(gold),
        "mrr": 1 / hits[0] if hits else 0,
        "ndcg": sum(1 / log2(i + 1) for i in hits) / ideal,
    }


@contextmanager
def library():
    from app.db.demo import demo_engine

    cases = [
        Case.model_validate(row)
        for row in json.loads((PROJECT_ROOT / "evaluation/questions.json").read_text())
    ]
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        settings = Settings(upload_dir=root / "uploads")
        engine = demo_engine(root / "eval.db")
        try:
            with TestClient(create_app(settings, sessionmaker(engine))) as client:
                papers, chunks, texts = {}, {}, {}
                for path in generate(root / "papers"):
                    response = client.post(
                        "/api/papers/upload", files={"file": (path.name, path.read_bytes())}
                    )
                    response.raise_for_status()
                    paper = response.json()
                    papers[paper["id"]] = path.stem
                    response = client.get(f"/api/papers/{paper['id']}?chunk_limit=100")
                    response.raise_for_status()
                    for chunk in response.json()["chunks"]:
                        section = chunk["section_title"]
                        if chunk["text"] == paper["title"]:
                            section = f"heading-{chunk['chunk_index']}"
                        key = f"{path.stem}/{section}"
                        if key in texts:
                            raise ValueError(f"Ambiguous evaluation passage: {key}")
                        chunks[chunk["id"]] = key
                        texts[key] = chunk["text"]
                for case in cases:
                    labels = set(case.relevant_chunk_ids)
                    if (
                        labels - texts.keys()
                        or {label.split("/")[0] for label in labels} != set(case.relevant_paper_ids)
                        or bool(labels) != bool(case.expected_points)
                    ):
                        raise ValueError(f"Inconsistent judgments for {case.question}")
                yield client, cases, papers, chunks, texts
        finally:
            engine.dispose()


def save(name, report):
    target = PROJECT_ROOT / "reports" / name
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    print(target, flush=True)
