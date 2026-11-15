"""Collect actual model evidence and answers; score a reviewed report without regenerating."""

import argparse
import json
from pathlib import Path

from evaluation import library, save


class Recorder:
    def __init__(self, provider):
        self.provider = provider
        self.context = []
        self.generated = None

    @property
    def claims(self):
        # The answer pipeline can replace paraphrases with source quotations.
        # Review the final claims that reached the user, not the earlier draft.
        return [claim.model_dump() for claim in self.generated.claims] if self.generated else []

    def generate(self, question, evidence):
        self.context = evidence
        self.generated = self.provider.generate(question, evidence)
        return self.generated


def score(rows):
    totals = {
        key: []
        for key in (
            "citation_correctness",
            "groundedness",
            "answer_relevance",
            "expected_point_coverage",
            "context_relevance",
        )
    }
    for row in rows:
        if "error" in row:
            raise ValueError("Cannot score a failed generation")
        review = row["review"]
        for name, size in [
            ("answer_relevance", 1),
            ("groundedness", len(row["claims"])),
            ("expected_point_coverage", len(row["expected_points"])),
            ("citation_correctness", sum(len(c["sources"]) for c in row["claims"])),
        ]:
            values = review[name]
            if len(values) != size or any(type(v) is not bool for v in values):
                raise ValueError(f"Complete {name} for {row['question']}")
            totals[name].extend(values)
        totals["context_relevance"].extend(
            passage["chunk"] in row["relevant_chunk_ids"] for passage in row["context"]
        )
    result = {
        key: {
            "passed": sum(values),
            "count": len(values),
            "rate": sum(values) / len(values) if values else None,
        }
        for key, values in totals.items()
    }
    claims = totals["groundedness"]
    result["unsupported_claim_rate"] = {
        "unsupported": len(claims) - sum(claims),
        "count": len(claims),
        "rate": (len(claims) - sum(claims)) / len(claims) if claims else None,
    }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score", type=Path, help="Score a copy with completed boolean judgments")
    args = parser.parse_args()
    if args.score:
        report = json.loads(args.score.read_text(encoding="utf-8-sig"))
        report["metrics"] = score(report["cases"])
        save("rag-scored.json", report)
        return
    report = {"cases": []}
    with library() as (client, cases, _, _, texts):
        report["embedding_model"] = client.app.state.embedder.spec.key
        lookup = {text: key for key, text in texts.items() if "/heading-" not in key}
        for case in cases:
            recorder = Recorder(client.app.state.answer_provider)
            client.app.state.answer_provider = recorder
            try:
                response = client.post(
                    "/api/chat/query", json={"question": case.question, "top_k": 5}
                )
            finally:
                client.app.state.answer_provider = recorder.provider
            row = case.model_dump()
            report["cases"].append(row)
            if response.is_error:
                row["error"] = response.json()["detail"]
                continue
            data = response.json()
            claims = [] if data["insufficient_evidence"] else recorder.claims
            row.update(
                model=data["model"],
                answer=data["answer"],
                abstained=data["insufficient_evidence"],
                context=[{**item, "chunk": lookup[item["text"]]} for item in recorder.context],
                claims=claims,
                review={
                    "answer_relevance": [None],
                    "expected_point_coverage": [None] * len(case.expected_points),
                    "groundedness": [None] * len(claims),
                    "citation_correctness": [None for claim in claims for _ in claim["sources"]],
                },
            )
    save("rag-eval.json", report)
    if any("error" in row for row in report["cases"]):
        raise SystemExit("Incomplete generation run; see report.")


if __name__ == "__main__":
    main()
