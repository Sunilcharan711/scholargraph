"""Opt-in real-model Q&A smoke evaluation on original synthetic PDFs, not a benchmark."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from app.core.config import PROJECT_ROOT, Settings
from app.db.demo import demo_engine
from app.main import create_app
from fastapi.testclient import TestClient
from make_demo_papers import generate
from sqlalchemy.orm import sessionmaker

CASES = [
    ("How does the prototype combine keyword and semantic retrieval?", 0, False),
    ("What is the fusion constant?", 0, False),
    ("What are the experiment's limitations?", 0, False),
    ("What accuracy did the system achieve on 10,000 papers?", 0, True),
    ("How does reciprocal rank fusion work?", 2, True),
    ("How is water supplied to tomato roots?", 2, False),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="qa")
    args = parser.parse_args()
    if not args.label.replace("-", "").replace("_", "").isalnum():
        parser.error("label must contain only letters, digits, hyphens and underscores")
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        config = Settings(upload_dir=root / "uploads")
        with httpx.Client(timeout=5, trust_env=False) as connection:
            tags = connection.get(config.ollama_url.rstrip("/") + "/api/tags")
            tags.raise_for_status()
        engine = demo_engine(root / "qa.db")
        report = {"model": config.chat_model, "model_inventory": tags.json(), "cases": []}
        try:
            with TestClient(create_app(config, sessionmaker(engine))) as client:
                ids = []
                for path in generate(root / "papers"):
                    response = client.post(
                        "/api/papers/upload", files={"file": (path.name, path.read_bytes())}
                    )
                    response.raise_for_status()
                    ids.append(response.json()["id"])
                for question, paper_index, should_abstain in CASES:
                    response = client.post(
                        "/api/chat/query",
                        json={
                            "question": question,
                            "paper_ids": [ids[paper_index]],
                            "mode": "hybrid",
                        },
                    )
                    body = response.json()
                    sources = body.get("citations", [])
                    valid = response.status_code == 200
                    for source in sources:
                        detail = client.get(
                            f"/api/papers/{source['paper_id']}?chunk_limit=100"
                        ).json()
                        chunk = next(
                            (c for c in detail["chunks"] if c["id"] == source["chunk_id"]), None
                        )
                        valid = (
                            valid
                            and source["paper_id"] == ids[paper_index]
                            and bool(
                                chunk
                                and source["page"] == chunk["page_number"]
                                and source["snippet"] in chunk["text"]
                            )
                        )
                        pdf = client.get(f"/api/papers/{source['paper_id']}/pdf")
                        valid = (
                            valid and pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
                        )
                    case = {
                        "question": question,
                        "expected_abstention": should_abstain,
                        "status": response.status_code,
                        "source_integrity": valid,
                        "response": body,
                    }
                    report["cases"].append(case)
                    print(json.dumps(case), flush=True)
                report["embedding_model"] = client.app.state.embedder.spec.key
        finally:
            engine.dispose()
        report["summary"] = {
            "cases": len(report["cases"]),
            "http_successes": sum(c["status"] == 200 for c in report["cases"]),
            "source_integrity_passes": sum(c["source_integrity"] for c in report["cases"]),
            "abstention_decisions_matching_expectation": sum(
                c["status"] == 200
                and c["response"].get("insufficient_evidence") == c["expected_abstention"]
                for c in report["cases"]
            ),
            "note": "Decision checks are not correctness; inspect answers and support manually.",
        }
        target = PROJECT_ROOT / "reports" / f"{args.label}.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Saved {target}. Inspect semantic support manually; valid IDs are not entailment.")


if __name__ == "__main__":
    main()
