# ScholarGraph evaluation

## Milestone 9

The [question set](../evaluation/questions.json) covers three original synthetic PDFs,
six answerable questions and one unanswerable question. One question needs passages
from two papers. Each case lists its question, relevant paper and passage IDs, and
expected answer points. Paper IDs match generated filenames, and passage IDs combine
the filename stem and section heading. Each run resolves these labels against a fresh
SQLite library populated through the upload API. These authored cases measure behavior
on this fixture only.

Run the following from the repository root with backend dependencies installed. For
the fourth retrieval method, set `RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2`
and make its weights available. Answer and latency runs use the configured Ollama
server and `CHAT_MODEL`. The scripts write JSON under `reports/`. A failed method
or request is recorded and causes a nonzero exit.

```sh
uv run --project backend python scripts/run_retrieval_eval.py --top-k 5
uv run --project backend python scripts/run_rag_eval.py
uv run --project backend python scripts/run_rag_eval.py --score reports/rag-reviewed.json
uv run --project backend python scripts/benchmark_latency.py --repeats 3
uv run --project backend python scripts/benchmark_latency.py --repeats 3 --rerank
```

Retrieval scores are macro averages across the six answerable questions. Precision
uses K as the denominator even when fewer results return. Recall uses the number
of relevant items, MRR uses the first relevant rank within K, and nDCG uses binary
relevance with logarithmic discount. Paper scores collapse duplicate papers in the
returned K passages in first-appearance order.

| Passage retrieval at K=5 | Precision | Recall | MRR | nDCG |
| --- | ---: | ---: | ---: | ---: |
| BM25 | 0.233 | 1.000 | 0.917 | 0.949 |
| Dense | 0.200 | 0.917 | 0.917 | 0.898 |
| Hybrid | 0.233 | 1.000 | 1.000 | 0.987 |

The November 12 run used the cached MiniLM embedding model. Hybrid with reranking
returned HTTP 503 because its weights were unavailable locally and the registry
connection failed.

### Reviewing generated answers

Copy `reports/rag-eval.json` to `reports/rag-reviewed.json`. Read the returned
answer, its claims, the numbered passages the model saw, and the expected points.
Replace each null in the review arrays with a boolean before running `--score`.

- Mark answer relevance true when the answer addresses the question, or correctly
  abstains on an unanswerable question.
- Mark each expected point true only if the answer conveys the complete point.
- Mark each returned claim grounded when the supplied passages support all its
  assertions. Unsupported claim rate is the fraction failing this test.
- In claim and source order, mark each citation true when that passage directly
  supports the attached claim. An abstention contributes no claims or citations.
- The scorer computes context relevance from the fraction of passages actually
  supplied to the generator that have a relevant passage label.

In a review by Codex of one local Qwen2.5 1.5B run, 3/7 answers addressed the
question or correctly abstained. The answers covered 2/9 full expected points,
and 7/35 supplied passages were labeled relevant. All three returned claim blocks
were supported somewhere in context, but only 3/11 attached citations supported
their claim. The model also abstained on three answerable questions. These judgments
are available with the answers and evidence in `reports/rag-scored-baseline-nov12.json`.

### Timing

The benchmark records milliseconds for query embedding, retrieval (including fusion),
reranking, model generation, and total in-process HTTP request time. It reports
median and nearest-rank p95 across successful requests and includes every raw sample.
The total includes evidence assembly, validation and request handling. Corpus
indexing happens before timing. The first query is included, so model startup may
affect it. A disabled reranker contributes zero elapsed time.

The November 12 hybrid run used seven requests and one repetition, with reranking
disabled and local Qwen2.5 1.5B generation. Median embedding time was 33.24 ms,
retrieval 32.36 ms, generation 3,897.95 ms and total request time 4,010.90 ms.
Total p95 was 37,264.99 ms. Startup is included in the sample sequence. The small
sample and unspecified host load limit comparisons across machines.

Generated reports are ignored by Git and must be reproduced or reviewed in the local
workspace. The frontend Evaluation page bundles older paper-level retrieval and
abstention checks from September/October. The passage-level scores above use a
different question set and relevance unit.

## Demo verification — September 22, 2026

## Retrieval smoke evaluation

Three original synthetic PDFs and nine hand-authored questions. Real MiniLM embeddings
(revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`), SQLite demo storage,
and the actual upload/search API. A hit means the expected **paper** appears among
retrieved chunks; it does not establish passage-level relevance or claim support.

| Method | Hit@1 | Hit@5 | MRR@5 | Mean warm request time |
| --- | --- | --- | --- | --- |
| Dense | 9/9 | 9/9 | 1.000 | 55.3 ms |
| BM25 | 8/9 | 9/9 | 0.944 | 10.0 ms |
| Hybrid | 9/9 | 9/9 | 1.000 | 55.2 ms |

Run `uv run --project backend python scripts/evaluate_demo.py`. Generated detailed
results go to ignored `reports/demo-evaluation.json`. These queries were authored
alongside the corpus, not held out. This tiny check cannot rank retrieval approaches
on real research literature. Timings exclude initial model download and loading.

## Verification performed

- Backend suite: 86 passed, 1 skipped with real-model tests enabled; the skipped
  check requires a live PostgreSQL database.
- Ruff checks passed.
- Next.js production build and TypeScript checks passed.
- Playwright: 2 passed, desktop and mobile; mocked API responses.
- Live browser: uploaded three PDFs, searched through the real API, generated a real
  Ollama answer and opened its evidence dialog. Screenshots are in `docs/images`.
- Live generation: qwen2.5:1.5b returned a structurally valid cited answer in about
  7.5 seconds. It was too vague and cited unnecessary passages. Model/prompt quality
  improvement and a larger generation evaluation remain pending.
- The live-browser script stopped on an invalid URL in its PDF verification step;
  the API's PDF route is separately covered by backend tests. Do not interpret this
  as a fully passed end-to-end live browser test.
- PostgreSQL and Docker execution remain pending because neither runtime was available.
  The CI workflow includes a disposable PostgreSQL/pgvector integration test.

## Grounding limits

Each generated claim must provide source IDs; unknown IDs and fabricated numeric
citation markers are rejected. Metadata and excerpts are assembled from stored chunks,
not invented by the model. This validates provenance, not semantic entailment.
A model can still cite an irrelevant passage, omit a limitation, or fail to abstain.
Evidence is treated as untrusted text in the prompt, but prompt injection is not solved.

## October 13 verification update

The existing PostgreSQL CI job has now been inspected and confirmed passing.
See [verification details](verification-2026-10-13.md) for the exact test scope,
new local baseline results, and remaining Docker/real-model PostgreSQL gaps.

## October 14 Q&A update

A real-model six-case comparison and stricter response validation are documented in
[Milestone 5](milestone-5.md). Expected answer/abstention decisions improved from 3/6
to 5/6; this is not a held-out accuracy benchmark. One false abstention and redundant
citations remain.

## November 15 answer-model comparison

The initial November 15 setup template and Docker fallback used `qwen2.5:3b`. The original prompt,
structured-output schema, and retrieval settings are unchanged. Codex reviewed all
answers and cited passages from one local run against the same seven authored
questions used for the 1.5B baseline. This is a development comparison, not a
held-out benchmark or evidence of accuracy on real research papers.

| Measure | 1.5B baseline | 3B run |
| --- | --- | --- |
| Fully relevant answers or correct abstentions | 3/7 | 5/7 |
| Full expected points covered | 2/9 | 6/9 |
| Claims supported somewhere in supplied context | 3/3 | 8/8 |
| Attached citations supporting their claim | 3/11 | 8/8 |
| False abstentions on answerable questions | 3 | 0 |

The 3B model still answered the source-mapping question with an unrelated retrieval
explanation. It also omitted the greenhouse half of a two-paper comparison; this
partial answer was counted as a relevance failure. Supported statements can still
be irrelevant or incomplete. Supplied-context relevance remained 7/35.

The separate six-case scoped Q&A check matched all six expected answer/abstention
decisions, with valid source metadata in all six cases. Manual inspection found
the four substantive answers supported by their cited passages; the two absent
answers were correctly declined. Total request times ranged from 2.09 to 12.26
seconds on this machine. These scoped timings are not directly comparable to the
seven-question baseline timing above. The larger model needs more memory and disk.

Local artifacts: `reports/rag-reviewed-3b-nov15.json`, `reports/rag-scored.json`,
and `reports/qa-3b-nov15.json`. Reports are ignored by Git. Reproduce using
`CHAT_MODEL=qwen2.5:3b` with `scripts/run_rag_eval.py` and
`scripts/evaluate_qa.py --label qa-3b-nov15`, then review each answer and source
before scoring. Prompt/schema experiments were rejected because they introduced
incorrect answers or did not consistently improve these checks.

## November 15 Q&A regression fixes

The current setup uses `qwen3:4b` with Ollama thinking disabled. Qwen2.5 3B and
7B candidates still failed the reported questions; they are not the selected
fix. Qwen3 thinking mode exceeded the existing 120-second request timeout on
this host, so generation explicitly uses `think: false` and keeps the timeout.

The prompt now requires separate coverage of requested studies and explicit
measurement/validation gaps. For limitations questions, claims citing a labeled
limitations section are replaced with the supplied source excerpt when it fits
within 1,800 characters. This preserves negative results and qualifications, and
avoids replacing them with a vague paraphrase. Only already-cited passages are
used; unknown source IDs are still rejected before this step. Other questions
and longer excerpts keep the normal generation path. Numeric references inside
quoted paper text use distinct brackets so they cannot impersonate app citations.

Run `uv run --project backend python scripts/check_answer_regressions.py` with
Ollama running and the configured model installed. It checks the citation-mapping
question and the two-paper limitations question at both `top_k=5` and `top_k=6`.
All four cases failed with the previous 3B setup; all four passed with this fix.
The checks require relevant citations and expected concepts, not merely HTTP 200.
Inspect the actual answers in `reports/answer-regressions.json` as well: keyword
and citation coverage alone do not establish semantic correctness on unseen papers.
The RAG evaluator now records final displayed claims, including source quotations,
rather than the model's earlier draft.

The Windows launcher reads `/api/status` before reporting its storage mode, so
reusing the Docker stack reports PostgreSQL instead of incorrectly saying SQLite.

A conservative pre-generation check also declines a requested reported metric
when the retrieved passages do not discuss that metric or its supported aliases.
This prevents absent accuracy measurements from becoming claims of zero or failed
accuracy. It is an absence check, not a numerical fact checker; definition and
methodology questions continue through generation.

Final verification: 41 focused backend tests passed, with Ruff lint/format checks
passing. All six scoped Q&A cases matched expected answer/abstention decisions
and source metadata checks (`reports/qa-qwen3-verified.json`). Their total request
times ranged from about 0.03 seconds for the early metric abstention to 15.42
seconds for generated answers. The four substantive answers were inspected
against their cited excerpts. These are authored synthetic development cases,
not a held-out quality benchmark. The original two failures also have dedicated
checks at both evidence budgets as described above.
