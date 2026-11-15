"""Opt-in live-model checks for topic drift and missing cross-paper evidence.

Uses the original synthetic corpus. Citation coverage and required concepts are
regression checks, not a substitute for reviewing semantic support.
"""

import re

from evaluation import library, save


def main():
    report = {"cases": []}
    with library() as (client, cases, _, chunks, _):
        for index in (2, 5):
            case = cases[index]
            for top_k in (5, 6):  # Evaluation and frontend evidence budgets.
                response = client.post(
                    "/api/chat/query", json={"question": case.question, "top_k": top_k}
                )
                response.raise_for_status()
                answer = response.json()
                cited = {chunks[c["chunk_id"]] for c in answer["citations"]}
                text = answer["answer"].lower()
                concepts = (
                    [r"map", r"metadata", r"reject|unknown|invalid"]
                    if index == 2
                    else [r"synthetic", r"yield", r"water sav", r"no |not |neither|without"]
                )
                passed = (
                    not answer["insufficient_evidence"]
                    and set(case.relevant_chunk_ids) <= cited
                    and all(re.search(pattern, text) for pattern in concepts)
                )
                report["cases"].append(
                    {"question": case.question, "top_k": top_k, "passed": passed, **answer}
                )
                print(case.question, top_k, "PASS" if passed else "FAIL", flush=True)
    save("answer-regressions.json", report)
    if not all(case["passed"] for case in report["cases"]):
        raise SystemExit("Answer regression failed; inspect reports/answer-regressions.json.")


if __name__ == "__main__":
    main()
