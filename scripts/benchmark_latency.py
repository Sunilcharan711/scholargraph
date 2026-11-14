"""Measure stages of the same end-to-end hybrid chat request."""

import argparse
from collections import defaultdict
from math import ceil
from statistics import median
from time import perf_counter

from evaluation import library, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("repeats must be positive")
    report = {"rerank": args.rerank, "repeats": args.repeats, "samples": [], "errors": []}
    stages = defaultdict(list)
    with library() as (client, cases, *_):
        report["embedding_model"] = client.app.state.embedder.spec.key
        for repeat in range(args.repeats):
            for case in cases:
                start = perf_counter()
                response = client.post(
                    "/api/chat/query",
                    json={"question": case.question, "top_k": 5, "rerank": args.rerank},
                )
                total = (perf_counter() - start) * 1000
                if response.is_error:
                    report["errors"].append(
                        {
                            "question": case.question,
                            "repeat": repeat,
                            "error": response.json()["detail"],
                        }
                    )
                    continue
                data = response.json()
                times = {
                    key: data[key]
                    for key in ("embedding_ms", "search_ms", "rerank_ms", "generation_ms")
                }
                times["total_ms"] = round(total, 3)
                for key, value in times.items():
                    stages[key].append(value)
                report["samples"].append(
                    {
                        "question": case.question,
                        "repeat": repeat,
                        "model": data["model"],
                        "reranker": data["reranker_model"],
                        **times,
                    }
                )
    report["summary"] = {
        key: {"median": median(values), "p95": sorted(values)[ceil(0.95 * len(values)) - 1]}
        for key, values in stages.items()
    }
    save("latency-reranked.json" if args.rerank else "latency.json", report)
    if report["errors"]:
        raise SystemExit("Incomplete latency run; see report.")


if __name__ == "__main__":
    main()
