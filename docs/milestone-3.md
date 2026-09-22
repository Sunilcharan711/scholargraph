# Milestone 3 verification

Implemented on 2026-09-22. Optional reranking and citation-grounded generation have not started.

## Delivered

- Shared typed Retriever, RetrievalBatch and RetrievalHit contract.
- DenseRetriever refactored to return reusable retrieval data.
- Lightweight BM25 implementation with positive IDF, term-frequency saturation,
  length normalization and Unicode-aware tokenization; no new dependency required.
- Request-time lexical corpus construction, so uploads/deletions need no cache invalidation.
- Equal-weight Reciprocal Rank Fusion using configurable k (default 60).
- Independent candidate retrieval before final top_k; default 50 candidates per method,
  increased to top_k if necessary, configured maximum 200.
- POST /api/search modes dense, bm25 and hybrid; dense remains the default.
- Explicit score/score_type fields and optional raw-score/rank diagnostics.
- Stage latency diagnostics and model-eligibility counts.
- Configuration and documentation updates; no database migration needed.

## Checks actually run

Initial clean baseline: 56 passed, 3 skipped with model tests disabled.
Final full suite: RUN_MODEL_TESTS=1 and EMBEDDING_LOCAL_FILES_ONLY=true.

| Check | Result |
| --- | --- |
| Full pytest suite | 72 passed, 1 skipped |
| Real local MiniLM PDF upload/search test in all three modes | Passed using SQLite test distance adapter |
| BM25 hand-calculated score and query-term deduplication | Passed |
| BM25 length normalization, frequency saturation and Unicode tokens | Passed |
| RRF formula, duplicates, missing lists, ties and raw-score scale independence | Passed |
| Hybrid candidate-pool consensus before final top_k | Passed |
| Paper/status filtering and lexical access to legacy/other-model chunks | Passed |
| BM25 with unavailable embedding model | Passed |
| Hybrid model failure returns 503 instead of silent lexical fallback | Passed |
| Fresh upload and deletion visible in both new modes | Passed |
| Ruff lint | Passed |
| Ruff format check | Passed, 52 Python files |
| git diff --check | Passed |

Tests generate original PDFs. The real-model check uses the previously verified cached
MiniLM weights; no download was required. A Windows default text-encoding issue while
writing the Unicode test fixture was fixed by writing UTF-8 explicitly.
Two existing upstream Starlette/AnyIO test-client deprecation warnings remain.

## Still unverified

Docker and PostgreSQL commands are unavailable, and the usual Docker executable path
is absent. No TEST_DATABASE_URL was configured. The PostgreSQL integration test was
expanded to cover BM25/hybrid but was skipped. Native pgvector execution, live migrations,
Docker image builds and Compose startup remain pending. SQLite/API/model tests do not
replace that verification. No new benchmark or general hybrid-quality claim is made.

## Design decisions and limits

BM25 scans/tokenizes selected ready chunk text per request. This favors correctness and
freshness for a small local library. Its memory/CPU cost grows with corpus size; candidate
limits bound fusion, not corpus loading. Replace it with an indexed lexical implementation
when measurements justify doing so, retaining the same retriever interface.

BM25 uses k1=1.5, b=0.75, and IDF=ln(1+(N-df+0.5)/(df+0.5)). It does not stem, remove
stop words or implement phrase syntax. Statistics depend on selected papers. No lexical
matches means no BM25 results; zero-score chunks are not padded into the candidate list.

RRF sums reciprocal one-based ranks, with one contribution per chunk per method.
Diagnostics preserve distinct BM25, cosine and fused scores. Similarity_score remains
cosine-only for existing dense clients and is null for BM25/hybrid. Excluded chunk counts
in hybrid describe the dense leg; those chunks can still be found lexically.

Both legs filter paper IDs and ready status; dense additionally filters embedding space.
Read operations run sequentially using the same session, with no strict snapshot-consistency
promise during concurrent edits. Search errors are explicit, and model failure does not
silently change the requested retrieval method.

## Try it

Start the configured backend, then send this JSON to POST /api/search:

```json
{
  "query": "What limitations do the authors discuss?",
  "paper_ids": [],
  "top_k": 10,
  "mode": "hybrid",
  "diagnostics": true
}
```

To use lexical search without a model, select mode=bm25. Existing papers remain searchable
lexically even if their vectors are absent or belong to another model. For hybrid/dense,
index legacy papers with the documented scripts/index_papers.py command as needed.

Suggested commit: `feat: add BM25 and hybrid retrieval with rank diagnostics`

No commit or push was made in this milestone. Copyright and existing licensing remain unchanged.
