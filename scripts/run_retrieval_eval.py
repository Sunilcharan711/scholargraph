"""Compare four retrieval modes on the same labeled passages."""

import argparse
from statistics import mean

from evaluation import library, ranking, save


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, choices=range(1, 51), default=5)
    k = parser.parse_args().top_k
    report = {"top_k": k, "modes": {}}
    with library() as (client, cases, papers, chunks, _):
        report["embedding_model"] = client.app.state.embedder.spec.key
        for mode in ("bm25", "dense", "hybrid", "hybrid+reranker"):
            rows = []
            entry = report["modes"][mode] = {"cases": rows}
            for case in cases:
                if not case.relevant_chunk_ids:
                    continue
                response = client.post(
                    "/api/search",
                    json={
                        "query": case.question,
                        "mode": mode.split("+")[0],
                        "top_k": k,
                        "rerank": mode == "hybrid+reranker",
                    },
                )
                if response.is_error:
                    entry["error"] = response.json()["detail"]
                    break
                data = response.json()
                hits = data["results"]
                passage_ids = [chunks[h["chunk_id"]] for h in hits]
                paper_ids = list(dict.fromkeys(papers[h["paper_id"]] for h in hits))
                rows.append(
                    {
                        "question": case.question,
                        "passages": passage_ids,
                        "chunk_scores": ranking(passage_ids, case.relevant_chunk_ids, k),
                        "paper_scores": ranking(paper_ids, case.relevant_paper_ids, k),
                    }
                )
                entry["reranker_model"] = data["reranker_model"]
            if "error" not in entry:
                entry["macro_mean"] = {
                    level: {m: mean(row[level][m] for row in rows) for m in rows[0][level]}
                    for level in ("chunk_scores", "paper_scores")
                }
    save("retrieval-eval.json", report)
    if any("error" in mode for mode in report["modes"].values()):
        raise SystemExit("Incomplete comparison; see the recorded method error.")


if __name__ == "__main__":
    main()
