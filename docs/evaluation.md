# Demo verification — September 22, 2026

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
