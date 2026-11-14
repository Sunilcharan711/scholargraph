# Milestone 5 — Q&A reliability pass (October 14, 2026)

## Delivered

- More explicit answer instructions, evidence-first source blocks, and the actual
  question last. Existing local Ollama provider remains configurable.
- Repeated title-only and duplicate passages are removed from Q&A evidence. The service
  retrieves up to three times the requested evidence count (capped at 50) to refill
  those omissions. At most `top_k` passages and 16,000 characters reach the model.
  Individual excerpts remain capped at 4,000 characters. Character limits are not
  exact token guarantees, especially for non-English text.
- Passage titles, page numbers and sections accompany evidence, with stable IDs.
- Provider JSON schema limits source numbers to the current evidence. Server-side
  checks still reject unknown references and invented numeric citation markers.
- Strict source-ID types and boolean output validation; blank claims, malformed JSON,
  incomplete/truncated output and transport failures are rejected explicitly.
- Response timings separate retrieval/evidence preparation from generation; evidence
  count is exposed. No database migration or frontend change is required.
- An opt-in reproducible evaluation, `scripts/evaluate_qa.py`, uses real MiniLM,
  real Ollama, generated original PDFs and a temporary SQLite database. It leaves the
  user's library untouched and checks citation IDs, page numbers, excerpts and PDF access.

## Verification

Backend full suite: **97 passed, 1 skipped** with real-model tests enabled. The local
PostgreSQL integration case is skipped because no test server is configured. Existing
PostgreSQL CI evidence is recorded separately in `verification-2026-10-13.md`.
Ruff lint and formatting passed. No new frontend code was added; frontend/browser tests
were not rerun for this backend-only change.
The running Next.js proxy on localhost:3000 was checked separately: the fusion-constant
question returned 60 with a page-2 citation, and the source PDF returned HTTP 200 with
a valid PDF signature. This was an HTTP integration check, not a browser interaction test.

Provider failure tests cover timeout, HTTP error, non-object payload, invalid JSON,
non-boolean abstention, non-integer source IDs, blank claims and token-limit truncation.
Evidence cleanup, citations, page/PDF access and existing ingestion/search regressions
remain covered. Two upstream Starlette/AnyIO deprecation warnings persist.

## Real-model before/after check

Three original synthetic PDFs, six hand-authored questions; four answerable questions
and two deliberately unsupported questions. Same `qwen2.5:1.5b` Ollama model and
MiniLM revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, with hybrid retrieval and
paper filters. These are development cases used while adjusting the prompt, not a
held-out benchmark. Each reported version was run once; outputs can vary.

| Question | Previous behavior | Final behavior |
| --- | --- | --- |
| How are keyword and semantic retrieval combined? | Restated question, six citations | Mentions dense embeddings and RRF, two citations |
| What is the fusion constant? | Incorrect abstention | 60, correct Methods passage |
| What are the experiment's limitations? | Incorrect abstention | Still incorrectly abstains |
| Accuracy on 10,000 papers? | Correct abstention | Correct abstention |
| RRF question with only greenhouse paper selected | Correct abstention | Correct abstention |
| Water supplied to tomato roots? | Incorrect abstention | Drip irrigation, correct Methods passage plus an unnecessary citation |

Answer/abstention decisions matching expectations: **3/6 before, 5/6 after**.
The old first response was a weak restatement, so 3/6 must not be called answer accuracy.
All six final requests returned HTTP 200; every returned citation mapped to a stored
chunk from the selected paper with matching page and excerpt, and the PDF route worked.
Manual inspection found source redundancy: the hybrid-method answer also cites its
abstract; the irrigation answer also cites Limitations, which does not support the
irrigation claim. The Methods passage supports the answer in each case. The model also
omits BM25 by name in the hybrid explanation and does not retain every synthetic-study
qualification. Citation validity therefore must not be described as perfect grounding.

An intermediate claims-first schema produced unsupported claims, including invented
100% accuracy. It was rejected and is not the active implementation. A 3B-model download
was attempted but stalled; the application still uses the installed 1.5B model and
no model upgrade is claimed. No API key or external paper-text service was used.

## Reproduce

Start Ollama with the configured model available, then from the repository root:

```powershell
$env:EMBEDDING_LOCAL_FILES_ONLY = 'true'
uv run --project backend python scripts/evaluate_qa.py --label qa-check
```

Offline embeddings require the existing completed MiniLM cache. A fresh checkout must
first download it. Evaluation reports are written under ignored `reports/` and include
model inventory, prompts, answers and source metadata. Inspect the answers manually;
the automated summary measures decisions and source integrity, not semantic entailment.

The current pass improves the demo but does not establish reliable answering across
arbitrary scientific papers. Remaining work includes broader held-out evaluation,
false-abstention reduction, citation precision, prompt-injection evaluation and full
real-model/PostgreSQL verification. Optional reranking remains deferred.
