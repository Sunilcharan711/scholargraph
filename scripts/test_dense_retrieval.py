"""Small real-model semantic smoke check, or a read-only check of a running search API."""

import argparse
import json
from pathlib import Path
from time import perf_counter

import httpx
from app.core.config import get_settings
from app.retrieval.embeddings import embed_texts
from app.retrieval.sentence_transformer import SentenceTransformerEmbedder

DOCUMENTS = [
    "Solar panels turn sunlight into electricity. Photovoltaic cells generate renewable energy.",
    "A clinical trial tests a vaccine. Vaccination trains the immune system to resist infection.",
    "A database index speeds up record lookup. SQL queries retrieve rows from relational tables.",
]
QUESTIONS = [
    "How can we produce electrical power from the sun?",
    "How do immunizations protect people against disease?",
    "How can indexed tables make data retrieval faster?",
]


def model_smoke() -> dict[str, object]:
    provider = SentenceTransformerEmbedder(get_settings())
    start = perf_counter()
    documents = embed_texts(provider, DOCUMENTS)
    document_ms = (perf_counter() - start) * 1000
    start = perf_counter()
    queries = embed_texts(provider, QUESTIONS)
    query_ms = (perf_counter() - start) * 1000
    checks = []
    for expected, query in enumerate(queries):
        scores = [sum(a * b for a, b in zip(query, doc, strict=True)) for doc in documents]
        first = max(range(len(scores)), key=lambda index: scores[index])
        checks.append(
            {
                "question": QUESTIONS[expected],
                "expected": expected,
                "actual": first,
                "scores": [round(score, 6) for score in scores],
                "passed": first == expected,
            }
        )
    return {
        "scope": "real local model + in-memory cosine; not PostgreSQL or an evaluation benchmark",
        "model": provider.spec.key,
        "dimensions": provider.spec.dimensions,
        "document_embedding_ms_including_model_load": round(document_ms, 3),
        "query_embedding_ms": round(query_ms, 3),
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", help="For example http://localhost:8000; uses existing papers")
    parser.add_argument("--query", default="What limitations do the authors discuss?")
    parser.add_argument("--paper-id", action="append", default=[])
    parser.add_argument("--output", type=Path, default=Path("reports/dense_smoke.json"))
    args = parser.parse_args()
    try:
        if args.api_url:
            response = httpx.post(
                f"{args.api_url.rstrip('/')}/api/search",
                json={
                    "query": args.query,
                    "paper_ids": args.paper_id,
                    "top_k": 5,
                    "mode": "dense",
                },
                timeout=180,
            )
            response.raise_for_status()
            payload = response.json()
            result = {
                "scope": "running API search against existing papers",
                "response": payload,
                "passed": bool(payload["results"]),
            }
        else:
            result = model_smoke()
    except Exception as exc:
        print(f"Smoke check failed ({type(exc).__name__}). Check model/database configuration.")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
