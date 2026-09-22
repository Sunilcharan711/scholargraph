"""Small real-embedding retrieval evaluation; no external papers or claimed benchmark."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from app.core.config import PROJECT_ROOT, Settings
from app.db.demo import demo_engine
from app.main import create_app
from fastapi.testclient import TestClient
from make_demo_papers import generate
from sqlalchemy.orm import sessionmaker

CASES = [
    ("ALPHA-42", 0),
    ("How are keyword and semantic results combined?", 0),
    ("What does the fusion constant equal?", 0),
    ("How are source IDs mapped to paper pages?", 1),
    ("Does a citation guarantee a supported claim?", 1),
    ("When should an answer abstain?", 1),
    ("How is water delivered to tomato roots?", 2),
    ("What reduces evaporation from soil?", 2),
    ("What does the greenhouse sensor measure?", 2),
]


def main():
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = Settings(upload_dir=root / "uploads")
        engine = demo_engine(root / "evaluation.db")
        try:
            with TestClient(
                create_app(config, sessionmaker(engine, expire_on_commit=False))
            ) as client:
                ids = []
                for path in generate(root / "papers"):
                    result = client.post(
                        "/api/papers/upload", files={"file": (path.name, path.read_bytes())}
                    )
                    result.raise_for_status()
                    ids.append(result.json()["id"])
                report = {
                    "corpus": "3 original synthetic PDFs; 9 hand-authored queries",
                    "storage": "sqlite-demo",
                    "metrics": {},
                }
                for mode in ("dense", "bm25", "hybrid"):
                    ranks, latencies = [], []
                    for question, expected in CASES:
                        start = perf_counter()
                        response = client.post(
                            "/api/search", json={"query": question, "mode": mode, "top_k": 5}
                        )
                        response.raise_for_status()
                        results = response.json()["results"]
                        rank = next(
                            (i for i, r in enumerate(results, 1) if r["paper_id"] == ids[expected]),
                            None,
                        )
                        ranks.append(rank)
                        latencies.append((perf_counter() - start) * 1000)
                    report["metrics"][mode] = {
                        "hit_at_1": sum(r == 1 for r in ranks) / len(ranks),
                        "hit_at_5": sum(r is not None for r in ranks) / len(ranks),
                        "mrr_at_5": sum(1 / r if r else 0 for r in ranks) / len(ranks),
                        "mean_ms": sum(latencies) / len(latencies),
                        "ranks": ranks,
                    }
                report["embedding_model"] = client.app.state.embedder.spec.key
                target = PROJECT_ROOT / "reports/demo-evaluation.json"
                target.parent.mkdir(exist_ok=True)
                target.write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(json.dumps(report, indent=2))
        finally:
            engine.dispose()


if __name__ == "__main__":
    main()
